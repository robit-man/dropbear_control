"""Cross-layer checks from generated Dropbear identity into host-link V1."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from host.myactuator_lib import hostlink_v1 as link


ROOT = Path(__file__).resolve().parents[2]
HOST_VIEW = ROOT / "generated/dropbear/host/dropbear_config.json"


def hello(endpoint_id: str, role: link.EndpointRole) -> link.Hello:
    return link.Hello(
        endpoint_id=endpoint_id,
        role=role,
        supported_major=link.VERSION_MAJOR,
        minimum_minor=0,
        maximum_minor=link.VERSION_MINOR,
        required_capabilities=link.MANDATORY_CAPABILITIES,
        offered_capabilities=link.MANDATORY_CAPABILITIES,
        minimum_rate_hz=10,
        maximum_rate_hz=1000,
        preferred_rate_hz=500,
        maximum_payload_size=link.MAX_PAYLOAD_SIZE,
    )


class GeneratedHostLinkContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.view = json.loads(HOST_VIEW.read_text(encoding="utf-8"))
        cls.generated = cls.view["generated_identity"]
        cls.registry = cls.view["registry"]
        cls.digest = link.sha256_from_hex(cls.generated["canonical_digest"])
        cls.identity = link.ConfigIdentity(
            cls.generated["configuration_id"],
            str(cls.generated["configuration_revision"]),
            cls.digest,
        )
        cls.negotiation = link.negotiate(
            hello("dropbear-host", link.EndpointRole.HOST),
            hello("dropbear-gateway", link.EndpointRole.GATEWAY),
        )

    def motion_candidate(self, *, config=None) -> link.Command:
        return link.Command(
            canonical_actuator_id=self.registry["actuators"][0]["actuator_id"],
            config=config or self.identity,
            source_identity="whole-body-controller",
            lease_id="offline-fixture-lease",
            lease_owner="gateway-arbiter-owner",
            lease_sequence=1,
            lease_expiry_monotonic_ns=2_000_000,
            mode=link.CommandMode.POSITION,
            enable_requested=True,
            position_rad=0.0,
        )

    def test_generated_identity_maps_exactly_into_host_link(self) -> None:
        self.assertEqual(
            link.sha256_to_hex(self.identity.sha256),
            self.generated["canonical_digest"],
        )
        self.assertEqual(self.identity.identity, self.generated["configuration_id"])
        self.assertEqual(
            self.identity.revision,
            str(self.generated["configuration_revision"]),
        )
        self.assertEqual(self.generated["configuration_state"], "incomplete_observation")

    def test_link_acceptance_never_promotes_incomplete_config_to_motion(self) -> None:
        self.assertFalse(self.registry["safety_admission"]["motion_enable_allowed"])
        command = self.motion_candidate()
        raw = link.encode_message(
            command,
            session_id=7,
            sequence=1,
            monotonic_ns=1_000_000,
            config_sha256=self.digest,
        )
        receiver = link.SessionReceiver(
            active_session_id=7,
            active_config_sha256=self.digest,
            negotiation=self.negotiation,
        )
        result = receiver.receive(
            link.decode_frame(raw), now_monotonic_ns=1_000_001
        )
        self.assertTrue(result.link_accepted)
        self.assertEqual(result.message, command)
        self.assertFalse(result.motion_authorized)

    def test_config_hash_mismatch_is_rejected_before_link_exposure(self) -> None:
        other = bytes.fromhex("a5" * 32)
        with self.assertRaises(link.ValidationError):
            link.encode_message(
                self.motion_candidate(),
                session_id=7,
                sequence=1,
                monotonic_ns=1_000_000,
                config_sha256=other,
            )

    def test_source_identity_is_not_aliased_to_lease_owner(self) -> None:
        command = self.motion_candidate()
        self.assertNotEqual(command.source_identity, command.lease_owner)
        restored = link.decode_message(
            link.decode_frame(
                link.encode_message(
                    command,
                    session_id=7,
                    sequence=1,
                    monotonic_ns=1_000_000,
                    config_sha256=self.digest,
                )
            )
        )
        self.assertEqual(restored.source_identity, "whole-body-controller")
        self.assertEqual(restored.lease_owner, "gateway-arbiter-owner")


if __name__ == "__main__":
    unittest.main()
