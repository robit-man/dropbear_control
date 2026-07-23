from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from myactuator_lib.dropbear_source_registry_v2 import (
    DropbearSourceRegistryV2,
    SourceRegistryAdmissionError,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_dropbear_source_registry_v2.py"
V1_TOOL = ROOT / "tools/manage_dropbear_source_authority.py"
REGISTRY_PATH = ROOT / "generated/dropbear_source_registry_v2/registry.json"
REGISTRY_SCHEMA = json.loads(
    (
        ROOT
        / "schemas/dropbear-source-authority-registry-v2.schema.json"
    ).read_text()
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


manager = load_module("dropbear_source_registry_v2_test_module", TOOL)
v1 = load_module("dropbear_source_registry_v2_v1_test_module", V1_TOOL)


class DropbearSourceRegistryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = v1.inventory()
        cls.files = cls.inventory["files"]

    def source_file(self, suffix: str):
        matches = [
            record
            for record in self.files
            if record["package_family"] == "gazebo_dropbear"
            and record["classification"] == "source_candidate"
            and record["path"].endswith(suffix)
        ]
        self.assertEqual(1, len(matches), suffix)
        return matches[0]

    def accepted_decision(self, marker: str = "one"):
        decision = v1.template()
        decision["record_state"] = "submitted"
        decision["reviewer"] = {
            "reviewer_id": f"source-reviewer-{marker}",
            "organization_or_team": "independent-source-review-team",
            "independence_attested": True,
            "reviewed_at": "2026-07-23T12:00:00Z",
            "review_assertion": f"Synthetic V2 lifecycle decision {marker}.",
            "signature_evidence_refs": [
                f"tests/dropbear_source_registry_v2/reviewer-{marker}"
            ],
        }
        decision["disposition"] = "accept_selection"
        decision["family_policy"] = {
            "mode": "single_family",
            "primary_family": "gazebo_dropbear",
            "rationale": f"Synthetic family policy {marker}.",
            "evidence_refs": [
                f"tests/dropbear_source_registry_v2/family-{marker}"
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
            source = self.source_file(role_paths[role["role"]])
            role.update(
                status="selected",
                selected_files=[v1.selection_from_file(source)],
                rationale=f"Synthetic {role['role']} selection {marker}.",
                evidence_refs=[
                    f"tests/dropbear_source_registry_v2/role-{marker}"
                ],
            )
        selected_by_key: dict[str, set[str]] = {}
        for role in decision["role_decisions"]:
            for selected in role["selected_files"]:
                selected_by_key.setdefault(selected["logical_key"], set()).add(
                    selected["git_object_id"]
                )
        for row in decision["divergence_decisions"]:
            selected = sorted(selected_by_key.get(row["logical_key"], set()))
            row.update(
                selected_git_object_ids=selected,
                disposition=(
                    "select_object"
                    if len(selected) == 1
                    else "select_multiple_with_roles"
                    if len(selected) > 1
                    else "not_in_selected_scope"
                ),
                rationale=f"Synthetic divergence {marker}.",
                evidence_refs=[
                    f"tests/dropbear_source_registry_v2/divergence-{marker}"
                ],
            )
        decision["decision_complete"] = True
        decision["runtime_description_complete"] = True
        v1.set_digest(decision)
        v1.validate_decision(decision)
        return decision

    def envelope(
        self,
        marker: str = "one",
        *,
        submitted_at: str = "2026-07-23T12:10:00Z",
        supersedes: str | None = None,
    ):
        decision = self.accepted_decision(marker)
        value = {
            "schema_version": "dropbear-source-authority-submission/2",
            "submission_id": "sourcesubmission-" + "0" * 20,
            "submitted_at": submitted_at,
            "submitter": {
                "actor_id": f"source-submitter-{marker}",
                "organization_or_team": "source-submission-team",
                "human_attested": True,
            },
            "supersedes_submission_id": supersedes,
            "decision_sha256": manager.sha_bytes(
                manager.canonical_bytes(decision)
            ),
            "decision": decision,
            "submission_reason": f"Synthetic lifecycle submission {marker}.",
            "evidence_refs": [
                f"tests/dropbear_source_registry_v2/submission-{marker}"
            ],
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["submission_id"] = manager.expected_submission_id(value)
        manager.set_digest(value)
        manager.validate_submission(value)
        return value

    def event(
        self,
        envelope,
        event_type: str,
        sequence: int,
        approved_at: str,
        *,
        replacement=None,
        approver: str | None = None,
    ):
        prior, next_state = manager.TRANSITIONS[event_type]
        value = {
            "schema_version": "dropbear-source-authority-event/2",
            "event_id": "sourceevent-" + "0" * 20,
            "sequence": sequence,
            "event_type": event_type,
            "subject": {
                "submission_id": envelope["submission_id"],
                "submission_sha256": manager.sha_bytes(
                    manager.canonical_bytes(envelope)
                ),
                "decision_id": envelope["decision"]["decision_id"],
                "decision_sha256": envelope["decision_sha256"],
                "superseding_submission_id": (
                    replacement["submission_id"] if replacement else None
                ),
                "superseding_submission_sha256": (
                    manager.sha_bytes(manager.canonical_bytes(replacement))
                    if replacement
                    else None
                ),
            },
            "transition": {
                "prior_state": prior,
                "next_state": next_state,
            },
            "approver": {
                "approver_id": approver or f"governance-approver-{sequence}",
                "organization_or_team": "independent-governance-team",
                "human_attested": True,
                "independence_attested": True,
                "governance_authority_attested": True,
                "approved_at": approved_at,
                "approval_assertion": f"Synthetic {event_type} approval.",
                "signature_evidence_refs": [
                    f"tests/dropbear_source_registry_v2/approval-{sequence}"
                ],
            },
            "reason": f"Synthetic {event_type} lifecycle test.",
            "evidence_refs": [
                f"tests/dropbear_source_registry_v2/event-{sequence}"
            ],
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["event_id"] = manager.expected_event_id(value)
        manager.set_digest(value)
        manager.validate_event(value)
        return value

    def write_case(self, directory: Path, envelopes, events):
        decisions = directory / "decisions"
        event_dir = directory / "events"
        decisions.mkdir()
        event_dir.mkdir()
        for envelope in envelopes:
            (
                decisions / f"{envelope['submission_id']}.json"
            ).write_bytes(manager.canonical_bytes(envelope))
        for event in events:
            (
                event_dir
                / f"{event['sequence']:06d}-{event['event_id']}.json"
            ).write_bytes(manager.canonical_bytes(event))
        return decisions, event_dir

    def consumer(self, registry, envelopes, events):
        return DropbearSourceRegistryV2(
            registry,
            REGISTRY_SCHEMA,
            json.loads(
                (
                    ROOT
                    / "schemas/dropbear-source-authority-submission-v2.schema.json"
                ).read_text()
            ),
            json.loads(
                (
                    ROOT
                    / "schemas/dropbear-source-authority-event-v2.schema.json"
                ).read_text()
            ),
            manager.INVENTORY.read_bytes(),
            manager.V1_STATUS.read_bytes(),
            {
                row["submission_path"]: manager.canonical_bytes(envelope)
                for row, envelope in zip(registry["submissions"], sorted(
                    envelopes, key=lambda item: item["submission_id"]
                ))
            },
            {
                row["event_path"]: manager.canonical_bytes(event)
                for row, event in zip(registry["events"], events)
            },
        )

    def test_tracked_registry_is_canonical_empty_and_denial_only(self):
        value = manager.build()
        manager.validate_registry(value)
        self.assertEqual(value, json.loads(REGISTRY_PATH.read_text()))
        self.assertEqual([], value["submissions"])
        self.assertEqual([], value["events"])
        self.assertIsNone(value["active_submission_id"])
        self.assertEqual(0, value["summary"]["accepted_count"])
        self.assertFalse(value["summary"]["source_authority_selected"])
        self.assertFalse(value["support_granted"])
        self.assertFalse(value["physical_motion_authority"])
        consumer = DropbearSourceRegistryV2.load()
        self.assertFalse(consumer.source_authority_selected)
        with self.assertRaises(SourceRegistryAdmissionError):
            consumer.require_active()

    def test_valid_submission_without_event_stays_submitted_and_inactive(self):
        envelope = self.envelope()
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], []
            )
            registry = manager.build(decisions, events)
        self.assertEqual(1, registry["summary"]["submitted_count"])
        self.assertEqual(0, registry["summary"]["accepted_count"])
        self.assertIsNone(registry["active_submission_id"])

    def test_accept_event_selects_one_runtime_complete_source_only(self):
        envelope = self.envelope()
        accept = self.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], [accept]
            )
            registry = manager.build(decisions, events)
        self.assertEqual(envelope["submission_id"], registry["active_submission_id"])
        self.assertEqual(1, registry["summary"]["accepted_count"])
        self.assertTrue(registry["summary"]["source_authority_selected"])
        self.assertEqual([], registry["blockers"])
        self.assertFalse(registry["support_granted"])
        self.assertFalse(registry["physical_motion_authority"])
        self.assertEqual(0, manager.build()["summary"]["accepted_count"])
        consumer = self.consumer(registry, [envelope], [accept])
        authority = consumer.require_active(role="kinematic_tree")
        self.assertEqual(envelope["submission_id"], authority.submission_id)
        self.assertTrue(
            authority.selected_paths("kinematic_tree")[0].endswith(
                "dropbear_gz.urdf.xacro"
            )
        )
        self.assertFalse(authority.support_granted)
        self.assertFalse(authority.physical_motion_authority)

    def test_reject_event_is_terminal_and_never_active(self):
        envelope = self.envelope()
        reject = self.event(
            envelope, "reject", 1, "2026-07-23T12:20:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], [reject]
            )
            registry = manager.build(decisions, events)
        self.assertEqual(1, registry["summary"]["rejected_count"])
        self.assertEqual(0, registry["summary"]["accepted_count"])
        self.assertIsNone(registry["active_submission_id"])

    def test_accept_then_revoke_removes_authority_deterministically(self):
        envelope = self.envelope()
        events_value = [
            self.event(envelope, "accept", 1, "2026-07-23T12:20:00Z"),
            self.event(envelope, "revoke", 2, "2026-07-23T12:30:00Z"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], events_value
            )
            first = manager.build(decisions, events)
            second = manager.build(decisions, events)
        self.assertEqual(first, second)
        self.assertEqual(1, first["summary"]["revoked_count"])
        self.assertEqual(0, first["summary"]["accepted_count"])
        self.assertIsNone(first["active_submission_id"])
        consumer = self.consumer(first, [envelope], events_value)
        self.assertEqual(
            "revoked",
            consumer.entry(envelope["submission_id"]).lifecycle_state,
        )
        with self.assertRaises(SourceRegistryAdmissionError):
            consumer.require_active()

    def test_atomic_supersede_replaces_active_submission_without_overlap(self):
        old = self.envelope("old", submitted_at="2026-07-23T12:10:00Z")
        replacement = self.envelope(
            "new",
            submitted_at="2026-07-23T12:25:00Z",
            supersedes=old["submission_id"],
        )
        events_value = [
            self.event(old, "accept", 1, "2026-07-23T12:20:00Z"),
            self.event(
                old,
                "supersede",
                2,
                "2026-07-23T12:30:00Z",
                replacement=replacement,
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [old, replacement], events_value
            )
            registry = manager.build(decisions, events)
        states = {
            row["submission_id"]: row for row in registry["submissions"]
        }
        self.assertEqual("superseded", states[old["submission_id"]]["lifecycle_state"])
        self.assertEqual(
            replacement["submission_id"],
            states[old["submission_id"]]["superseded_by_submission_id"],
        )
        self.assertEqual(
            "accepted",
            states[replacement["submission_id"]]["lifecycle_state"],
        )
        self.assertEqual(replacement["submission_id"], registry["active_submission_id"])
        self.assertEqual(1, registry["summary"]["accepted_count"])
        consumer = self.consumer(registry, [old, replacement], events_value)
        self.assertEqual(
            replacement["submission_id"],
            consumer.require_active().submission_id,
        )
        self.assertEqual(
            "superseded",
            consumer.entry(old["submission_id"]).lifecycle_state,
        )

    def test_host_consumer_denies_stale_generation_unknown_role_and_unknown_entry(self):
        envelope = self.envelope()
        accept = self.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], [accept]
            )
            registry = manager.build(decisions, events)
        consumer = self.consumer(registry, [envelope], [accept])
        with self.assertRaises(SourceRegistryAdmissionError):
            consumer.require_active(registry_generation_sha256="0" * 64)
        with self.assertRaises(SourceRegistryAdmissionError):
            consumer.require_active(role="inferred_role")
        with self.assertRaises(SourceRegistryAdmissionError):
            consumer.entry("sourcesubmission-" + "0" * 20)

    def test_host_consumer_denies_registry_submission_event_and_source_tamper(self):
        envelope = self.envelope()
        accept = self.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], [accept]
            )
            registry = manager.build(decisions, events)

        changed_registry = copy.deepcopy(registry)
        changed_registry["blockers"] = ["forged"]
        with self.assertRaises(SourceRegistryAdmissionError):
            self.consumer(changed_registry, [envelope], [accept])

        changed_envelope = copy.deepcopy(envelope)
        changed_envelope["submission_reason"] = "forged"
        with self.assertRaises(SourceRegistryAdmissionError):
            self.consumer(registry, [changed_envelope], [accept])

        changed_event = copy.deepcopy(accept)
        changed_event["reason"] = "forged"
        with self.assertRaises(SourceRegistryAdmissionError):
            self.consumer(registry, [envelope], [changed_event])

        original = manager.INVENTORY.read_bytes()
        with self.assertRaises(SourceRegistryAdmissionError):
            DropbearSourceRegistryV2(
                registry,
                REGISTRY_SCHEMA,
                json.loads(manager.SUBMISSION_SCHEMA.read_text()),
                json.loads(manager.EVENT_SCHEMA.read_text()),
                original + b" ",
                manager.V1_STATUS.read_bytes(),
                {
                    registry["submissions"][0]["submission_path"]:
                    manager.canonical_bytes(envelope)
                },
                {
                    registry["events"][0]["event_path"]:
                    manager.canonical_bytes(accept)
                },
            )

    def test_accept_ineligible_decision_and_multiple_active_sources_deny(self):
        incomplete = self.envelope()
        incomplete["decision"]["runtime_description_complete"] = False
        v1.set_digest(incomplete["decision"])
        incomplete["decision_sha256"] = manager.sha_bytes(
            manager.canonical_bytes(incomplete["decision"])
        )
        incomplete["submission_id"] = manager.expected_submission_id(incomplete)
        manager.set_digest(incomplete)
        with self.assertRaises(manager.SourceRegistryError):
            manager.validate_submission(incomplete)

        first = self.envelope("first")
        second = self.envelope(
            "second", submitted_at="2026-07-23T12:11:00Z"
        )
        events_value = [
            self.event(first, "accept", 1, "2026-07-23T12:20:00Z"),
            self.event(second, "accept", 2, "2026-07-23T12:30:00Z"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [first, second], events_value
            )
            with self.assertRaises(manager.SourceRegistryError):
                manager.build(decisions, events)

    def test_sequence_time_transition_and_filename_drift_deny(self):
        envelope = self.envelope()
        accept = self.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        revoke = self.event(
            envelope, "revoke", 2, "2026-07-23T12:19:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], [accept, revoke]
            )
            with self.assertRaises(manager.SourceRegistryError):
                manager.build(decisions, events)

        bad = copy.deepcopy(accept)
        bad["transition"]["next_state"] = "rejected"
        manager.set_digest(bad)
        with self.assertRaises(manager.SourceRegistryError):
            manager.validate_event(bad)

        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = self.write_case(
                Path(temporary), [envelope], []
            )
            original = next(decisions.iterdir())
            original.rename(decisions / "wrong-name.json")
            with self.assertRaises(manager.SourceRegistryError):
                manager.build(decisions, events)

    def test_approver_is_human_independent_and_distinct(self):
        envelope = self.envelope()
        for approver in (
            "codex-automated-approver",
            envelope["decision"]["reviewer"]["reviewer_id"],
            envelope["submitter"]["actor_id"],
        ):
            event = self.event(
                envelope,
                "accept",
                1,
                "2026-07-23T12:20:00Z",
            )
            event["approver"]["approver_id"] = approver
            event["event_id"] = manager.expected_event_id(event)
            manager.set_digest(event)
            if approver == "codex-automated-approver":
                with self.assertRaises(manager.SourceRegistryError):
                    manager.validate_event(event)
                continue
            manager.validate_event(event)
            with tempfile.TemporaryDirectory() as temporary:
                decisions, events = self.write_case(
                    Path(temporary), [envelope], [event]
                )
                with self.assertRaises(manager.SourceRegistryError):
                    manager.build(decisions, events)

    def test_submission_event_hash_id_digest_and_current_subject_drift_deny(self):
        envelope = self.envelope()
        mutations = [
            lambda value: value.__setitem__("submission_id", "sourcesubmission-" + "0" * 20),
            lambda value: value.__setitem__("decision_sha256", "0" * 64),
            lambda value: value["integrity"].__setitem__("record_sha256", "0" * 64),
            lambda value: value["decision"]["subject"].__setitem__(
                "repository_tree_id", "0" * 40
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(envelope)
            mutation(value)
            if value["integrity"]["record_sha256"] != "0" * 64:
                manager.set_digest(value)
            with self.assertRaises(manager.SourceRegistryError):
                manager.validate_submission(value)

        event = self.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        for field, changed in (
            ("event_id", "sourceevent-" + "0" * 20),
            ("integrity", {"record_sha256": "0" * 64}),
        ):
            value = copy.deepcopy(event)
            value[field] = changed
            with self.assertRaises(manager.SourceRegistryError):
                manager.validate_event(value)

    def test_foreign_files_are_rejected_from_owned_namespaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            decisions = root / "decisions"
            events = root / "events"
            decisions.mkdir()
            events.mkdir()
            (decisions / "README.txt").write_text("foreign")
            with self.assertRaises(manager.SourceRegistryError):
                manager.build(decisions, events)

    def test_failed_generate_is_transactional_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            decisions = root / "decisions"
            events = root / "events"
            output = root / "registry.json"
            decisions.mkdir()
            events.mkdir()
            manager.generate(decisions, events, output)
            before = output.read_bytes()
            (events / "foreign.txt").write_text("invalid")
            with self.assertRaises(manager.SourceRegistryError):
                manager.generate(decisions, events, output)
            self.assertEqual(before, output.read_bytes())

    def test_registry_summary_generation_digest_and_active_identity_tamper_deny(self):
        value = manager.build()
        mutations = [
            lambda item: item["summary"].__setitem__("submission_count", 1),
            lambda item: item.__setitem__("active_submission_id", "sourcesubmission-" + "0" * 20),
            lambda item: item.__setitem__("registry_generation_sha256", "0" * 64),
            lambda item: item["integrity"].__setitem__("record_sha256", "0" * 64),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(value)
            mutation(changed)
            with self.assertRaises(manager.SourceRegistryError):
                manager.validate_registry(changed)

    def test_registry_schema_rejects_support_motion_or_count_promotions(self):
        validator = Draft202012Validator(REGISTRY_SCHEMA)
        baseline = manager.build()
        mutations = [
            lambda value: value.__setitem__("support_granted", True),
            lambda value: value.__setitem__("physical_motion_authority", True),
            lambda value: value["summary"].__setitem__("accepted_count", 2),
            lambda value: value["summary"].__setitem__(
                "active_runtime_complete_count", 2
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(baseline)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))

    def test_cli_check_is_read_only_and_canonical(self):
        before = REGISTRY_PATH.read_bytes()
        result = subprocess.run(
            ["python3", str(TOOL), "--check"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIn("submissions=0 events=0 active=0", result.stdout)
        self.assertEqual(before, REGISTRY_PATH.read_bytes())
        self.assertEqual(
            before,
            manager.canonical_bytes(json.loads(before)),
        )


if __name__ == "__main__":
    unittest.main()
