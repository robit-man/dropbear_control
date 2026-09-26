from __future__ import annotations

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_ROOT))

from hardware_service import (  # noqa: E402
    HardwareObservationManager,
    ObservationParseError,
    parse_firmware_calibration_line,
    parse_firmware_configuration_line,
)
from firmware_service import DeviceFirmwareManager, FirmwareToolError  # noqa: E402


class _MaintenanceObservation:
    def __init__(self, capabilities=("config-records-v1", "calibration-result-v1")):
        self.capabilities = list(capabilities)
        self.configuration_timestamp = 1
        self.calibration_timestamp = 0
        self.guarded_commands = []

    def snapshot(self):
        return {"sides": {"left": {
            "configuredPath": "/dev/test-left",
            "firmware": {"capabilities": self.capabilities},
            "health": {"runtimeReady": True},
            "configuration": {
                "updatedMonotonicNs": self.configuration_timestamp,
                "completeMonotonicNs": self.configuration_timestamp,
                "meta": {"rebootRequired": False},
                "constraints": {name: {"min": -10, "max": 10} for name in (
                    "outer_calf", "inner_calf", "knee", "hip_pitch", "hip_yaw", "hip_roll"
                )},
            },
            "calibration": ({
                "updatedMonotonicNs": self.calibration_timestamp,
                "status": "ok",
                "kind": "offsets",
                "values": {"outer_calf": 1, "inner_calf": 2, "hip_pitch": 3, "knee": 4, "hip_roll": 5},
            } if self.calibration_timestamp else {}),
        }}}

    def send_diagnostic(self, side, command):
        if command == "config show":
            self.configuration_timestamp += 1
        return {"sent": True, "side": side, "command": command, "bytes": len(command)}

    def send_guarded_command(self, side, command):
        self.guarded_commands.append(command)
        if command == "calibrate save":
            self.calibration_timestamp += 1
        return {"sent": True, "side": side, "command": command, "bytes": len(command)}


