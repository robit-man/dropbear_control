from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
SCHEMA_PATH = ROOT / "schemas/dropbear-reconciliation.schema.json"
CONFIG_PATH = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
DROPBEAR_REPO = ROOT / "references/Dropbear"

EXPECTED_ADDRESSES = {
    "left_outer_calf": 0x141,
    "left_inner_calf": 0x142,
    "right_inner_calf": 0x143,
    "right_outer_calf": 0x144,
    "left_knee": 0x145,
    "left_hip_pitch": 0x146,
    "right_hip_pitch": 0x147,
    "right_knee": 0x148,
    "left_hip_yaw": 0x149,
    "left_hip_roll": 0x14A,
    "right_hip_roll": 0x14B,
    "right_hip_yaw": 0x14C,
}

EXPECTED_LAYERS = [
    "high_level_intent",
    "ros_trajectory_demo",
    "ros2_control_gazebo",
    "production_host_api",
    "host_link_v1",
    "session_gateway",
    "can_adapter",
    "native_actuator_protocol",
    "joint_observation",
    "state_estimator",
]


class DropbearReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(cls.schema)

    def assert_invalid(self, mutation) -> None:
        candidate = copy.deepcopy(self.artifact)
        mutation(candidate)
        self.assertTrue(list(self.validator.iter_errors(candidate)))

    def test_schema_accepts_checked_in_artifact(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual([], list(self.validator.iter_errors(self.artifact)))

    def test_source_hashes_are_bound_to_pinned_git_objects(self) -> None:
        generated = self.artifact["generated_from"]
        head = subprocess.check_output(
            ["git", "-C", str(DROPBEAR_REPO), "rev-parse", "HEAD"], text=True
        ).strip()
        self.assertEqual(generated["dropbear_repository_commit"], head)
        source_ids = set()
        for source in generated["source_files"]:
            source_ids.add(source["source_id"])
            raw = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(DROPBEAR_REPO),
                    "show",
                    f"{head}:{source['path']}",
                ]
            )
            self.assertEqual(source["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(source["authority"], "upstream_observation_only")
        self.assertEqual(7, len(source_ids))

    def test_canonical_config_identity_and_motion_denial_are_unchanged(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        generated = self.artifact["generated_from"]
        self.assertEqual(config["configuration_id"], generated["canonical_configuration_id"])
        self.assertEqual(config["configuration_revision"], generated["canonical_configuration_revision"])
        self.assertEqual(config["configuration_integrity"]["digest"], generated["canonical_configuration_digest"])
        self.assertFalse(config["safety_admission"]["motion_enable_allowed"])
        self.assertFalse(self.artifact["summary"]["motion_enable_allowed"])
        self.assertFalse(self.artifact["admission"]["motion_enable_allowed"])

    def test_cardinalities_preserve_gaps_instead_of_filling_them(self) -> None:
        summary = self.artifact["summary"]
        self.assertEqual(12, summary["canonical_actuator_count"])
        self.assertEqual(12, summary["low_level_command_address_observation_count"])
        self.assertEqual(10, summary["external_sensor_observation_count"])
        self.assertEqual(10, summary["ros_leg_command_joint_count"])
        for key in (
            "evidence_backed_ros_actuator_mapping_count",
            "installed_identity_count",
            "runtime_route_count",
            "valid_calibration_count",
            "accepted_cad_binding_count",
            "physical_hardware_plugin_count",
        ):
            self.assertEqual(0, summary[key])

    def test_legacy_addresses_are_observations_not_routes(self) -> None:
        actuators = {row["canonical_joint_name"]: row for row in self.artifact["actuators"]}
        self.assertEqual(set(EXPECTED_ADDRESSES), set(actuators))
        self.assertEqual(12, len({row["actuator_id"] for row in actuators.values()}))
        for name, expected_address in EXPECTED_ADDRESSES.items():
            row = actuators[name]
            observed = row["low_level_observation"]
            self.assertEqual(expected_address, observed["legacy_request_arbitration_id"])
            self.assertEqual(expected_address - 0x140, observed["arithmetic_candidate_node_id"])
            self.assertFalse(observed["candidate_is_installed_route"])
            self.assertEqual("unresolved", row["route"]["status"])
            self.assertIsNone(row["route"]["native_node_id"])
            self.assertIsNone(row["route"]["owner_controller_node_id"])
            self.assertTrue(all(value is None for key, value in row["installed_identity"].items() if key != "status"))

    def test_no_ros_mapping_is_guessed(self) -> None:
        expected = {
            "left": ["LL_hip_joint", "LL_knee_actuator_joint", "LL_Revolute67", "LL_Revolute81", "LL_Revolute88"],
            "right": ["RL_hip_joint", "RL_knee_actuator_joint", "RL_Revolute67", "RL_Revolute81", "RL_Revolute88"],
        }
        self.assertEqual(expected, {group["chirality"]: group["joint_ids"] for group in self.artifact["ros_leg_groups"]})
        for group in self.artifact["ros_leg_groups"]:
            self.assertEqual([], group["canonical_actuator_ids"])
            self.assertEqual("unresolved_no_guess", group["mapping_status"])
            self.assertTrue(group["open_loop_control"])
            self.assertEqual(10, group["controller_manager_rate_hz"])
            self.assertFalse(group["physical_hardware_plugin_present"])
        for actuator in self.artifact["actuators"]:
            self.assertEqual([], actuator["ros_joint_ids"])
            self.assertEqual("unresolved_no_guess", actuator["mapping_status"])

    def test_feedback_and_readiness_remain_explicit(self) -> None:
        rows = {row["canonical_joint_name"]: row for row in self.artifact["actuators"]}
        external = [row for row in rows.values() if row["feedback"]["external_sensor_id"] is not None]
        self.assertEqual(10, len(external))
        for name in ("left_hip_yaw", "right_hip_yaw"):
            self.assertIsNone(rows[name]["feedback"]["external_sensor_id"])
            self.assertIn("external_joint_feedback_missing", rows[name]["blockers"])
        for row in rows.values():
            self.assertFalse(row["motion_ready"])
            self.assertEqual("missing", row["calibration"]["status"])
            self.assertEqual("missing", row["limit_provenance"]["status"])
            self.assertEqual("unknown", row["cad_binding"]["status"])
            self.assertGreaterEqual(len(row["blockers"]), 8)

    def test_layer_chain_has_no_motion_authority_or_unblocked_bypass(self) -> None:
        layers = self.artifact["layer_interfaces"]
        self.assertEqual(EXPECTED_LAYERS, [layer["layer_id"] for layer in layers])
        for layer in layers:
            self.assertFalse(layer["physical_motion_authority"])
            self.assertTrue(layer["blockers"])

    def test_conflict_sources_resolve_to_provenance_records(self) -> None:
        source_ids = {row["source_id"] for row in self.artifact["generated_from"]["source_files"]}
        conflict_ids = set()
        for conflict in self.artifact["conflicts"]:
            conflict_ids.add(conflict["conflict_id"])
            self.assertTrue(set(conflict["source_ids"]).issubset(source_ids))
        self.assertEqual(len(conflict_ids), len(self.artifact["conflicts"]))
        self.assertIn("actuator-ros-cardinality", conflict_ids)
        self.assertIn("legacy-address-not-route", conflict_ids)

    def test_schema_rejects_every_unsafe_promotion(self) -> None:
        self.assert_invalid(lambda value: value["summary"].__setitem__("motion_enable_allowed", True))
        self.assert_invalid(lambda value: value["actuators"][0]["route"].__setitem__("native_node_id", 1))
        self.assert_invalid(lambda value: value["actuators"][0]["installed_identity"].__setitem__("model", "RMD-X10"))
        self.assert_invalid(lambda value: value["actuators"][0]["ros_joint_ids"].append("LL_hip_joint"))
        self.assert_invalid(lambda value: value["ros_leg_groups"][0]["canonical_actuator_ids"].append("actuator-left-hip-yaw"))
        self.assert_invalid(lambda value: value["layer_interfaces"][0].__setitem__("physical_motion_authority", True))
        self.assert_invalid(lambda value: value["actuators"][0]["calibration"].__setitem__("motor_to_joint_sign", 1))


if __name__ == "__main__":
    unittest.main()
