"""Tests for the dependency-free Dropbear configuration semantics."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "schemas" / "validate_dropbear_config.py"
EXAMPLE_PATH = ROOT / "schemas" / "examples" / "dropbear-observed-incomplete.json"
SCHEMA_PATH = ROOT / "schemas" / "dropbear-config.schema.json"

SPEC = importlib.util.spec_from_file_location("dropbear_config_validator", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


class DropbearConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def mutated(self) -> dict:
        return copy.deepcopy(self.example)

    def validate_mutation(self, config: dict):
        VALIDATOR.set_canonical_digest(config)
        return VALIDATOR.validate_config(config)

    @staticmethod
    def codes(issues) -> set[str]:
        return {issue.code for issue in issues}

    def test_schema_declares_draft_2020_12_and_strict_root(self) -> None:
        self.assertEqual(
            self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], "1.0.0")

    def test_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(self.schema)

    def test_observation_example_passes_structural_schema(self) -> None:
        errors = list(Draft202012Validator(self.schema).iter_errors(self.example))
        self.assertEqual(errors, [])

    def test_structural_schema_rejects_missing_required_field(self) -> None:
        config = self.mutated()
        del config["robot"]
        errors = list(Draft202012Validator(self.schema).iter_errors(config))
        self.assertTrue(any(error.validator == "required" for error in errors))

    def test_structural_schema_rejects_additional_property(self) -> None:
        config = self.mutated()
        config["unreviewed_runtime_default"] = True
        errors = list(Draft202012Validator(self.schema).iter_errors(config))
        self.assertTrue(
            any(error.validator == "additionalProperties" for error in errors)
        )

    def test_observation_example_passes_semantic_validation(self) -> None:
        self.assertEqual(VALIDATOR.validate_config(self.example), [])

    def test_example_digest_is_reproducible(self) -> None:
        self.assertEqual(
            self.example["configuration_integrity"]["digest"],
            VALIDATOR.canonical_digest(self.example),
        )

    def test_exact_six_semantic_joints_per_leg(self) -> None:
        by_side = {
            side: {
                joint["semantic_joint"]
                for joint in self.example["joints"]
                if joint["chirality"] == side
            }
            for side in ("left", "right")
        }
        expected = {
            "hip_yaw",
            "hip_roll",
            "hip_pitch",
            "knee",
            "inner_calf",
            "outer_calf",
        }
        self.assertEqual(by_side, {"left": expected, "right": expected})

    def test_five_external_encoders_per_leg_and_missing_hip_yaw(self) -> None:
        encoders = [
            sensor
            for sensor in self.example["sensors"]
            if sensor["sensor_type"] == "external_absolute_encoder"
        ]
        self.assertEqual(
            {side: sum(sensor["canonical_joint_name"].startswith(side) for sensor in encoders)
             for side in ("left", "right")},
            {"left": 5, "right": 5},
        )
        joint_by_name = {
            joint["canonical_name"]: joint for joint in self.example["joints"]
        }
        for side in ("left", "right"):
            feedback = joint_by_name[f"{side}_hip_yaw"]["feedback"]
            self.assertIsNone(feedback["external_sensor_id"])
            self.assertEqual(feedback["external_sensor_status"], "missing")

    def test_legacy_command_identifiers_are_observations_not_node_ids(self) -> None:
        addresses = [actuator["address"] for actuator in self.example["actuators"]]
        self.assertEqual(
            {address["legacy_full_command_can_id"] for address in addresses},
            set(range(0x141, 0x14D)),
        )
        self.assertTrue(all(address["native_node_id"] is None for address in addresses))
        self.assertTrue(
            all(address["status"] == "unverified_observation" for address in addresses)
        )

    def test_exact_tuples_are_unknown_unsupported_and_not_wildcards(self) -> None:
        for actuator in self.example["actuators"]:
            exact_tuple = actuator["exact_tuple"]
            self.assertEqual(exact_tuple["model"], "UNKNOWN")
            self.assertEqual(exact_tuple["drive_firmware"], "UNKNOWN")
            self.assertEqual(exact_tuple["protocol_revision"], "UNKNOWN")
            self.assertEqual(exact_tuple["support_state"], "unsupported")
            self.assertFalse(any("*" in str(value) for value in exact_tuple.values()))

    def test_example_has_no_owner_or_enable_authority(self) -> None:
        self.assertIsNone(self.example["buses"][0]["owner_controller_node_id"])
        self.assertTrue(
            all(
                actuator["owner_controller_node_id"] is None
                for actuator in self.example["actuators"]
            )
        )
        safety = self.example["safety_admission"]
        self.assertFalse(safety["motion_enable_allowed"])
        self.assertIsNone(safety["enable_authority_id"])
        self.assertEqual(safety["enable_authority_status"], "none")

    def test_duplicate_bus_is_rejected(self) -> None:
        config = self.mutated()
        config["buses"].append(copy.deepcopy(config["buses"][0]))
        self.assertIn("E_BUS_ID_DUPLICATE", self.codes(self.validate_mutation(config)))

    def test_duplicate_controller_runtime_node_id_is_rejected(self) -> None:
        config = self.mutated()
        config["controller_nodes"][0]["runtime_node_id"] = 7
        config["controller_nodes"][1]["runtime_node_id"] = 7
        self.assertIn(
            "E_RUNTIME_NODE_ID_DUPLICATE", self.codes(self.validate_mutation(config))
        )

    def test_duplicate_native_node_id_on_bus_is_rejected(self) -> None:
        config = self.mutated()
        config["actuators"][0]["address"]["native_node_id"] = 1
        config["actuators"][1]["address"]["native_node_id"] = 1
        self.assertIn(
            "E_NATIVE_NODE_ID_DUPLICATE", self.codes(self.validate_mutation(config))
        )

    def test_actuator_owner_must_match_bus_owner(self) -> None:
        config = self.mutated()
        config["buses"][0]["owner_controller_node_id"] = (
            "left-gateway-role-observation"
        )
        config["actuators"][0]["owner_controller_node_id"] = (
            "right-gateway-role-observation"
        )
        self.assertIn(
            "E_ACTUATOR_OWNER_MISMATCH", self.codes(self.validate_mutation(config))
        )

    def test_noncanonical_joint_name_is_rejected(self) -> None:
        config = self.mutated()
        config["joints"][0]["canonical_name"] = "left_yaw"
        codes = self.codes(self.validate_mutation(config))
        self.assertIn("E_CANONICAL_JOINT_SET", codes)
        self.assertIn("E_CANONICAL_JOINT_FORM", codes)

    def test_alias_field_inside_joint_is_rejected(self) -> None:
        config = self.mutated()
        config["joints"][0]["aliases"] = ["left-yaw"]
        self.assertIn(
            "E_ALIAS_OUTSIDE_BOUNDARY", self.codes(self.validate_mutation(config))
        )

    def test_wildcard_exact_tuple_is_rejected(self) -> None:
        config = self.mutated()
        config["actuators"][0]["exact_tuple"]["model"] = "RMD-*"
        self.assertIn("E_TUPLE_WILDCARD", self.codes(self.validate_mutation(config)))

    def test_unknown_tuple_cannot_claim_support(self) -> None:
        config = self.mutated()
        config["actuators"][0]["exact_tuple"]["support_state"] = "catalogued"
        self.assertIn(
            "E_UNKNOWN_TUPLE_SUPPORTED", self.codes(self.validate_mutation(config))
        )

    def test_incomplete_configuration_cannot_be_enableable(self) -> None:
        config = self.mutated()
        config["safety_admission"]["motion_enable_allowed"] = True
        config["safety_admission"]["enable_authority_id"] = "unsafe-test-authority"
        config["safety_admission"]["enable_authority_status"] = "verified"
        config["safety_admission"]["independent_power_removal_status"] = "verified"
        config["safety_admission"]["blockers"] = []
        issues = self.validate_mutation(config)
        self.assertIn("E_ENABLE_INCOMPLETE", self.codes(issues))
        message = next(
            issue.message for issue in issues if issue.code == "E_ENABLE_INCOMPLETE"
        )
        self.assertIn("exact tuple is incomplete", message)
        self.assertIn("ownership is not verified", message)

    def test_tampered_content_fails_digest(self) -> None:
        config = self.mutated()
        config["robot"]["hardware_revision"] = "tampered"
        self.assertIn("E_CONFIG_DIGEST", self.codes(VALIDATOR.validate_config(config)))

    def test_unknown_provenance_reference_is_rejected(self) -> None:
        config = self.mutated()
        config["robot"]["source_refs"].append("missing-source")
        self.assertIn("E_SOURCE_REFERENCE", self.codes(self.validate_mutation(config)))


if __name__ == "__main__":
    unittest.main()
