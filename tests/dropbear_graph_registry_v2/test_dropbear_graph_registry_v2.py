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

from tests.dropbear_graph_v2 import test_dropbear_graph_v2 as graph_fixtures
from tests.dropbear_source_registry_v2 import (
    test_dropbear_source_registry_v2 as source_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_dropbear_graph_registry_v2.py"
GRAPH_TOOL = ROOT / "tools/manage_dropbear_graph_v2.py"
REGISTRY_PATH = ROOT / "generated/dropbear_graph_registry_v2/registry.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


manager = load_module("dropbear_graph_registry_v2_test_module", TOOL)
graph_manager = load_module("dropbear_graph_registry_graph_test_module", GRAPH_TOOL)


class DropbearGraphRegistryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_fixtures.DropbearSourceRegistryV2Tests.setUpClass()

    def active_source_registry(self):
        case = source_fixtures.DropbearSourceRegistryV2Tests()
        envelope = case.envelope("graph-source")
        accept = case.event(
            envelope, "accept", 1, "2026-07-23T12:20:00Z"
        )
        with tempfile.TemporaryDirectory() as temporary:
            decisions, events = case.write_case(
                Path(temporary), [envelope], [accept]
            )
            return source_fixtures.manager.build(decisions, events)

    def graph_status(self, source_registry):
        value = json.loads(manager.GRAPH_STATUS.read_text())
        value["source"]["source_registry_generation_sha256"] = source_registry[
            "registry_generation_sha256"
        ]
        value["summary"]["source_authority_active_count"] = 1
        return value

    def exact_dropbear_graph(self):
        value = graph_fixtures.DropbearGraphV2Tests().graph()
        for side in ("left", "right"):
            for joint_name in (
                "hip-roll",
                "hip-pitch",
                "knee",
                "inner-calf",
                "outer-calf",
            ):
                frame_id = f"{side}-{joint_name}-frame"
                link_id = f"{side}-{joint_name}-link"
                joint_id = f"{side}-{joint_name}-joint"
                coordinate_id = f"{side}-{joint_name}-coordinate"
                actuator_id = f"actuator-{side}-{joint_name}"
                value["frames"].append(
                    {
                        "frame_id": frame_id,
                        "kind": "link",
                        "parent_frame_id": "base-frame",
                        "chirality": side,
                        "transform": graph_fixtures.transform(
                            "base-frame",
                            (
                                0.1,
                                0.1 if side == "left" else -0.1,
                                -0.05,
                            ),
                        ),
                        "source_evidence_refs": graph_fixtures.evidence(frame_id),
                    }
                )
                value["links"].append(
                    {
                        "link_id": link_id,
                        "frame_id": frame_id,
                        "chirality": side,
                        "source_evidence_refs": graph_fixtures.evidence(link_id),
                    }
                )
                value["joints"].append(
                    {
                        "joint_id": joint_id,
                        "parent_link_id": "base-link",
                        "child_link_id": link_id,
                        "joint_type": "revolute",
                        "activity": "active",
                        "chirality": side,
                        "origin_frame_id": frame_id,
                        "axis": {
                            "expressed_in_frame_id": "base-frame",
                            "xyz_unit": [1.0, 0.0, 0.0],
                        },
                        "coordinate_id": coordinate_id,
                        "source_evidence_refs": graph_fixtures.evidence(joint_id),
                    }
                )
                value["dof_ledger"]["coordinates"].append(
                    {
                        "coordinate_id": coordinate_id,
                        "joint_id": joint_id,
                        "classification": "independent",
                        "unit": "rad",
                        "commandable": True,
                    }
                )
                value["ownership"].append(
                    {
                        "coordinate_id": coordinate_id,
                        "writer_kind": "gateway",
                        "writer_id": f"{side}-{joint_name}-writer",
                        "state_policy_id": f"{side}-{joint_name}-state-policy",
                        "diagnostic_bypass_allowed": False,
                    }
                )
                dependency_ids = []
                for kind in ("cad", "calibration", "limit", "route"):
                    dependency_id = f"{side}-{joint_name}-{kind}-dependency"
                    dependency_ids.append(dependency_id)
                    value["dependencies"].append(
                        {
                            "dependency_id": dependency_id,
                            "kind": kind,
                            "state": "admitted",
                            "subject_id": f"synthetic-{side}-{joint_name}-{kind}",
                            "evidence_refs": graph_fixtures.evidence(dependency_id),
                        }
                    )
                value["actuator_bindings"].append(
                    {
                        "actuator_id": actuator_id,
                        "chirality": side,
                        "command_coordinate_id": coordinate_id,
                        "joint_ids": [joint_id],
                        "dependency_ids": dependency_ids,
                        "source_evidence_refs": graph_fixtures.evidence(actuator_id),
                    }
                )
                value["ros_mappings"].append(
                    {
                        "mapping_id": f"{side}-{joint_name}-ros-mapping",
                        "ros_joint_name": f"{side}_{joint_name.replace('-', '_')}_joint",
                        "coordinate_id": coordinate_id,
                        "actuator_ids": [actuator_id],
                        "status": "mapped",
                        "source_evidence_refs": graph_fixtures.evidence(
                            f"{side}-{joint_name}-ros"
                        ),
                    }
                )
        for joint_name in (
            "hip-roll",
            "hip-pitch",
            "knee",
            "inner-calf",
            "outer-calf",
        ):
            for kind, suffix in (
                ("link", "link"),
                ("joint", "joint"),
                ("actuator", None),
            ):
                if kind == "actuator":
                    left_id = f"actuator-left-{joint_name}"
                    right_id = f"actuator-right-{joint_name}"
                else:
                    left_id = f"left-{joint_name}-{suffix}"
                    right_id = f"right-{joint_name}-{suffix}"
                value["symmetry_pairs"].append(
                    {
                        "symmetry_id": f"{joint_name}-{kind}-symmetry",
                        "entity_kind": kind,
                        "left_id": left_id,
                        "right_id": right_id,
                        "relation": "exact_mirror",
                        "reflection_plane": "xz",
                        "coordinate_sign": 1.0,
                        "coordinate_offset_si": 0.0,
                        "rationale": "Synthetic exact Dropbear coverage fixture.",
                        "evidence_refs": graph_fixtures.evidence(
                            f"{joint_name}-{kind}-symmetry"
                        ),
                    }
                )
        value["dof_ledger"]["summary"].update(
            independent=12,
            total_coordinates=14,
            physical_generalized_dof=12,
        )
        graph_manager.validate_graph(value, require_dropbear=True)
        return value

    def decision(self, marker, source_registry):
        value = graph_manager.template(source_registry)
        value["record_state"] = "submitted"
        value["reviewer"] = {
            "reviewer_id": f"mechanical-reviewer-{marker}",
            "organization_or_team": "independent-mechanical-review-team",
            "mechanical_graph_competence_attested": True,
            "independence_attested": True,
            "reviewed_at": "2026-07-23T13:00:00Z",
            "review_assertion": f"Synthetic exact graph review {marker}.",
            "signature_evidence_refs": graph_fixtures.evidence(f"review-{marker}"),
        }
        value["disposition"] = "accept_graph"
        value["graph"] = self.exact_dropbear_graph()
        value["migration"].update(
            resolved_v1_question_count=161,
            unresolved_v1_question_count=0,
            migration_complete=True,
            evidence_refs=graph_fixtures.evidence(f"migration-{marker}"),
        )
        value["decision_complete"] = True
        value["canonical_graph_admissible"] = True
        graph_manager.set_digest(value)
        graph_manager.validate_decision(value, source_registry)
        return value

    def envelope(
        self,
        marker,
        source_registry,
        *,
        submitted_at="2026-07-23T13:10:00Z",
        supersedes=None,
    ):
        decision = self.decision(marker, source_registry)
        value = {
            "schema_version": "dropbear-graph-submission/2",
            "submission_id": "graphsubmission-" + "0" * 20,
            "submitted_at": submitted_at,
            "submitter": {
                "actor_id": f"graph-submitter-{marker}",
                "organization_or_team": "graph-submission-team",
                "human_attested": True,
            },
            "supersedes_submission_id": supersedes,
            "source_registry_generation_sha256": source_registry[
                "registry_generation_sha256"
            ],
            "decision_sha256": manager.sha_bytes(
                manager.canonical_bytes(decision)
            ),
            "decision": decision,
            "submission_reason": f"Synthetic graph submission {marker}.",
            "evidence_refs": graph_fixtures.evidence(f"submission-{marker}"),
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["submission_id"] = manager.expected_submission_id(value)
        manager.set_digest(value)
        manager.validate_submission(value, source_registry)
        return value

    def event(
        self,
        envelope,
        source_registry,
        event_type,
        sequence,
        approved_at,
        *,
        replacement=None,
    ):
        prior, next_state = manager.TRANSITIONS[event_type]
        value = {
            "schema_version": "dropbear-graph-event/2",
            "event_id": "graphevent-" + "0" * 20,
            "sequence": sequence,
            "event_type": event_type,
            "source_registry_generation_sha256": source_registry[
                "registry_generation_sha256"
            ],
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
            "transition": {"prior_state": prior, "next_state": next_state},
            "approver": {
                "approver_id": f"graph-governance-approver-{sequence}",
                "organization_or_team": "independent-graph-governance",
                "human_attested": True,
                "independence_attested": True,
                "governance_authority_attested": True,
                "approved_at": approved_at,
                "approval_assertion": f"Synthetic {event_type} approval.",
                "signature_evidence_refs": graph_fixtures.evidence(f"event-{sequence}"),
            },
            "reason": f"Synthetic graph {event_type}.",
            "evidence_refs": graph_fixtures.evidence(f"event-reason-{sequence}"),
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        value["event_id"] = manager.expected_event_id(value)
        manager.set_digest(value)
        manager.validate_event(value, source_registry)
        return value

    def write_case(self, root, envelopes, events):
        decisions = root / "decisions"
        event_root = root / "events"
        decisions.mkdir()
        event_root.mkdir()
        for envelope in envelopes:
            (decisions / f"{envelope['submission_id']}.json").write_bytes(
                manager.canonical_bytes(envelope)
            )
        for event in events:
            (
                event_root
                / f"{event['sequence']:06d}-{event['event_id']}.json"
            ).write_bytes(manager.canonical_bytes(event))
        return decisions, event_root

    def build_case(self, source_registry, envelopes, events):
        status = self.graph_status(source_registry)
        with tempfile.TemporaryDirectory() as temporary:
            decisions, event_root = self.write_case(
                Path(temporary), envelopes, events
            )
            return manager.build(
                decisions,
                event_root,
                source_registry=source_registry,
                graph_status=status,
            )

    def test_tracked_registry_is_empty_canonical_and_denial_only(self):
        value = manager.build()
        self.assertEqual(value, json.loads(REGISTRY_PATH.read_text()))
        self.assertEqual([], value["submissions"])
        self.assertEqual([], value["events"])
        self.assertIsNone(value["active_graph_decision_id"])
        self.assertEqual(0, value["summary"]["canonical_graph_count"])
        self.assertFalse(value["support_granted"])
        self.assertFalse(value["physical_motion_authority"])

    def test_accept_selects_exact_twelve_actuator_graph(self):
        source = self.active_source_registry()
        envelope = self.envelope("one", source)
        accept = self.event(
            envelope, source, "accept", 1, "2026-07-23T13:20:00Z"
        )
        value = self.build_case(source, [envelope], [accept])
        self.assertEqual(envelope["submission_id"], value["active_submission_id"])
        self.assertEqual(1, value["summary"]["accepted_count"])
        self.assertEqual(12, value["summary"]["actuator_mapping_count"])
        self.assertEqual(12, value["summary"]["ros_mapping_count"])
        self.assertEqual([], value["blockers"])
        self.assertFalse(value["support_granted"])
        self.assertFalse(value["physical_motion_authority"])

    def test_accept_revoke_removes_graph_and_runtime_mappings(self):
        source = self.active_source_registry()
        envelope = self.envelope("revoke", source)
        events = [
            self.event(
                envelope, source, "accept", 1, "2026-07-23T13:20:00Z"
            ),
            self.event(
                envelope, source, "revoke", 2, "2026-07-23T13:30:00Z"
            ),
        ]
        value = self.build_case(source, [envelope], events)
        self.assertEqual(1, value["summary"]["revoked_count"])
        self.assertEqual(0, value["summary"]["canonical_graph_count"])
        self.assertEqual(0, value["summary"]["actuator_mapping_count"])
        self.assertIsNone(value["active_graph_decision_id"])

    def test_atomic_supersession_changes_active_submission_and_generation(self):
        source = self.active_source_registry()
        old = self.envelope("old", source)
        new = self.envelope(
            "new",
            source,
            submitted_at="2026-07-23T13:25:00Z",
            supersedes=old["submission_id"],
        )
        accepted_only = self.build_case(
            source,
            [old],
            [
                self.event(
                    old, source, "accept", 1, "2026-07-23T13:20:00Z"
                )
            ],
        )
        events = [
            self.event(
                old, source, "accept", 1, "2026-07-23T13:20:00Z"
            ),
            self.event(
                old,
                source,
                "supersede",
                2,
                "2026-07-23T13:30:00Z",
                replacement=new,
            ),
        ]
        value = self.build_case(source, [old, new], events)
        states = {row["submission_id"]: row for row in value["submissions"]}
        self.assertEqual("superseded", states[old["submission_id"]]["lifecycle_state"])
        self.assertEqual("accepted", states[new["submission_id"]]["lifecycle_state"])
        self.assertEqual(new["submission_id"], value["active_submission_id"])
        self.assertNotEqual(
            accepted_only["registry_generation_sha256"],
            value["registry_generation_sha256"],
        )

    def test_reject_sequence_time_multiple_active_and_approver_deny(self):
        source = self.active_source_registry()
        first = self.envelope("first", source)
        second = self.envelope(
            "second", source, submitted_at="2026-07-23T13:11:00Z"
        )
        reject = self.event(
            first, source, "reject", 1, "2026-07-23T13:20:00Z"
        )
        value = self.build_case(source, [first], [reject])
        self.assertEqual(1, value["summary"]["rejected_count"])

        two_accepts = [
            self.event(
                first, source, "accept", 1, "2026-07-23T13:20:00Z"
            ),
            self.event(
                second, source, "accept", 2, "2026-07-23T13:30:00Z"
            ),
        ]
        with self.assertRaises(manager.GraphRegistryError):
            self.build_case(source, [first, second], two_accepts)

        bad_approver = copy.deepcopy(two_accepts[0])
        bad_approver["approver"]["approver_id"] = first["submitter"]["actor_id"]
        bad_approver["event_id"] = manager.expected_event_id(bad_approver)
        manager.set_digest(bad_approver)
        with self.assertRaises(manager.GraphRegistryError):
            self.build_case(source, [first], [bad_approver])

        reversed_time = [
            two_accepts[0],
            self.event(
                first, source, "revoke", 2, "2026-07-23T13:19:00Z"
            ),
        ]
        with self.assertRaises(manager.GraphRegistryError):
            self.build_case(source, [first], reversed_time)

    def test_hash_id_source_generation_schema_and_cli_deny(self):
        source = self.active_source_registry()
        envelope = self.envelope("tamper", source)
        accept = self.event(
            envelope, source, "accept", 1, "2026-07-23T13:20:00Z"
        )
        for mutation in (
            lambda value: value.__setitem__(
                "submission_id", "graphsubmission-" + "0" * 20
            ),
            lambda value: value.__setitem__("decision_sha256", "0" * 64),
            lambda value: value.__setitem__(
                "source_registry_generation_sha256", "0" * 64
            ),
        ):
            changed = copy.deepcopy(envelope)
            mutation(changed)
            manager.set_digest(changed)
            with self.assertRaises(manager.GraphRegistryError):
                manager.validate_submission(changed, source)

        changed_event = copy.deepcopy(accept)
        changed_event["source_registry_generation_sha256"] = "0" * 64
        changed_event["event_id"] = manager.expected_event_id(changed_event)
        manager.set_digest(changed_event)
        with self.assertRaises(manager.GraphRegistryError):
            manager.validate_event(changed_event, source)

        schema = json.loads(manager.REGISTRY_SCHEMA.read_text())
        value = manager.build()
        promoted = copy.deepcopy(value)
        promoted["physical_motion_authority"] = True
        self.assertTrue(
            list(Draft202012Validator(schema).iter_errors(promoted))
        )
        result = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("active=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