class HardwareConfigurationProtocolTests(unittest.TestCase):
    def test_configuration_records_are_bounded_and_accumulate(self):
        records = (
            "DBCFG1,LEFTLEG,meta,1,standalone,3.000,0,0,0,behemoth-33",
            "DBCFG1,LEFTLEG,hyperspawn,250,0,0,1.000000",
            "DBCFG1,LEFTLEG,offsets,1,2,3,4,5",
            "DBCFG1,LEFTLEG,directions,1.0,-1.0,1.0,-1.0,1.0",
            "DBCFG1,LEFTLEG,constraint,outer_calf,-30,210",
            "DBCFG1,LEFTLEG,constraint,inner_calf,-30,210",
            "DBCFG1,LEFTLEG,constraint,knee,0,180",
            "DBCFG1,LEFTLEG,constraint,hip_pitch,-90,90",
            "DBCFG1,LEFTLEG,constraint,hip_yaw,-90,90",
            "DBCFG1,LEFTLEG,constraint,hip_roll,-45,45",
            "DBCFG1,LEFTLEG,end",
        )
        manager = HardwareObservationManager(enabled=False)
        for sequence, record in enumerate(records, 1):
            self.assertLessEqual(len(record.encode("ascii")), 256)
            self.assertTrue(manager.ingest_line("left", record, sequence))
        configuration = manager.snapshot()["sides"]["left"]["configuration"]
        self.assertEqual(configuration["meta"]["firmwareVersion"], "behemoth-33")
        self.assertEqual(configuration["offsets"]["hip_pitch"], 3)
        self.assertEqual(configuration["directions"]["knee"], 1.0)
        self.assertEqual(configuration["constraints"]["hip_roll"], {"min": -45, "max": 45})
        self.assertEqual(configuration["completeMonotonicNs"], len(records))

    def test_configuration_role_mismatch_is_rejected(self):
        with self.assertRaises(ObservationParseError):
            parse_firmware_configuration_line(
                "left", "DBCFG1,RIGHTLEG,offsets,1,2,3,4,5"
            )

    def test_calibration_result_is_structured(self):
        result = parse_firmware_calibration_line(
            "right", "DBCAL1,RIGHTLEG,ok,offsets,-1,-2,-3,-4,-5"
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["values"]["knee"], -4)

    def test_diagnostic_and_guarded_allowlists_remain_non_motion(self):
        writes: list[bytes] = []
        manager = HardwareObservationManager(
            left_path="/dev/test-left",
            enabled=True,
            diagnostic_writer=lambda _path, data: writes.append(data) or len(data),
        )
        manager.send_diagnostic("left", "can info 0x141")
        manager.send_guarded_command("left", "config set offset knee -12")
        self.assertEqual(writes[0], b"<DB1:LEFTLEG> can info 0x141\n")
        self.assertEqual(writes[1], b"<DB1:LEFTLEG> config set offset knee -12\n")
        manager.send_diagnostic("left", "can info 0x14b")
        self.assertEqual(writes[2], b"<DB1:LEFTLEG> can info 0x14b\n")
        manager.send_diagnostic("left", "can poll off")
        manager.send_diagnostic("left", "can registers")
        manager.send_diagnostic("left", "can poll on")
        self.assertEqual(writes[3], b"<DB1:LEFTLEG> can poll off\n")
        self.assertEqual(writes[4], b"<DB1:LEFTLEG> can registers\n")
        self.assertEqual(writes[5], b"<DB1:LEFTLEG> can poll on\n")
        with self.assertRaises(ValueError):
            manager.send_diagnostic("left", "can info 0x140")
        with self.assertRaises(ValueError):
            manager.send_diagnostic("left", "can info 0x161")
        with self.assertRaises(ValueError):
            manager.send_guarded_command("left", "torque knee 10")
        with self.assertRaises(ValueError):
            manager.send_guarded_command("left", "direction right_knee +")
        with self.assertRaises(ValueError):
            manager.send_diagnostic("left", "torque knee 1")

    def test_grouped_observation_commands_are_uart_paced(self):
        writes: list[bytes] = []
        manager = HardwareObservationManager(
            left_path="/dev/test-left",
            enabled=True,
            diagnostic_writer=lambda _path, data: writes.append(data) or len(data),
        )
        manager._states["left"].command_protocol = "DB1"
        with mock.patch("hardware_service.time.sleep") as sleep:
            result = manager.request_observation_stream(True)
        self.assertTrue(result["sides"]["left"]["ok"])
        self.assertEqual(writes[:3], [
            b"<DB1:LEFTLEG> version\n",
            b"<DB1:LEFTLEG> health\n",
            b"<DB1:LEFTLEG> observe on\n",
        ])
        self.assertGreaterEqual(sleep.call_args_list.count(mock.call(0.08)), 2)

    def test_host_configuration_route_translates_only_structured_settings(self):
        observation = _MaintenanceObservation()
        with tempfile.TemporaryDirectory() as directory:
            manager = DeviceFirmwareManager(Path(directory), observation)
            manager._device = lambda _device_id: {
                "id": "left-device", "role": "left", "connected": True,
                "stablePath": "/dev/test-left",
            }
            base = {
                "deviceId": "left-device",
                "robotSupported": True,
                "estopReady": True,
                "limitsReviewed": True,
                "confirmation": "APPLY LEFT CONFIG",
            }
            result = manager.configure({**base, "setting": "direction", "joint": "knee", "value": "-"})
            self.assertEqual(observation.guarded_commands, ["direction left_knee -"])
            self.assertEqual(result["schema"], "dropbear-leg-configuration-v1")
            with self.assertRaises(FirmwareToolError):
                manager.configure({**base, "setting": "torque", "joint": "knee", "value": 10})

    def test_calibration_requires_new_protocol_and_returns_saved_offsets(self):
        observation = _MaintenanceObservation()
        with tempfile.TemporaryDirectory() as directory:
            manager = DeviceFirmwareManager(Path(directory), observation)
            manager._device = lambda _device_id: {
                "id": "left-device", "role": "left", "connected": True,
                "stablePath": "/dev/test-left",
            }
            result = manager.calibrate({
                "deviceId": "left-device",
                "robotSupported": True,
                "areaClear": True,
                "estopReady": True,
                "confirmation": "CALIBRATE LEFT",
            })
            self.assertTrue(result["saved"])
            self.assertEqual(observation.guarded_commands, ["calibrate save"])

            observation.capabilities = []
            with self.assertRaisesRegex(FirmwareToolError, "calibration-result-v1"):
                manager.calibrate({
                    "deviceId": "left-device",
                    "robotSupported": True,
                    "areaClear": True,
                    "estopReady": True,
                    "confirmation": "CALIBRATE LEFT",
                })


if __name__ == "__main__":
    unittest.main()
