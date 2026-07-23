from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from myactuator_lib.dropbear_source_authority import (
    DropbearSourceAuthorityStatus,
    SourceAuthorityAdmissionError,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_dropbear_source_authority.py"
INVENTORY_PATH = ROOT / "generated/dropbear_description/inventory.json"
STATUS_PATH = ROOT / "generated/dropbear_source_authority/status.json"
STATUS_SCHEMA = json.loads(
    (ROOT / "schemas/dropbear-source-authority-status.schema.json").read_text()
)

spec = importlib.util.spec_from_file_location(
    "dropbear_source_authority_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class DropbearSourceAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = manager.inventory()
        cls.template = manager.template()
        cls.files = {
            record["path"]: record for record in cls.inventory["files"]
        }

    def file(self, suffix: str):
        matches = [
            record
            for record in self.inventory["files"]
            if record["package_family"] == "gazebo_dropbear"
            and record["classification"] == "source_candidate"
            and record["path"].endswith(suffix)
        ]
        self.assertEqual(1, len(matches), suffix)
        return matches[0]

    def accepted_fixture(self):
        decision = copy.deepcopy(self.template)
        decision["record_state"] = "submitted"
        decision["reviewer"] = {
            "reviewer_id": "independent-human-test-fixture",
            "organization_or_team": "external-test-fixture-team",
            "independence_attested": True,
            "reviewed_at": "2026-07-23T07:00:00Z",
            "review_assertion": (
                "Synthetic unit-test decision; not a project source review."
            ),
            "signature_evidence_refs": [
                "tests/dropbear_source_authority/synthetic-reviewer"
            ],
        }
        decision["disposition"] = "accept_selection"
        decision["family_policy"] = {
            "mode": "single_family",
            "primary_family": "gazebo_dropbear",
            "rationale": "Synthetic test-only single-family policy.",
            "evidence_refs": [
                "tests/dropbear_source_authority/synthetic-family-policy"
            ],
        }
        role_paths = {
            "kinematic_tree": "urdf/gazebo/dropbear_gz.urdf.xacro",
            "visual_geometry": "urdf/gazebo/leg.xacro",
            "collision_geometry": "urdf/gazebo/leg.xacro",
            "inertial_properties": "urdf/gazebo/leg.xacro",
            "ros2_control": "urdf/ros2_control/dropbear.ros2_control.xacro",
            "gazebo_constraints": "urdf/gazebo/leg.xacro",
            "controller_configuration": "config/controllers.yaml",
        }
        for role in decision["role_decisions"]:
            source = self.file(role_paths[role["role"]])
            role["status"] = "selected"
            role["selected_files"] = [manager.selection_from_file(source)]
            role["rationale"] = f"Synthetic selection for {role['role']}."
            role["evidence_refs"] = [
                "tests/dropbear_source_authority/synthetic-role-selection"
            ]
        selected_by_key = {}
        for role in decision["role_decisions"]:
            for selected in role["selected_files"]:
                selected_by_key.setdefault(selected["logical_key"], set()).add(
                    selected["git_object_id"]
                )
        for divergence in decision["divergence_decisions"]:
            selected = sorted(selected_by_key.get(divergence["logical_key"], set()))
            divergence["selected_git_object_ids"] = selected
            divergence["disposition"] = (
                "select_object"
                if len(selected) == 1
                else "select_multiple_with_roles"
                if len(selected) > 1
                else "not_in_selected_scope"
            )
            divergence["rationale"] = "Synthetic divergence disposition."
            divergence["evidence_refs"] = [
                "tests/dropbear_source_authority/synthetic-divergence"
            ]
        decision["decision_complete"] = True
        decision["runtime_description_complete"] = True
        manager.set_digest(decision)
        return decision

    def test_generated_template_is_exact_unanswered_and_digest_bound(self):
        manager.validate_decision(copy.deepcopy(self.template), self.inventory)
        template_path = (
            ROOT
            / "generated/dropbear_source_authority/templates"
            / f"{self.template['decision_id']}.json"
        )
        self.assertEqual(self.template, json.loads(template_path.read_text()))
        self.assertEqual(7, len(self.template["role_decisions"]))
        self.assertEqual(29, len(self.template["divergence_decisions"]))
        self.assertTrue(
            all(row["status"] == "unanswered" for row in self.template["role_decisions"])
        )
        self.assertFalse(self.template["decision_complete"])
        self.assertFalse(self.template["runtime_description_complete"])
        self.assertFalse(self.template["support_granted"])
        self.assertFalse(self.template["physical_motion_authority"])

    def test_status_is_hash_bound_zero_accepted_and_motion_false(self):
        status = json.loads(STATUS_PATH.read_text())
        self.assertEqual(
            status["source"]["inventory_sha256"],
            hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(0, status["summary"]["submitted_decision_count"])
        self.assertEqual(0, status["summary"]["accepted_decision_count"])
        self.assertEqual(0, status["summary"]["runtime_complete_decision_count"])
        self.assertFalse(status["summary"]["source_authority_selected"])
        self.assertFalse(status["summary"]["support_granted"])
        self.assertFalse(status["summary"]["physical_motion_authority"])
        self.assertEqual([], status["accepted_decision_ids"])

    def test_complete_synthetic_human_fixture_validates_without_becoming_project_evidence(self):
        decision = self.accepted_fixture()
        manager.validate_decision(decision, self.inventory)
        self.assertTrue(decision["decision_complete"])
        self.assertTrue(decision["runtime_description_complete"])
        tracked_status = json.loads(STATUS_PATH.read_text())
        self.assertEqual(0, tracked_status["summary"]["accepted_decision_count"])

    def test_derivative_path_cannot_be_smuggled_as_primary_source(self):
        decision = self.accepted_fixture()
        install = next(
            record for record in self.inventory["files"]
            if record["classification"] == "install_derivative"
            and record["description_kind"] == "controller_yaml"
        )
        selection = decision["role_decisions"][-1]["selected_files"][0]
        selection.update(
            {
                "path": install["path"],
                "git_object_id": install["git_object_id"],
                "sha256": install["sha256"],
                "size_bytes": install["size_bytes"],
                "logical_key": install["logical_key"],
                "package_family": install["package_family"],
            }
        )
        manager.set_digest(decision)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(decision, self.inventory)

    def test_every_selected_identity_field_is_exact(self):
        base = self.accepted_fixture()
        mutations = [
            ("git_object_id", "0" * 40),
            ("sha256", "0" * 64),
            ("size_bytes", 0),
            ("logical_key", "urdf/guessed.xacro"),
            ("package_family", "cad_detailed"),
        ]
        for field, value in mutations:
            decision = copy.deepcopy(base)
            decision["role_decisions"][0]["selected_files"][0][field] = value
            manager.set_digest(decision)
            with self.assertRaises(manager.SourceAuthorityError, msg=field):
                manager.validate_decision(decision, self.inventory)

    def test_expanded_urdf_requires_exact_generator_lineage(self):
        decision = self.accepted_fixture()
        expanded = next(
            record for record in self.inventory["files"]
            if record["package_family"] == "gazebo_dropbear"
            and record["classification"] == "expanded_generated_candidate"
        )
        decision["role_decisions"][0]["selected_files"] = [
            manager.selection_from_file(expanded)
        ]
        manager.set_digest(decision)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(decision, self.inventory)

    def test_all_roles_and_divergent_groups_must_be_decided(self):
        unanswered_role = self.accepted_fixture()
        role = unanswered_role["role_decisions"][0]
        role.update(
            {
                "status": "unanswered",
                "selected_files": [],
                "rationale": None,
                "evidence_refs": [],
            }
        )
        manager.set_digest(unanswered_role)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(unanswered_role, self.inventory)

        unanswered_divergence = self.accepted_fixture()
        row = unanswered_divergence["divergence_decisions"][0]
        row.update(
            {
                "disposition": "unanswered",
                "selected_git_object_ids": [],
                "rationale": None,
                "evidence_refs": [],
            }
        )
        manager.set_digest(unanswered_divergence)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(unanswered_divergence, self.inventory)

    def test_unavailable_role_can_complete_review_but_not_runtime_description(self):
        decision = self.accepted_fixture()
        role = next(
            row for row in decision["role_decisions"]
            if row["role"] == "inertial_properties"
        )
        role.update(
            {
                "status": "unavailable",
                "selected_files": [],
                "unavailability_reason": "Synthetic fixture has no accepted inertial source.",
                "rationale": "Keep runtime description incomplete.",
                "evidence_refs": [
                    "tests/dropbear_source_authority/synthetic-unavailable"
                ],
            }
        )
        decision["runtime_description_complete"] = False
        manager.set_digest(decision)
        manager.validate_decision(decision, self.inventory)

    def test_automation_nonindependence_and_non_utc_review_deny(self):
        mutations = [
            lambda value: value["reviewer"].__setitem__(
                "reviewer_id", "codex-automated-reviewer"
            ),
            lambda value: value["reviewer"].__setitem__(
                "independence_attested", False
            ),
            lambda value: value["reviewer"].__setitem__(
                "reviewed_at", "2026-07-23T07:00:00-07:00"
            ),
            lambda value: value["reviewer"].__setitem__(
                "signature_evidence_refs", []
            ),
        ]
        for mutation in mutations:
            decision = self.accepted_fixture()
            mutation(decision)
            manager.set_digest(decision)
            with self.assertRaises(manager.SourceAuthorityError):
                manager.validate_decision(decision, self.inventory)

    def test_digest_subject_and_inventory_drift_deny(self):
        digest = self.accepted_fixture()
        digest["integrity"]["record_sha256"] = "0" * 64
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(digest, self.inventory)
        subject = self.accepted_fixture()
        subject["subject"]["repository_tree_id"] = "0" * 40
        manager.set_digest(subject)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(subject, self.inventory)

    def test_schemas_reject_support_motion_status_or_unknown_promotions(self):
        status = json.loads(STATUS_PATH.read_text())
        mutations = [
            lambda value: value["summary"].__setitem__("accepted_decision_count", 1),
            lambda value: value["summary"].__setitem__("source_authority_selected", True),
            lambda value: value["summary"].__setitem__("support_granted", True),
            lambda value: value["summary"].__setitem__("physical_motion_authority", True),
            lambda value: value["accepted_decision_ids"].append(
                self.template["decision_id"]
            ),
        ]
        validator = Draft202012Validator(STATUS_SCHEMA)
        for mutation in mutations:
            value = copy.deepcopy(status)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))
        decision = self.accepted_fixture()
        decision["support_granted"] = True
        manager.set_digest(decision)
        with self.assertRaises(manager.SourceAuthorityError):
            manager.validate_decision(decision, self.inventory)

    def test_cli_check_is_read_only_and_canonical(self):
        before = STATUS_PATH.read_bytes()
        result = subprocess.run(
            ["python3", str(TOOL), "--check"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIn("submitted=0 accepted=0", result.stdout)
        self.assertEqual(before, STATUS_PATH.read_bytes())
        self.assertEqual(
            before,
            manager.canonical_bytes(json.loads(before)),
        )

    def test_host_consumer_rechecks_sources_and_exposes_no_selected_path(self):
        status = DropbearSourceAuthorityStatus.load()
        self.assertFalse(status.source_authority_selected)
        self.assertFalse(status.physical_motion_authority)
        for role in manager.ROLES:
            decision = status.decision(role)
            self.assertFalse(decision.selected)
            self.assertEqual((), decision.selected_paths)
            self.assertTrue(decision.blockers)
            with self.assertRaises(SourceAuthorityAdmissionError):
                status.require_selected(role)

    def test_host_consumer_has_no_role_family_prefix_or_case_fallback(self):
        status = DropbearSourceAuthorityStatus.load()
        for role in (
            "kinematic",
            "KINEMATIC_TREE",
            "gazebo",
            "controller",
            "urdf",
            "",
        ):
            with self.assertRaises(SourceAuthorityAdmissionError):
                status.decision(role)

    def test_host_consumer_rechecks_template_hash_and_draft_state(self):
        status_value = json.loads(STATUS_PATH.read_text())
        changed_hash = copy.deepcopy(status_value)
        changed_hash["template"]["sha256"] = "0" * 64
        with self.assertRaises(SourceAuthorityAdmissionError):
            DropbearSourceAuthorityStatus(changed_hash, STATUS_SCHEMA)

        promoted = copy.deepcopy(self.template)
        promoted["record_state"] = "submitted"
        manager.set_digest(promoted)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            fake_root = Path(temporary)
            inventory_path = (
                fake_root / status_value["source"]["inventory_path"]
            )
            template_path = fake_root / status_value["template"]["path"]
            inventory_path.parent.mkdir(parents=True)
            template_path.parent.mkdir(parents=True)
            inventory_path.write_bytes(INVENTORY_PATH.read_bytes())
            template_path.write_bytes(manager.canonical_bytes(promoted))
            changed = copy.deepcopy(status_value)
            changed["template"]["sha256"] = hashlib.sha256(
                template_path.read_bytes()
            ).hexdigest()
            with self.assertRaises(SourceAuthorityAdmissionError):
                DropbearSourceAuthorityStatus(changed, STATUS_SCHEMA, fake_root)


if __name__ == "__main__":
    unittest.main()
