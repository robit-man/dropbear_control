from __future__ import annotations

import dataclasses
import json
import unittest
from dataclasses import replace
from pathlib import Path

from myactuator_lib.security_authorization import (
    Action,
    ApprovalAssertion,
    AuthorizationEngine,
    AuthorizationPolicy,
    AuthorizationRequest,
    DecisionCode,
    IdentityAssertion,
    Role,
    SafetyState,
    Target,
)


FIXTURE = Path(__file__).with_name("golden_authorization.jsonl")
ZERO = "0" * 64
ACTOR = "1" * 64
SESSION = "2" * 64
AUTH_CONTEXT = "3" * 64
CONFIG = "4" * 64
SOURCE = "5" * 64
GRAPH = "6" * 64
CORRELATION = "7" * 64
ARTIFACT = "8" * 64
REVIEWER = "9" * 64


def policy(**changes) -> AuthorizationPolicy:
    return replace(
        AuthorizationPolicy(CONFIG, SOURCE, GRAPH),
        **changes,
    )


def identity(**changes) -> IdentityAssertion:
    return replace(
        IdentityAssertion(
            ACTOR,
            SESSION,
            AUTH_CONTEXT,
            Role.OPERATOR,
            True,
            False,
            100,
            1000,
        ),
        **changes,
    )


def approval(**changes) -> ApprovalAssertion:
    return replace(
        ApprovalAssertion(
            REVIEWER,
            "a" * 64,
            Role.EVIDENCE_REVIEWER,
            True,
            False,
            100,
            1000,
            ARTIFACT,
        ),
        **changes,
    )


def request(**changes) -> AuthorizationRequest:
    return replace(
        AuthorizationRequest(
            Action.SUBMIT_MOTION,
            Target.PHYSICAL_REMOTE,
            SafetyState.ENABLED,
            SESSION,
            CORRELATION,
            1,
            500,
            CONFIG,
            SOURCE,
            GRAPH,
            ARTIFACT,
            True,
            True,
            True,
            True,
            True,
            approval(),
        ),
        **changes,
    )


def corpus_case(variant: str):
    selected_policy = policy()
    selected_identity = identity()
    selected_request = request()
    normal_capacity = 16
    prefill = False
    normal_ready = True
    safe_ready = True
    replay = False

    if variant == "observer_read":
        selected_identity = identity(role=Role.OBSERVER)
        selected_request = request(action=Action.READ_STATE, target=Target.OFFLINE)
    elif variant == "diagnostic_read":
        selected_identity = identity(role=Role.DIAGNOSTIC_OPERATOR)
        selected_request = request(
            action=Action.READ_DIAGNOSTICS, target=Target.PHYSICAL_REMOTE
        )
    elif variant == "simulation_motion":
        selected_request = request(target=Target.SIMULATION)
    elif variant == "physical_remote_enabled":
        selected_policy = policy(
            physical_actuation_enabled=True,
            remote_physical_actuation_enabled=True,
        )
    elif variant == "safe_disable":
        selected_request = request(action=Action.REQUEST_DISABLE)
    elif variant == "config_activation":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.PHYSICAL_LOCAL,
        )
    elif variant == "firmware_activation":
        selected_identity = identity(role=Role.FIRMWARE_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_FIRMWARE,
            target=Target.PHYSICAL_LOCAL,
        )
    elif variant == "evidence_submit":
        selected_identity = identity(role=Role.EVIDENCE_REVIEWER)
        selected_request = request(
            action=Action.SUBMIT_EVIDENCE, target=Target.OFFLINE
        )
    elif variant == "unauthenticated":
        selected_identity = identity(authenticated=False)
    elif variant == "revoked":
        selected_identity = identity(revoked=True)
    elif variant == "session_not_yet_valid":
        selected_request = request(now_ns=99)
    elif variant == "session_expired":
        selected_request = request(now_ns=1000)
    elif variant == "session_mismatch":
        selected_request = request(session_digest="b" * 64)
    elif variant == "replay":
        selected_request = request(target=Target.SIMULATION)
        replay = True
    elif variant == "role_denied":
        selected_identity = identity(role=Role.DIAGNOSTIC_OPERATOR)
        selected_request = request(target=Target.SIMULATION)
    elif variant == "physical_disabled":
        pass
    elif variant == "remote_physical_disabled":
        selected_policy = policy(physical_actuation_enabled=True)
    elif variant == "remote_admin_disabled":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(action=Action.STAGE_CONFIG)
    elif variant == "local_presence":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.PHYSICAL_LOCAL,
            local_presence_verified=False,
        )
    elif variant == "config_missing":
        selected_request = request(target=Target.SIMULATION, config_digest=ZERO)
    elif variant == "config_mismatch":
        selected_request = request(
            target=Target.SIMULATION, config_digest="b" * 64
        )
    elif variant == "source_missing":
        selected_request = request(
            target=Target.SIMULATION, source_generation_digest=ZERO
        )
    elif variant == "source_mismatch":
        selected_request = request(
            target=Target.SIMULATION, source_generation_digest="b" * 64
        )
    elif variant == "graph_missing":
        selected_request = request(
            target=Target.SIMULATION, graph_generation_digest=ZERO
        )
    elif variant == "graph_mismatch":
        selected_request = request(
            target=Target.SIMULATION, graph_generation_digest="b" * 64
        )
    elif variant == "lease_missing":
        selected_request = request(target=Target.SIMULATION, lease_valid=False)
    elif variant == "safety_missing":
        selected_request = request(
            target=Target.SIMULATION, safety_admission_ready=False
        )
    elif variant == "artifact_integrity":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.STAGE_CONFIG,
            target=Target.OFFLINE,
            artifact_integrity_verified=False,
        )
    elif variant == "rollback_missing":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.OFFLINE,
            rollback_guard_verified=False,
        )
    elif variant == "approval_missing":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.OFFLINE,
            approval=None,
        )
    elif variant == "approval_same_actor":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.OFFLINE,
            approval=approval(actor_digest=ACTOR),
        )
    elif variant == "approval_wrong_role":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.OFFLINE,
            approval=approval(role=Role.SAFETY_OPERATOR),
        )
    elif variant == "approval_scope":
        selected_identity = identity(role=Role.CONFIGURATION_MANAGER)
        selected_request = request(
            action=Action.ACTIVATE_CONFIG,
            target=Target.OFFLINE,
            approval=approval(scope_digest="b" * 64),
        )
    elif variant == "audit_unavailable":
        selected_request = request(target=Target.SIMULATION)
        normal_ready = False
    elif variant == "safe_audit_unavailable":
        selected_request = request(action=Action.REQUEST_DISABLE)
        safe_ready = False
    elif variant == "audit_full":
        selected_identity = identity(role=Role.DIAGNOSTIC_OPERATOR)
        selected_request = request(
            action=Action.READ_STATE,
            target=Target.OFFLINE,
            sequence=2,
        )
        normal_capacity = 1
        prefill = True
    elif variant == "invalid_request":
        selected_identity = identity(authenticated=False)
        selected_request = request(correlation_digest=ZERO)
    else:
        raise AssertionError(f"unknown corpus variant {variant}")

    engine = AuthorizationEngine(
        selected_policy,
        selected_identity,
        normal_audit_capacity=normal_capacity,
        safe_audit_capacity=2,
    )
    engine.set_audit_health(normal_ready=normal_ready, safe_ready=safe_ready)
    if prefill:
        first = engine.authorize(
            request(
                action=Action.READ_STATE,
                target=Target.OFFLINE,
                sequence=1,
            )
        )
        assert first.code == DecisionCode.PASS_TO_NEXT_GATE
    if replay:
        first = engine.authorize(selected_request)
        assert first.code == DecisionCode.PASS_TO_NEXT_GATE
    return engine.authorize(selected_request), engine


