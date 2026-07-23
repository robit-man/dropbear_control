from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from typing import Dict, Tuple

from myactuator_lib import hostlink_v1 as hostlink
from myactuator_lib import rmd_v44 as v44
from myactuator_lib import rmd_v44_emulator as emulator


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = Path(os.environ["STACK_V1_GATEWAY_BRIDGE"])
SESSION = 0x11223344
FRAME_TIME_NS = 1_000_000
LEASE_EXPIRY_NS = 100_000_000
SYNTHETIC_HASH = bytes.fromhex("33" * 32)
SYNTHETIC_CONFIG = hostlink.ConfigIdentity(
    "synthetic-v44-node1", "1", SYNTHETIC_HASH
)


def command_frame(config: hostlink.ConfigIdentity, actuator: str) -> bytes:
    command = hostlink.Command(
        actuator,
        config,
        "synthetic-controller",
        "synthetic-offline-lease",
        "synthetic-controller",
        3,
        LEASE_EXPIRY_NS,
        hostlink.CommandMode.CURRENT_Q,
        True,
        current_q_a=1.25,
    )
    return hostlink.encode_message(
        command,
        session_id=SESSION,
        sequence=3,
        monotonic_ns=FRAME_TIME_NS,
        config_sha256=config.sha256,
    )


def parse_fields(line: str) -> Tuple[str, Dict[str, str]]:
    parts = line.strip().split()
    if not parts:
        raise AssertionError("bridge returned an empty line")
    values = {}
    for item in parts[1:]:
        key, value = item.split("=", 1)
        values[key] = value
    return parts[0], values


