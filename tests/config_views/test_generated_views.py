"""Integration tests for deterministic canonical Dropbear projections."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_dropbear_views.py"
CONFIG = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
SCHEMA = ROOT / "schemas/dropbear-config.schema.json"
TRACKED = ROOT / "generated/dropbear"
JSON_VIEWS = ("host", "ui", "simulator")


def canonical_digest(config: dict) -> str:
    value = copy.deepcopy(config)
    value["configuration_integrity"].pop("digest", None)
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tree_bytes(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class GeneratedViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.json_views = {
            kind: json.loads(
                (TRACKED / kind / "dropbear_config.json").read_text(encoding="utf-8")
            )
            for kind in JSON_VIEWS
        }
        cls.ros_view = yaml.safe_load(
            (TRACKED / "ros/dropbear_config.yaml").read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            (TRACKED / "manifest.json").read_text(encoding="utf-8")
        )

    def run_generator(
        self,
        output: Path,
        *,
        config: Path = CONFIG,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(TOOL),
            "--config",
            str(config),
            "--schema",
            str(SCHEMA),
            "--output-dir",
            str(output),
        ]
        if check:
            command.append("--check")
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_tracked_views_pass_check_mode(self) -> None:
        result = self.run_generator(TRACKED, check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"action": "checked"', result.stdout)

    def test_all_views_have_identical_generated_identity(self) -> None:
        identities = [
            view["generated_identity"] for view in self.json_views.values()
        ]
        identities.extend(
            [self.ros_view["generated_identity"], self.manifest["generated_identity"]]
        )
        self.assertTrue(all(identity == identities[0] for identity in identities))
        identity = identities[0]
        self.assertEqual(identity["schema_version"], self.config["schema_version"])
        self.assertEqual(identity["configuration_id"], self.config["configuration_id"])
        self.assertEqual(
            identity["configuration_revision"], self.config["configuration_revision"]
        )
        self.assertEqual(
            identity["configuration_state"], self.config["configuration_state"]
        )
        self.assertEqual(
            identity["canonical_digest"],
            self.config["configuration_integrity"]["digest"],
        )
        self.assertEqual(identity["tool"]["tool_id"], "generate-dropbear-views")
        self.assertEqual(identity["tool"]["tool_version"], "1.0.0")

    def test_json_and_ros_views_losslessly_preserve_registry(self) -> None:
        for kind, view in self.json_views.items():
            with self.subTest(kind=kind):
                self.assertEqual(view["registry"], self.config)
                self.assertEqual(view["view_kind"], kind)
        self.assertEqual(self.ros_view["registry"], self.config)
        self.assertEqual(self.ros_view["view_kind"], "ros")

    def test_json_views_and_manifest_are_canonical_json(self) -> None:
        paths = [
            TRACKED / kind / "dropbear_config.json" for kind in JSON_VIEWS
        ] + [TRACKED / "manifest.json"]
        for path in paths:
            with self.subTest(path=path):
                value = json.loads(path.read_text(encoding="utf-8"))
                expected = (
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                self.assertEqual(path.read_bytes(), expected)

    def test_unknown_and_non_enableable_values_are_preserved(self) -> None:
        for view in [*self.json_views.values(), self.ros_view]:
            registry = view["registry"]
            self.assertEqual(registry["configuration_state"], "incomplete_observation")
            self.assertFalse(registry["safety_admission"]["motion_enable_allowed"])
            self.assertIsNone(registry["safety_admission"]["enable_authority_id"])
            self.assertEqual(registry["safety_admission"]["enable_authority_status"], "none")
            self.assertTrue(
                all(bus["owner_controller_node_id"] is None for bus in registry["buses"])
            )
            for actuator in registry["actuators"]:
                self.assertIsNone(actuator["owner_controller_node_id"])
                self.assertIsNone(actuator["address"]["native_node_id"])
                self.assertEqual(actuator["exact_tuple"]["model"], "UNKNOWN")
                self.assertEqual(
                    actuator["exact_tuple"]["drive_firmware"], "UNKNOWN"
                )
                self.assertEqual(
                    actuator["exact_tuple"]["support_state"], "unsupported"
                )
            for joint in registry["joints"]:
                self.assertIsNone(joint["actuation"]["motor_to_joint_sign"])
                self.assertIsNone(joint["actuation"]["output_per_motor_ratio"])
                self.assertTrue(
                    all(
                        joint["actuation"]["limits"][field] is None
                        for field in (
                            "position_lower_rad",
                            "position_upper_rad",
                            "max_velocity_rad_s",
                            "max_qaxis_current_a",
                            "max_effort_nm",
                            "max_temperature_c",
                        )
                    )
                )
                self.assertIsNone(joint["calibration_id"])
                self.assertIsNone(joint["cad_binding"]["asset_id"])

    def test_manifest_hashes_every_non_manifest_artifact(self) -> None:
        declared = {
            item["path"]: item for item in self.manifest["artifacts"]
        }
        actual_paths = {
            path.relative_to(TRACKED).as_posix()
            for path in TRACKED.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        self.assertEqual(set(declared), actual_paths)
        for relative_path, record in declared.items():
            content = (TRACKED / relative_path).read_bytes()
            self.assertEqual(record["bytes"], len(content))
            self.assertEqual(record["sha256"], hashlib.sha256(content).hexdigest())

    def test_firmware_header_has_identity_and_disabled_static_assert(self) -> None:
        header = (TRACKED / "firmware/dropbear_config.generated.hpp").read_text(
            encoding="utf-8"
        )
        identity = self.manifest["generated_identity"]
        expected_pairs = {
            "kSchemaVersion": identity["schema_version"],
            "kConfigurationId": identity["configuration_id"],
            "kConfigurationState": identity["configuration_state"],
            "kCanonicalDigest": identity["canonical_digest"],
            "kGeneratorId": identity["tool"]["tool_id"],
            "kGeneratorVersion": identity["tool"]["tool_version"],
        }
        for constant, value in expected_pairs.items():
            self.assertRegex(
                header,
                rf"{constant}\s*=\s*{re.escape(json.dumps(value))};",
            )
        self.assertIn("kMotionEnableAllowed = false;", header)
        self.assertIn("static_assert(!kMotionEnableAllowed", header)

    def test_firmware_view_compiles_and_links_as_cxx17(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            main = temporary_path / "main.cpp"
            executable = temporary_path / "generated-config-test"
            main.write_text(
                """#include \"dropbear_config.generated.hpp\"\n