class SecurityAuthorizationTests(unittest.TestCase):
    def test_shared_corpus_is_canonical_unique_and_exact(self) -> None:
        rows = FIXTURE.read_text(encoding="utf-8").splitlines()
        self.assertEqual(37, len(rows))
        seen = set()
        for line in rows:
            row = json.loads(line)
            self.assertEqual(
                line,
                json.dumps(row, sort_keys=True, separators=(",", ":")),
            )
            self.assertNotIn(row["case"], seen)
            seen.add(row["case"])
            result, _ = corpus_case(row["variant"])
            self.assertEqual(
                row["expected_code"],
                result.code.name,
                row["case"],
            )
            self.assertFalse(result.motion_authorized)
            self.assertEqual(
                result.proceed_to_next_gate,
                result.code == DecisionCode.PASS_TO_NEXT_GATE,
            )

    def test_closed_role_matrix_has_no_wildcard_or_admin_role(self) -> None:
        expected = {
            Role.OBSERVER: {Action.READ_STATE},
            Role.DIAGNOSTIC_OPERATOR: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
            },
            Role.OPERATOR: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
                Action.SUBMIT_MOTION,
                Action.REQUEST_DISABLE,
            },
            Role.SAFETY_OPERATOR: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
                Action.REQUEST_DISABLE,
                Action.RESET_FAULT,
            },
            Role.CONFIGURATION_MANAGER: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
                Action.STAGE_CONFIG,
                Action.ACTIVATE_CONFIG,
            },
            Role.FIRMWARE_MANAGER: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
                Action.STAGE_FIRMWARE,
                Action.ACTIVATE_FIRMWARE,
            },
            Role.EVIDENCE_REVIEWER: {
                Action.READ_STATE,
                Action.READ_DIAGNOSTICS,
                Action.SUBMIT_EVIDENCE,
            },
        }
        for role in Role:
            for index, action in enumerate(Action, start=1):
                selected_request = request(
                    action=action,
                    target=Target.OFFLINE,
                    sequence=index,
                )
                if action == Action.SUBMIT_MOTION:
                    selected_request = replace(
                        selected_request, target=Target.SIMULATION
                    )
                engine = AuthorizationEngine(policy(), identity(role=role))
                result = engine.authorize(selected_request)
                if action in expected[role]:
                    self.assertNotEqual(
                        DecisionCode.ROLE_ACTION_DENIED,
                        result.code,
                        (role, action),
                    )
                else:
                    self.assertEqual(
                        DecisionCode.ROLE_ACTION_DENIED,
                        result.code,
                        (role, action),
                    )
        self.assertNotIn("ADMIN", {role.name for role in Role})

    def test_denied_fresh_request_consumes_sequence_and_cannot_be_replayed(self) -> None:
        engine = AuthorizationEngine(
            policy(), identity(role=Role.DIAGNOSTIC_OPERATOR)
        )
        denied = engine.authorize(request(target=Target.SIMULATION))
        self.assertEqual(DecisionCode.ROLE_ACTION_DENIED, denied.code)
        self.assertTrue(denied.sequence_committed)
        replayed = engine.authorize(
            request(action=Action.READ_STATE, target=Target.OFFLINE)
        )
        self.assertEqual(DecisionCode.REPLAY_OR_REORDER, replayed.code)
        self.assertFalse(replayed.sequence_committed)

    def test_diagnostics_cannot_exhaust_safe_disable_audit_lane(self) -> None:
        engine = AuthorizationEngine(
            policy(),
            identity(role=Role.OPERATOR),
            normal_audit_capacity=1,
            safe_audit_capacity=2,
        )
        self.assertEqual(
            DecisionCode.PASS_TO_NEXT_GATE,
            engine.authorize(
                request(
                    action=Action.READ_DIAGNOSTICS,
                    target=Target.OFFLINE,
                    sequence=1,
                )
            ).code,
        )
        self.assertEqual(
            DecisionCode.AUDIT_CAPACITY_EXHAUSTED,
            engine.authorize(
                request(
                    action=Action.READ_DIAGNOSTICS,
                    target=Target.OFFLINE,
                    sequence=2,
                )
            ).code,
        )
        for sequence in (3, 4, 5):
            result = engine.authorize(
                request(action=Action.REQUEST_DISABLE, sequence=sequence)
            )
            self.assertEqual(DecisionCode.PASS_TO_NEXT_GATE, result.code)
            self.assertTrue(result.audit_event)
        self.assertEqual(1, len(engine.normal_audit))
        self.assertEqual(2, len(engine.safe_audit))
        self.assertEqual(1, engine.safe_audit_overwrite_count)
        self.assertEqual([4, 5], [event.sequence for event in engine.safe_audit])

    def test_audit_is_context_complete_digest_only_and_secret_free(self) -> None:
        result, engine = corpus_case("config_activation")
        self.assertEqual(DecisionCode.PASS_TO_NEXT_GATE, result.code)
        event = result.audit_event
        self.assertIsNotNone(event)
        assert event is not None
        required = {
            "actor_digest",
            "session_digest",
            "correlation_digest",
            "authentication_context_digest",
            "action",
            "target",
            "role",
            "decision",
            "safety_state",
            "sequence",
            "monotonic_time_ns",
            "config_digest",
            "source_generation_digest",
            "graph_generation_digest",
            "artifact_digest",
            "lease_valid",
            "safety_admission_ready",
        }
        fields = {field.name for field in dataclasses.fields(event)}
        self.assertTrue(required <= fields)
        forbidden_names = ("secret", "password", "credential", "private", "token")
        self.assertFalse(
            any(fragment in name for name in fields for fragment in forbidden_names)
        )
        encoded = json.dumps(dataclasses.asdict(event), sort_keys=True)
        self.assertNotIn("SEEDED-SECRET-MUST-NOT-APPEAR", encoded)
        for field in (
            event.actor_digest,
            event.session_digest,
            event.correlation_digest,
            event.authentication_context_digest,
            event.config_digest,
            event.source_generation_digest,
            event.graph_generation_digest,
            event.artifact_digest,
        ):
            self.assertRegex(field, r"^[0-9a-f]{64}$")
        self.assertEqual(1, len(engine.normal_audit))

    def test_default_policy_denies_physical_motion_but_not_offline_work(self) -> None:
        physical = AuthorizationEngine(policy(), identity()).authorize(request())
        offline = AuthorizationEngine(policy(), identity()).authorize(
            request(target=Target.SIMULATION)
        )
        self.assertEqual(
            DecisionCode.PHYSICAL_ACTUATION_DISABLED, physical.code
        )
        self.assertEqual(DecisionCode.PASS_TO_NEXT_GATE, offline.code)
        self.assertFalse(offline.motion_authorized)

    def test_audit_capacity_configuration_is_bounded(self) -> None:
        for normal_capacity, safe_capacity in ((0, 1), (17, 1), (1, 0), (1, 5)):
            with self.subTest(
                normal_capacity=normal_capacity,
                safe_capacity=safe_capacity,
            ), self.assertRaises(ValueError):
                AuthorizationEngine(
                    policy(),
                    identity(),
                    normal_audit_capacity=normal_capacity,
                    safe_audit_capacity=safe_capacity,
                )


if __name__ == "__main__":
    unittest.main()