class BridgeProcess:
    def __init__(self, mode: str, frame: bytes) -> None:
        self.process = subprocess.Popen(
            [str(BRIDGE), mode],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert self.process.stdin is not None
        self.process.stdin.write(f"FRAME {frame.hex()}\n")
        self.process.stdin.flush()

    def read(self) -> Tuple[str, Dict[str, str]]:
        assert self.process.stdout is not None
        return parse_fields(self.process.stdout.readline())

    def send(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def finish(self) -> None:
        stdout, stderr = self.process.communicate(timeout=5)
        if self.process.returncode != 0:
            raise AssertionError(
                f"bridge failed rc={self.process.returncode} "
                f"stdout={stdout!r} stderr={stderr!r}"
            )


def tx_frame(values: Dict[str, str]) -> v44.CanFrame:
    return v44.CanFrame(int(values["arbitration"]), bytes.fromhex(values["data"]))


def make_emulator() -> emulator.RmdV44Emulator:
    return emulator.RmdV44Emulator(
        [
            emulator.NodeState(
                1,
                disabled=False,
                iq_raw=-17,
                output_speed_raw=23,
                output_angle_raw=-41,
            )
        ],
        response_deadline_us=20_000,
        capability_policy=emulator.CapabilityPolicy.allow_explicit(
            motion=[v44.Command.IQ_CONTROL]
        ),
        admission_callback=lambda _context: True,
    )


def start_positive() -> Tuple[BridgeProcess, Dict[str, str], v44.CanFrame]:
    bridge = BridgeProcess(
        "positive", command_frame(SYNTHETIC_CONFIG, "synthetic-actuator-node1")
    )
    label, values = bridge.read()
    if label != "TX":
        bridge.finish()
        raise AssertionError(f"expected TX, received {label} {values}")
    return bridge, values, tx_frame(values)


def send_response(
    bridge: BridgeProcess, values: Dict[str, str], delivery: emulator.Delivery, at_ms: int
) -> Dict[str, str]:
    bridge.send(
        f"RX {at_ms} {values['bus']} {delivery.frame.arbitration_id} "
        f"{delivery.frame.data.hex()}"
    )
    label, result = bridge.read()
    if label != "RESULT":
        raise AssertionError(f"expected RESULT, received {label} {result}")
    bridge.finish()
    return result


class StackV1GatewayTests(unittest.TestCase):
    def test_synthetic_v1_current_reaches_emulator_and_correlates_response(self) -> None:
        bridge, values, native = start_positive()
        self.assertEqual(native, v44.encode_iq_control_raw(1, 125))
        instance = make_emulator()
        submission = instance.submit(native)
        self.assertTrue(submission.accepted, submission.reason)
        deliveries = instance.poll()
        self.assertEqual(len(deliveries), 1)
        result = send_response(bridge, values, deliveries[0], 2)
        self.assertEqual(result["response"], "OK")
        self.assertEqual(result["observation"], "OK")
        self.assertEqual(
            {key: int(result[key]) for key in (
                "received", "admitted", "native_tx", "native_response", "observed", "rejected"
            )},
            {
                "received": 1,
                "admitted": 1,
                "native_tx": 1,
                "native_response": 1,
                "observed": 1,
                "rejected": 0,
            },
        )
        state = instance.state(1)
        self.assertEqual(state.last_iq_command_raw, 125)
        self.assertEqual(state.iq_raw, -17)
        self.assertEqual(state.output_speed_raw, 23)
        self.assertEqual(state.output_angle_raw, -41)
        self.assertFalse(instance.is_physical_plant)
        self.assertFalse(instance.model_firmware_applicability_verified)

    def test_tracked_dropbear_config_is_link_typed_but_cannot_reach_native_tx(self) -> None:
        manifest = json.loads(
            (ROOT / "generated/dropbear/manifest.json").read_text(encoding="utf-8")
        )
        registry = json.loads(
            (ROOT / "generated/dropbear/host/dropbear_config.json").read_text(
                encoding="utf-8"
            )
        )["registry"]
        identity = manifest["generated_identity"]
        self.assertFalse(registry["safety_admission"]["motion_enable_allowed"])
        self.assertTrue(
            all(item["address"]["native_node_id"] is None for item in registry["actuators"])
        )
        config = hostlink.ConfigIdentity(
            identity["configuration_id"],
            str(identity["configuration_revision"]),
            bytes.fromhex(identity["canonical_digest"]),
        )
        bridge = BridgeProcess(
            "tracked", command_frame(config, "actuator-left-knee")
        )
        label, result = bridge.read()
        bridge.finish()
        self.assertEqual(label, "TRACKED")
        self.assertEqual(result["link"], "1")
        self.assertEqual(result["motion_allowed"], "0")
        self.assertEqual(result["config"], "MOTION_NOT_ALLOWED")
        self.assertEqual(result["native_node_bound"], "0")
        self.assertEqual(result["native_tx"], "0")

    def test_emulator_response_drop_becomes_native_timeout_not_execution_claim(self) -> None:
        bridge, _values, native = start_positive()
        instance = make_emulator()
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=v44.Command.IQ_CONTROL,
                drop_response=True,
            )
        )
        self.assertTrue(instance.submit(native).accepted)
        self.assertEqual(instance.poll(), ())
        bridge.send("EXPIRE 21")
        label, result = bridge.read()
        bridge.finish()
        self.assertEqual(label, "RESULT")
        self.assertEqual(result["expire"], "1")
        self.assertEqual(result["native_response"], "0")
        self.assertEqual(result["observed"], "0")
        self.assertEqual(result["rejected"], "1")

    def test_emulator_late_response_is_rejected_at_native_deadline(self) -> None:
        bridge, values, native = start_positive()
        instance = make_emulator()
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=v44.Command.IQ_CONTROL,
                extra_delay_us=30_000,
            )
        )
        self.assertTrue(instance.submit(native).accepted)
        deliveries = instance.advance_to(30_000)
        self.assertEqual(deliveries, ())
        self.assertIn(
            "response_deadline_missed", [event.kind for event in instance.events()]
        )
        bridge.send("EXPIRE 21")
        label, result = bridge.read()
        bridge.finish()
        self.assertEqual(label, "RESULT")
        self.assertEqual(result["expire"], "1")
        self.assertEqual(result["native_response"], "0")
        self.assertEqual(result["observed"], "0")

    def test_emulator_unexpected_node_preserves_pending_correlation(self) -> None:
        bridge, values, native = start_positive()
        instance = make_emulator()
        wrong = v44.CanFrame(0x242, bytes.fromhex("a1197b0000000000"))
        v44.decode_response(wrong, expected_motor_id=2, expected_command=0xA1)
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=v44.Command.IQ_CONTROL,
                unexpected_response=wrong,
            )
        )
        self.assertTrue(instance.submit(native).accepted)
        deliveries = instance.poll()
        self.assertEqual(len(deliveries), 1)
        result = send_response(bridge, values, deliveries[0], 2)
        self.assertEqual(result["response"], "RESPONSE_UNEXPECTED_NODE")
        self.assertEqual(result["native_response"], "0")
        self.assertEqual(result["observed"], "0")
        self.assertEqual(result["outstanding"], "1")

    def test_emulator_drive_fault_is_protocol_state_not_plant_evidence(self) -> None:
        bridge, values, native = start_positive()
        instance = make_emulator()
        instance.queue_scenario(
            emulator.ResponseScenario(
                motor_id=1,
                command=v44.Command.IQ_CONTROL,
                drive_error_mask=0x0004,
                drive_disables=True,
            )
        )
        self.assertTrue(instance.submit(native).accepted)
        state = instance.state(1)
        self.assertEqual(state.error_mask, 0x0004)
        self.assertTrue(state.disabled)
        self.assertIn("drive_fault_injected", [event.kind for event in instance.events()])
        deliveries = instance.poll()
        result = send_response(bridge, values, deliveries[0], 2)
        self.assertEqual(result["response"], "OK")
        self.assertEqual(result["observation"], "OK")
        self.assertFalse(instance.is_physical_plant)


if __name__ == "__main__":
    unittest.main()