int main() {
  using namespace myactuator::generated::dropbear;
  return kMotionEnableAllowed || kJoints.size() != 12U ||
                 kActuators.size() != 12U || kCanonicalRegistryJsonSize == 0U
             ? 1
             : 0;
}
""",
                encoding="utf-8",
            )
            command = [
                "g++",
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(TRACKED / "firmware"),
                str(TRACKED / "firmware/dropbear_config.generated.cpp"),
                str(main),
                "-o",
                str(executable),
            ]
            compile_result = subprocess.run(
                command, text=True, capture_output=True, check=False
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [str(executable)], text=True, capture_output=True, check=False
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)

    def test_generation_is_reproducible_across_output_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first_result = self.run_generator(first)
            second_result = self.run_generator(second)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(tree_bytes(first), tree_bytes(second))

    def test_check_mode_does_not_rewrite_matching_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            self.assertEqual(self.run_generator(output).returncode, 0)
            before = {
                path: (content, (output / path).stat().st_mtime_ns)
                for path, content in tree_bytes(output).items()
            }
            result = self.run_generator(output, check=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            after = {
                path: (content, (output / path).stat().st_mtime_ns)
                for path, content in tree_bytes(output).items()
            }
            self.assertEqual(after, before)

    def test_check_detects_mismatch_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            self.assertEqual(self.run_generator(output).returncode, 0)
            target = output / "host/dropbear_config.json"
            target.write_bytes(target.read_bytes() + b"tamper\n")
            before = target.read_bytes()
            result = self.run_generator(output, check=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("mismatch: host/dropbear_config.json", result.stderr)
            self.assertEqual(target.read_bytes(), before)

    def test_atomic_replace_removes_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            self.assertEqual(self.run_generator(output).returncode, 0)
            stale = output / "stale-runtime-default.txt"
            stale.write_text("must disappear", encoding="utf-8")
            result = self.run_generator(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(stale.exists())
            self.assertEqual(tree_bytes(output), tree_bytes(TRACKED))

    def test_digest_tamper_is_rejected_before_existing_output_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            self.assertEqual(self.run_generator(output).returncode, 0)
            before = tree_bytes(output)
            tampered = copy.deepcopy(self.config)
            tampered["robot"]["hardware_revision"] = "tampered-without-rehash"
            config_path = root / "tampered.json"
            config_path.write_text(json.dumps(tampered), encoding="utf-8")
            result = self.run_generator(output, config=config_path)
            self.assertEqual(result.returncode, 2)
            self.assertIn("E_CONFIG_DIGEST", result.stderr)
            self.assertEqual(tree_bytes(output), before)

    def test_structurally_invalid_config_is_rejected_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            malformed = copy.deepcopy(self.config)
            del malformed["actuators"]
            config_path = root / "missing-actuators.json"
            config_path.write_text(json.dumps(malformed), encoding="utf-8")
            output = root / "output"
            result = self.run_generator(output, config=config_path)
            self.assertEqual(result.returncode, 2)
            self.assertIn("structural validation failed", result.stderr)
            self.assertFalse(output.exists())

    def test_incomplete_config_cannot_generate_as_enableable_even_if_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unsafe = copy.deepcopy(self.config)
            unsafe["configuration_state"] = "complete_verified"
            unsafe["safety_admission"].update(
                {
                    "motion_enable_allowed": True,
                    "enable_authority_id": "invented-authority",
                    "enable_authority_status": "verified",
                    "independent_power_removal_status": "verified",
                    "blockers": [],
                }
            )
            unsafe["configuration_integrity"]["digest"] = canonical_digest(unsafe)
            config_path = root / "unsafe-but-rehashed.json"
            config_path.write_text(json.dumps(unsafe), encoding="utf-8")
            output = root / "output"
            result = self.run_generator(output, config=config_path)
            self.assertEqual(result.returncode, 2)
            self.assertIn("E_ENABLE_INCOMPLETE", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
