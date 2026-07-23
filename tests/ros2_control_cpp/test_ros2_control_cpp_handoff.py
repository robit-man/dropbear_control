from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from myactuator_lib import dropbear_hardware_api as hardware
from myactuator_lib import ros2_control_core as core
from tests.ros2_control_core.test_ros2_control_core import (
    CATALOG,
    GRAPH,
    NOW,
    SOURCE,
    Fixture,
    lease,
    present,
    absent,
    sample,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ros2_control/myactuator_dropbear_hardware"
LOCK = ROOT / "tools/ros2-cpp-environment-lock.json"
LOCK_SCHEMA = ROOT / "schemas/ros2-cpp-environment-lock.schema.json"


def operation(name: str, result: core.OperationResult, state: core.ControlLifecycle) -> str:
    return f"{name}:{result.disposition.value}:{state.value}"


def python_parity_lines() -> list[str]:
    lines = [
        "descriptor_fields="
        + ",".join(core.SystemInterfaceDescriptor.__dataclass_fields__),
        "joint_fields="
        + ",".join(core.JointInterfaceDescriptor.__dataclass_fields__),
    ]

    fixture = Fixture()
    lifecycle = []
    result = fixture.configure()
    lifecycle.append(operation("configure", result, fixture.core.state))
    result = fixture.core.activate(lease())
    lifecycle.append(operation("activate", result, fixture.core.state))
    result = fixture.core.deactivate()
    lifecycle.append(operation("deactivate", result, fixture.core.state))
    result = fixture.core.cleanup()
    lifecycle.append(operation("cleanup", result, fixture.core.state))
    result = fixture.core.shutdown()
    lifecycle.append(operation("shutdown", result, fixture.core.state))
    lines.append("lifecycle=" + ";".join(lifecycle))

    fixture = Fixture()
    assert fixture.activate().succeeded
    command = (
        core.JointCommandValue(
            "left-knee", core.CommandInterface.POSITION, 0.25
        ),
    )
    stale = dataclasses.replace(
        fixture.batch(command),
        simulator_catalog_generation_sha256="0" * 64,
    )
    timeout = dataclasses.replace(
        fixture.batch(command),
        issued_monotonic_ns=NOW - 10,
        deadline_monotonic_ns=NOW,
    )
    invalid = fixture.batch(
        (
            core.JointCommandValue(
                "left-knee", core.CommandInterface.POSITION, 2.0
            ),
        )
    )
    outcomes = (
        ("stale", fixture.core.write(stale)),
        ("timeout", fixture.core.write(timeout)),
        ("limit", fixture.core.write(invalid)),
        ("success", fixture.core.write(fixture.batch(command))),
        ("replay", fixture.core.write(fixture.batch(command))),
    )
    lines.append(
        "write="
        + ";".join(
            f"{label}:{result.disposition.value}" for label, result in outcomes
        )
    )

    fixture = Fixture()
    assert fixture.activate().succeeded
    fixture.backend.states["actuator-left-knee"] = sample(
        position_rad=present(
            0.1,
            hardware.SignalSource.EXTERNAL_JOINT_SENSOR,
            hardware.SignalValidity.STALE,
        ),
        velocity_rad_s=present(
            0.2,
            hardware.SignalSource.REVIEWED_FUSION,
        ),
        output_effort_nm=absent(hardware.SignalValidity.FAULTED),
        qaxis_current_a=present(
            0.3,
            hardware.SignalSource.NATIVE_DRIVE,
        ),
    )
    read = fixture.core.read()
    state_items = []
    for interface, item in read.states[0].interfaces:
        value = "null" if item.value is None else f"{item.value:.6f}"
        state_items.append(
            f"{interface.value}:{value}:{item.validity.value}:{item.source.value}"
        )
    lines.append(
        f"read={read.disposition.value};" + ";".join(state_items)
    )

    fixture = Fixture()
    assert fixture.activate().succeeded
    fixture.generations[0] = "9" * 64
    revoked = fixture.core.read()
    lines.append(
        f"revocation={revoked.disposition.value}:{fixture.core.state.value}"
    )
    return lines


class Ros2ControlCppHandoffTests(unittest.TestCase):
    def test_native_parity_output_matches_live_python_core(self) -> None:
        executable = os.environ.get("MYACTUATOR_CPP_PARITY_BIN")
        self.assertIsNotNone(executable)
        completed = subprocess.run(
            [str(executable), "--emit-parity"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            python_parity_lines(),
            completed.stdout.strip().splitlines(),
        )

    def test_plugin_has_no_transport_or_native_command_escape_surface(self) -> None:
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                list((PACKAGE / "include").rglob("*.hpp"))
                + list((PACKAGE / "src").rglob("*.cpp"))
            )
        ).lower()
        for forbidden in (
            "can_id",
            "motor_id",
            "opcode",
            "native_bytes",
            "raw_command",
            "serial_port",
            "twai.h",
            "socketcan",
        ):
            self.assertNotIn(forbidden, sources)
        self.assertNotIn("firmware/esp32", sources)
        self.assertIn("unavailablesessionport", sources)

    def test_invalid_states_render_nan_never_zero_fill(self) -> None:
        plugin = (PACKAGE / "src/system_interface.cpp").read_text(encoding="utf-8")
        self.assertIn("item.second.validity == SignalValidity::VALID", plugin)
        self.assertIn("quiet_NaN()", plugin)
        self.assertNotIn("item.second.value.value_or(0", plugin)

    def test_plugin_manifest_and_package_surface_are_exact(self) -> None:
        manifest = (
            PACKAGE / "myactuator_dropbear_hardware.xml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'base_class_type="hardware_interface::SystemInterface"',
            manifest,
        )
        self.assertIn(
            "myactuator_dropbear_hardware::DropbearSystemInterface",
            manifest,
        )
        package = (PACKAGE / "package.xml").read_text(encoding="utf-8")
        for dependency in (
            "hardware_interface",
            "pluginlib",
            "rclcpp",
            "rclcpp_lifecycle",
        ):
            self.assertIn(f"<depend>{dependency}</depend>", package)
        documentation = (
            ROOT / "docs/MYACTUATOR_ROS2_CONTROL_HANDOFF.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "myactuator_dropbear_hardware/DropbearSystemInterface",
            documentation,
        )
        self.assertIn("runtime result is denial", documentation)
        public_report = (
            ROOT
            / "generated/myactuator/ros2_control_cpp_handoff/report.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn(str(ROOT), public_report)
        self.assertNotIn("/home/", public_report)

    def test_environment_lock_is_closed_and_nonphysical(self) -> None:
        value = json.loads(LOCK.read_text(encoding="utf-8"))
        schema = json.loads(LOCK_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(value)
        self.assertTrue(value["claims"]["cpp_handoff_build_environment"])
        for claim in (
            "physical_adapter_present",
            "canonical_dropbear_admitted",
            "support_granted",
            "physical_motion_authority",
            "physical_io",
        ):
            self.assertFalse(value["claims"][claim])
        self.assertEqual(9, len(value["debian_packages"]))
        self.assertEqual(4, len(value["abi_artifacts"]))
        self.assertEqual(3, len(value["api_headers"]))

    def test_environment_lock_rejects_unknown_fields_and_promotions(self) -> None:
        value = json.loads(LOCK.read_text(encoding="utf-8"))
        schema = json.loads(LOCK_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        unknown = dict(value)
        unknown["unreviewed"] = True
        self.assertTrue(list(validator.iter_errors(unknown)))
        promoted = json.loads(json.dumps(value))
        promoted["claims"]["physical_motion_authority"] = True
        self.assertTrue(list(validator.iter_errors(promoted)))


if __name__ == "__main__":
    unittest.main()
