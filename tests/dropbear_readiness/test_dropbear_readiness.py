from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from myactuator_lib.dropbear_readiness import DropbearReadinessError, DropbearReadinessRegistry


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "generated/dropbear_readiness/readiness.json"
SCHEMA = ROOT / "schemas/dropbear-readiness.schema.json"


class DropbearReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(ARTIFACT.read_text())
        cls.schema = json.loads(SCHEMA.read_text())

    def test_baseline_is_exactly_twelve_and_zero_ready(self):
        registry = DropbearReadinessRegistry.load()
        self.assertFalse(registry.motion_enable_allowed)
        self.assertEqual(12, len(self.artifact["actuators"]))
        self.assertEqual(0, self.artifact["summary"]["motion_ready_count"])
        for row in self.artifact["actuators"]:
            decision = registry.decision(row["actuator_id"])
            self.assertFalse(decision.motion_ready)
            self.assertTrue(decision.blockers)

    def test_sources_are_current_hashes_and_config_digest_agrees(self):
        for source in self.artifact["sources"]:
            path = ROOT / source["path"]
            self.assertEqual(source["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        digest = self.artifact["configuration"]["canonical_digest"]
        config = json.loads((ROOT / "schemas/examples/dropbear-observed-incomplete.json").read_text())
        self.assertEqual(config["configuration_integrity"]["digest"], digest)

    def test_every_dependency_is_present_once_and_materializes_nothing(self):
        for row in self.artifact["actuators"]:
            names = [item["dependency"] for item in row["dependencies"]]
            self.assertEqual(13, len(names))
            self.assertEqual(13, len(set(names)))
            material = row["runtime_materialization"]
            self.assertTrue(all(value is None for key, value in material.items() if key != "effective_limit_record_ids"))
            self.assertEqual([], material["effective_limit_record_ids"])

    def test_hip_yaw_preserves_missing_external_feedback(self):
        rows = {row["canonical_joint_name"]: row for row in self.artifact["actuators"]}
        for name in ("left_hip_yaw", "right_hip_yaw"):
            dependency = {item["dependency"]: item for item in rows[name]["dependencies"]}
            self.assertEqual("missing", dependency["external_feedback"]["status"])
            self.assertEqual([], dependency["external_feedback"]["evidence_ids"])
            self.assertIn("external_joint_feedback_missing", rows[name]["blockers"])
        observed = [row for row in rows.values() if {item["dependency"]: item for item in row["dependencies"]}["external_feedback"]["status"] == "unverified_observation"]
        self.assertEqual(10, len(observed))

    def test_unknown_and_family_like_actuator_ids_never_fallback(self):
        registry = DropbearReadinessRegistry.load()
        for value in ("actuator-left", "RMD-X10", "actuator-left-hip", "UNKNOWN"):
            with self.assertRaises(DropbearReadinessError):
                registry.decision(value)

    def test_require_ready_always_returns_ordered_denial(self):
        registry = DropbearReadinessRegistry.load()
        with self.assertRaises(DropbearReadinessError) as caught:
            registry.require_motion_ready("actuator-left-hip-roll")
        self.assertIn("installed_identity_missing", str(caught.exception))
        self.assertIn("hil_evidence_missing", str(caught.exception))

    def test_schema_rejects_route_calibration_limit_policy_and_motion_promotions(self):
        mutations = [
            lambda value: value["actuators"][0].__setitem__("motion_ready", True),
            lambda value: value["actuators"][0]["runtime_materialization"].__setitem__("route", {"node": 1}),
            lambda value: value["actuators"][0]["runtime_materialization"].__setitem__("calibration_record_id", "guessed"),
            lambda value: value["actuators"][0]["runtime_materialization"]["effective_limit_record_ids"].append("guessed"),
            lambda value: value["actuators"][0]["runtime_materialization"].__setitem__("feedback_policy_id", "guessed"),
            lambda value: value["summary"].__setitem__("motion_enable_allowed", True),
        ]
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(self.schema)
        for mutation in mutations:
            value = copy.deepcopy(self.artifact)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))

    def test_consumer_rechecks_source_hashes(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text("{}")
            value = copy.deepcopy(self.artifact)
            value["sources"][0] = {"path": source.relative_to(ROOT).as_posix(), "sha256": "0" * 64}
            with self.assertRaises(DropbearReadinessError) as caught:
                DropbearReadinessRegistry(value, self.schema)
            self.assertIn("source missing or changed", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
