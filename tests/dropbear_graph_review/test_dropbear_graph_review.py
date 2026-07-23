from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_dropbear_graph_review.py"
SOURCE_TOOL = ROOT / "tools/manage_dropbear_source_authority.py"
INVENTORY_PATH = ROOT / "generated/dropbear_description/inventory.json"
STATUS_PATH = ROOT / "generated/dropbear_graph_review/status.json"
PACKET_PATH = ROOT / "generated/dropbear_graph_review/packet.json"
WORKBENCH_PATH = ROOT / "generated/dropbear_graph_review/workbench/index.html"
STATUS_SCHEMA = json.loads(
    (ROOT / "schemas/dropbear-graph-review-status.schema.json").read_text()
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


manager = load_module("dropbear_graph_review_test_module", TOOL)
source_manager = load_module(
    "dropbear_graph_review_source_test_module", SOURCE_TOOL
)


class DropbearGraphReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory, cls.source_status, cls.reconciliation = manager.sources()
        cls.template = manager.template()
        cls.packet = json.loads(PACKET_PATH.read_text())

    def source_file(self, suffix: str):
        matches = [
            record
            for record in self.inventory["files"]
            if record["package_family"] == "gazebo_dropbear"
            and record["classification"] == "source_candidate"
            and record["path"].endswith(suffix)
        ]
        self.assertEqual(1, len(matches), suffix)
        return matches[0]

    def accepted_source_fixture(self):
        decision = source_manager.template()
        decision["record_state"] = "submitted"
        decision["reviewer"] = {
            "reviewer_id": "independent-human-source-test-fixture",
            "organization_or_team": "external-source-test-fixture-team",
            "independence_attested": True,
            "reviewed_at": "2026-07-23T07:00:00Z",
            "review_assertion": (
                "Synthetic unit-test source decision; not project evidence."
            ),
            "signature_evidence_refs": [
                "tests/dropbear_graph_review/synthetic-source-review"
            ],
        }
        decision["disposition"] = "accept_selection"
        decision["family_policy"] = {
            "mode": "single_family",
            "primary_family": "gazebo_dropbear",
            "rationale": "Synthetic test-only single-family source selection.",
            "evidence_refs": [
                "tests/dropbear_graph_review/synthetic-source-family-policy"
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
            role["status"] = "selected"
            role["selected_files"] = [
                source_manager.selection_from_file(source)
            ]
            role["rationale"] = f"Synthetic source for {role['role']}."
            role["evidence_refs"] = [
                "tests/dropbear_graph_review/synthetic-source-role"
            ]
        selected_by_key: dict[str, set[str]] = {}
        for role in decision["role_decisions"]:
            for selected in role["selected_files"]:
                selected_by_key.setdefault(selected["logical_key"], set()).add(
                    selected["git_object_id"]
                )
        for divergence in decision["divergence_decisions"]:
            selected = sorted(
                selected_by_key.get(divergence["logical_key"], set())
            )
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
                "tests/dropbear_graph_review/synthetic-source-divergence"
            ]
        decision["decision_complete"] = True
        decision["runtime_description_complete"] = True
        source_manager.set_digest(decision)
        source_manager.validate_decision(decision, self.inventory)
        return decision

    def accepted_graph_fixture(self):
        source = self.accepted_source_fixture()
        decision = copy.deepcopy(self.template)
        decision["record_state"] = "submitted"
        decision["source_authority"] = {
            "decision_id": source["decision_id"],
            "decision_sha256": manager.sha_bytes(
                manager.canonical_bytes(source)
            ),
            "admitted": True,
        }
        decision["reviewer"] = {
            "reviewer_id": "independent-human-graph-test-fixture",
            "organization_or_team": "external-mechanical-test-fixture-team",
            "mechanical_graph_competence_attested": True,
            "independence_attested": True,
            "reviewed_at": "2026-07-23T08:00:00Z",
            "review_assertion": (
                "Synthetic unit-test graph decision; not project evidence."
            ),
            "signature_evidence_refs": [
                "tests/dropbear_graph_review/synthetic-graph-review"
            ],
        }
        decision["disposition"] = "accept_graph"

        graph = decision["graph"]
        graph["base_link_id"] = "base-link"
        graph["links"] = [
            {
                "link_id": "base-link",
                "canonical_name": "base",
                "source_observation_refs": [
                    "tests/dropbear_graph_review/synthetic-link"
                ],
            }
        ]
        graph["joints"] = []
        graph["ownership"] = []
        graph["actuator_bindings"] = []
        graph["observation_bindings"] = []
        graph["ros_command_bindings"] = []

        rows_by_side: dict[str, list[dict]] = {"left": [], "right": []}
        for actuator in self.reconciliation["actuators"]:
            rows_by_side[actuator["chirality"]].append(actuator)
        ros_by_side = {
            group["chirality"]: group["joint_ids"]
            for group in self.reconciliation["ros_leg_groups"]
        }
        mapped_semantics = {
            "hip_roll",
            "hip_pitch",
            "knee",
            "inner_calf",
            "outer_calf",
        }

        for side in ("left", "right"):
            parent = "base-link"
            mapped_index = 0
            for index, actuator in enumerate(rows_by_side[side], start=1):
                semantic = actuator["semantic_joint"].replace("_", "-")
                link_id = f"link-{side}-{index}"
                joint_id = f"joint-{side}-{semantic}"
                ownership_id = f"owner-{side}-{semantic}"
                graph["links"].append(
                    {
                        "link_id": link_id,
                        "canonical_name": f"{side}_synthetic_link_{index}",
                        "source_observation_refs": [
                            "tests/dropbear_graph_review/synthetic-link"
                        ],
                    }
                )
                graph["joints"].append(
                    {
                        "joint_id": joint_id,
                        "canonical_name": actuator["canonical_joint_name"],
                        "joint_type": "continuous",
                        "activity": "active",
                        "parent_link_id": parent,
                        "child_link_id": link_id,
                        "origin_xyz_m": [0.0, 0.0, 0.0],
                        "origin_rpy_rad": [0.0, 0.0, 0.0],
                        "axis_unit": [0.0, 0.0, 1.0],
                        "positive_direction": "positive about reviewed axis",
                        "zero_definition": "synthetic reviewed zero",
                        "mimic": None,
                        "source_observation_refs": [
                            "tests/dropbear_graph_review/synthetic-joint"
                        ],
                    }
                )
                graph["ownership"].append(
                    {
                        "ownership_id": ownership_id,
                        "command_owner": "synthetic-exclusive-controller",
                        "state_policy_id": "synthetic-command-state-policy",
                        "diagnostic_bypass_allowed": False,
                    }
                )
                graph["actuator_bindings"].append(
                    {
                        "actuator_id": actuator["actuator_id"],
                        "canonical_joint_name": actuator["canonical_joint_name"],
                        "joint_ids": [joint_id],
                        "command_coordinate_joint_id": joint_id,
                        "coupling_constraint_id": None,
                        "ownership_id": ownership_id,
                        "source_evidence_refs": [
                            "tests/dropbear_graph_review/synthetic-actuator-binding"
                        ],
                    }
                )
                feedback = actuator["feedback"]
                graph["observation_bindings"].append(
                    {
                        "canonical_joint_name": actuator[
                            "canonical_joint_name"
                        ],
                        "external_sensor_status": feedback[
                            "external_sensor_status"
                        ],
                        "external_sensor_id": feedback["external_sensor_id"],
                        "native_telemetry_status": "unknown",
                        "reconciliation_policy_status": "reviewed",
                        "source_evidence_refs": [
                            "tests/dropbear_graph_review/synthetic-observation"
                        ],
                    }
                )
                if actuator["semantic_joint"] in mapped_semantics:
                    ros_id = ros_by_side[side][mapped_index]
                    mapped_index += 1
                    ros_status = "mapped"
                    rationale = "Synthetic exact one-to-one reviewed mapping."
                else:
                    ros_id = None
                    ros_status = "uncommanded"
                    rationale = (
                        "Synthetic cardinality resolution leaves hip yaw "
                        "uncommanded by the five-joint ROS observation."
                    )
                graph["ros_command_bindings"].append(
                    {
                        "canonical_joint_name": actuator[
                            "canonical_joint_name"
                        ],
                        "status": ros_status,
                        "ros_joint_id": ros_id,
                        "rationale": rationale,
                        "source_evidence_refs": [
                            "tests/dropbear_graph_review/synthetic-ros-binding"
                        ],
                    }
                )
                parent = link_id
            self.assertEqual(5, mapped_index)

        graph_ids = {row["joint_id"] for row in graph["joints"]}
        for response in decision["question_responses"]:
            if response["kind"] == "actuator_mapping":
                joint_id = response["question_id"].replace("map-", "joint-", 1)
                self.assertIn(joint_id, graph_ids)
                response["resolution"] = "resolved_as_graph_fact"
                response["answer"] = "Synthetic reviewed actuator mapping."
                response["evidence_refs"] = [
                    "tests/dropbear_graph_review/synthetic-question-answer"
                ]
                response["graph_fact_ids"] = [joint_id]
            elif response["kind"] == "cardinality_and_coupling":
                side = "left" if "-left-" in response["question_id"] else "right"
                response["resolution"] = "resolved_as_graph_fact"
                response["answer"] = (
                    "Synthetic six-to-five review: hip yaw is not in the "
                    "observed ROS command set."
                )
                response["evidence_refs"] = [
                    "tests/dropbear_graph_review/synthetic-cardinality"
                ]
                response["graph_fact_ids"] = [f"joint-{side}-hip-yaw"]
            else:
                response["resolution"] = "resolved_not_in_graph"
                response["answer"] = (
                    "Synthetic fixture excludes this candidate after review."
                )
                response["evidence_refs"] = [
                    "tests/dropbear_graph_review/synthetic-exclusion"
                ]
                response["graph_fact_ids"] = []
        decision["decision_complete"] = True
        decision["canonical_graph_admissible"] = True
        manager.set_digest(decision)
        manager.validate_decision(
            decision, accepted_source_decision=source
        )
        return decision, source

    def assert_denied(self, decision, source, mutation):
        mutation(decision)
        manager.set_digest(decision)
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(
                decision, accepted_source_decision=source
            )

    def test_template_is_exact_empty_unanswered_and_digest_bound(self):
        manager.validate_decision(copy.deepcopy(self.template))
        template_path = (
            ROOT
            / "generated/dropbear_graph_review/templates"
            / f"{self.template['decision_id']}.json"
        )
        self.assertEqual(self.template, json.loads(template_path.read_text()))
        self.assertEqual(161, len(self.template["question_responses"]))
        self.assertTrue(
            all(
                row["resolution"] == "unanswered"
                for row in self.template["question_responses"]
            )
        )
        self.assertEqual([], self.template["graph"]["links"])
        self.assertFalse(self.template["canonical_graph_admissible"])
        self.assertFalse(self.template["support_granted"])
        self.assertFalse(self.template["physical_motion_authority"])

    def test_packet_partitions_all_questions_into_bounded_review_cohorts(self):
        question_ids = [
            question_id
            for cohort in self.packet["cohorts"]
            for question_id in cohort["question_ids"]
        ]
        self.assertEqual(10, len(self.packet["cohorts"]))
        self.assertEqual(161, len(question_ids))
        self.assertEqual(161, len(set(question_ids)))
        self.assertTrue(
            all(1 <= len(row["question_ids"]) <= 20 for row in self.packet["cohorts"])
        )
        self.assertEqual(
            set(question_ids),
            {row["question_id"] for row in self.inventory["review_questions"]},
        )
        self.assertEqual(0, self.packet["summary"]["accepted_graph_count"])
        self.assertFalse(self.packet["support_granted"])
        self.assertFalse(self.packet["physical_motion_authority"])

    def test_workbench_is_local_complete_and_cannot_promote_authority(self):
        html = WORKBENCH_PATH.read_text()
        for marker in (
            "http://",
            "https://",
            "fetch(",
            "XMLHttpRequest",
            "<script src=",
        ):
            self.assertNotIn(marker, html)
        for response in self.template["question_responses"]:
            self.assertIn(response["question_id"], html)
        self.assertIn("Review input only.", html)
        self.assertIn("cannot select source", html)
        self.assertIn('"canonical_graph_admissible": false', html)
        self.assertIn('"physical_motion_authority": false', html)

    def test_complete_synthetic_human_graph_validates_but_is_not_evidence(self):
        decision, source = self.accepted_graph_fixture()
        manager.validate_decision(
            decision, accepted_source_decision=source
        )
        tracked = json.loads(STATUS_PATH.read_text())
        self.assertTrue(decision["canonical_graph_admissible"])
        self.assertEqual(0, tracked["summary"]["accepted_graph_count"])
        self.assertEqual([], tracked["accepted_graph_decision_ids"])

    def test_positive_mimic_closed_chain_and_simulator_only_closure_validate(self):
        decision, source = self.accepted_graph_fixture()
        graph = decision["graph"]
        graph["links"].append(
            {
                "link_id": "link-mimic-fixture",
                "canonical_name": "synthetic_mimic_link",
                "source_observation_refs": [
                    "tests/dropbear_graph_review/synthetic-mimic-link"
                ],
            }
        )
        graph["joints"].append(
            {
                "joint_id": "joint-mimic-fixture",
                "canonical_name": "synthetic_mimic_joint",
                "joint_type": "continuous",
                "activity": "mimic",
                "parent_link_id": "link-left-6",
                "child_link_id": "link-mimic-fixture",
                "origin_xyz_m": [0.0, 0.0, 0.0],
                "origin_rpy_rad": [0.0, 0.0, 0.0],
                "axis_unit": [0.0, 0.0, 1.0],
                "positive_direction": "synthetic reviewed mimic direction",
                "zero_definition": "synthetic reviewed mimic zero",
                "mimic": {
                    "driver_joint_id": "joint-left-knee",
                    "multiplier": -1.0,
                    "offset_rad": 0.1,
                },
                "source_observation_refs": [
                    "tests/dropbear_graph_review/synthetic-mimic-joint"
                ],
            }
        )
        graph["joints"].append(
            {
                "joint_id": "joint-simulator-loop-fixture",
                "canonical_name": "synthetic_simulator_loop_edge",
                "joint_type": "continuous",
                "activity": "simulator_only",
                "parent_link_id": "base-link",
                "child_link_id": "link-left-6",
                "origin_xyz_m": [0.0, 0.0, 0.0],
                "origin_rpy_rad": [0.0, 0.0, 0.0],
                "axis_unit": [0.0, 1.0, 0.0],
                "positive_direction": "synthetic simulator closure direction",
                "zero_definition": "synthetic simulator closure zero",
                "mimic": None,
                "source_observation_refs": [
                    "tests/dropbear_graph_review/synthetic-simulator-edge"
                ],
            }
        )
        graph["constraints"].extend(
            [
                {
                    "constraint_id": "constraint-mimic-fixture",
                    "kind": "mimic",
                    "joint_ids": [
                        "joint-left-knee",
                        "joint-mimic-fixture",
                    ],
                    "independent_joint_ids": ["joint-left-knee"],
                    "equation": "q_mimic = -q_left_knee + 0.1 rad",
                    "solver_owner": "physical_mechanism",
                    "physical_counterpart_status": "reviewed",
                    "source_observation_refs": [
                        "tests/dropbear_graph_review/synthetic-mimic-constraint"
                    ],
                },
                {
                    "constraint_id": "constraint-closed-chain-fixture",
                    "kind": "closed_chain",
                    "joint_ids": [
                        "joint-left-inner-calf",
                        "joint-left-outer-calf",
                    ],
                    "independent_joint_ids": ["joint-left-inner-calf"],
                    "equation": "synthetic reviewed physical closure",
                    "solver_owner": "physical_mechanism",
                    "physical_counterpart_status": "reviewed",
                    "source_observation_refs": [
                        "tests/dropbear_graph_review/synthetic-closed-chain"
                    ],
                },
                {
                    "constraint_id": "constraint-simulator-loop-fixture",
                    "kind": "simulator_only_closure",
                    "joint_ids": [
                        "joint-left-knee",
                        "joint-simulator-loop-fixture",
                    ],
                    "independent_joint_ids": ["joint-left-knee"],
                    "equation": "synthetic simulator-only loop closure",
                    "solver_owner": "rigid_body_simulator",
                    "physical_counterpart_status": "not_applicable",
                    "source_observation_refs": [
                        "tests/dropbear_graph_review/synthetic-simulator-constraint"
                    ],
                },
            ]
        )
        mimic_response = next(
            row
            for row in decision["question_responses"]
            if row["kind"] == "mimic_or_coupling"
        )
        mimic_response.update(
            resolution="resolved_as_graph_fact",
            answer="Synthetic mimic and physical closed-chain fixture.",
            evidence_refs=[
                "tests/dropbear_graph_review/synthetic-positive-mimic"
            ],
            graph_fact_ids=[
                "joint-mimic-fixture",
                "constraint-mimic-fixture",
                "constraint-closed-chain-fixture",
            ],
        )
        loop_response = next(
            row
            for row in decision["question_responses"]
            if row["kind"] == "gazebo_loop_closure_candidate"
        )
        loop_response.update(
            resolution="resolved_as_graph_fact",
            answer="Synthetic simulator-only closure fixture.",
            evidence_refs=[
                "tests/dropbear_graph_review/synthetic-positive-loop"
            ],
            graph_fact_ids=[
                "joint-simulator-loop-fixture",
                "constraint-simulator-loop-fixture",
            ],
        )
        manager.set_digest(decision)
        manager.validate_decision(
            decision, accepted_source_decision=source
        )
        tracked = json.loads(STATUS_PATH.read_text())
        self.assertEqual(0, tracked["summary"]["canonical_graph_count"])

    def test_undeclared_simulator_edge_denies(self):
        base, source = self.accepted_graph_fixture()
        graph = base["graph"]
        graph["links"].append(
            {
                "link_id": "link-simulator-fixture",
                "canonical_name": "synthetic_simulator_link",
                "source_observation_refs": ["synthetic"],
            }
        )
        graph["joints"].append(
            {
                "joint_id": "joint-simulator-fixture",
                "canonical_name": "synthetic_simulator_joint",
                "joint_type": "continuous",
                "activity": "simulator_only",
                "parent_link_id": "base-link",
                "child_link_id": "link-simulator-fixture",
                "origin_xyz_m": [0.0, 0.0, 0.0],
                "origin_rpy_rad": [0.0, 0.0, 0.0],
                "axis_unit": [1.0, 0.0, 0.0],
                "positive_direction": "synthetic",
                "zero_definition": "synthetic",
                "mimic": None,
                "source_observation_refs": ["synthetic"],
            }
        )
        manager.set_digest(base)
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(
                base, accepted_source_decision=source
            )

    def test_mimic_dependency_cycle_denies(self):
        decision, source = self.accepted_graph_fixture()
        graph = decision["graph"]
        first = graph["joints"][0]
        second = graph["joints"][1]
        first.update(
            activity="mimic",
            mimic={
                "driver_joint_id": second["joint_id"],
                "multiplier": 1.0,
                "offset_rad": 0.0,
            },
        )
        second.update(
            activity="mimic",
            mimic={
                "driver_joint_id": first["joint_id"],
                "multiplier": 1.0,
                "offset_rad": 0.0,
            },
        )
        graph["constraints"].extend(
            [
                {
                    "constraint_id": "constraint-cycle-one",
                    "kind": "mimic",
                    "joint_ids": [first["joint_id"], second["joint_id"]],
                    "independent_joint_ids": [second["joint_id"]],
                    "equation": "synthetic cycle one",
                    "solver_owner": "physical_mechanism",
                    "physical_counterpart_status": "reviewed",
                    "source_observation_refs": ["synthetic"],
                },
                {
                    "constraint_id": "constraint-cycle-two",
                    "kind": "mimic",
                    "joint_ids": [first["joint_id"], second["joint_id"]],
                    "independent_joint_ids": [first["joint_id"]],
                    "equation": "synthetic cycle two",
                    "solver_owner": "physical_mechanism",
                    "physical_counterpart_status": "reviewed",
                    "source_observation_refs": ["synthetic"],
                },
            ]
        )
        manager.set_digest(decision)
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(
                decision, accepted_source_decision=source
            )

    def test_source_authority_missing_mismatched_or_incomplete_denies(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["source_authority"].__setitem__(
                "admitted", False
            ),
            lambda decision: decision["source_authority"].__setitem__(
                "decision_sha256", "0" * 64
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(base, accepted_source_decision=None)
        incomplete_source = copy.deepcopy(source)
        incomplete_source["runtime_description_complete"] = False
        source_manager.set_digest(incomplete_source)
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(
                base, accepted_source_decision=incomplete_source
            )

    def test_question_coverage_hash_resolution_and_fact_reference_deny(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["question_responses"].__setitem__(
                0, decision["question_responses"][1]
            ),
            lambda decision: decision["question_responses"][0].__setitem__(
                "question_sha256", "0" * 64
            ),
            lambda decision: decision["question_responses"][0].__setitem__(
                "graph_fact_ids", ["joint-unknown"]
            ),
            lambda decision: (
                decision["question_responses"][0].update(
                    {
                        "resolution": "unresolved_needs_evidence",
                        "graph_fact_ids": [],
                    }
                ),
                decision.__setitem__("decision_complete", False),
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_tree_self_edge_multiple_parent_disconnect_and_cycle_deny(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["graph"]["joints"][0].__setitem__(
                "child_link_id",
                decision["graph"]["joints"][0]["parent_link_id"],
            ),
            lambda decision: decision["graph"]["joints"][6].__setitem__(
                "child_link_id",
                decision["graph"]["joints"][0]["child_link_id"],
            ),
            lambda decision: decision["graph"]["joints"][0].__setitem__(
                "parent_link_id", "link-left-6"
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_joint_axis_finiteness_fixed_and_mimic_semantics_deny(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["graph"]["joints"][0].__setitem__(
                "axis_unit", [0.0, 0.0, 2.0]
            ),
            lambda decision: decision["graph"]["joints"][0].__setitem__(
                "origin_xyz_m", [float("inf"), 0.0, 0.0]
            ),
            lambda decision: decision["graph"]["joints"][0].update(
                {"joint_type": "fixed", "activity": "fixed"}
            ),
            lambda decision: decision["graph"]["joints"][0].update(
                {
                    "activity": "mimic",
                    "mimic": {
                        "driver_joint_id": decision["graph"]["joints"][0][
                            "joint_id"
                        ],
                        "multiplier": 1.0,
                        "offset_rad": 0.0,
                    },
                }
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_actuator_identity_coverage_ownership_and_coupling_deny(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["graph"]["actuator_bindings"].pop(),
            lambda decision: decision["graph"]["actuator_bindings"][0].__setitem__(
                "canonical_joint_name", "left_hip_roll"
            ),
            lambda decision: decision["graph"]["ownership"][0].__setitem__(
                "diagnostic_bypass_allowed", True
            ),
            lambda decision: decision["graph"]["actuator_bindings"][1].update(
                {
                    "command_coordinate_joint_id": decision["graph"][
                        "actuator_bindings"
                    ][0]["command_coordinate_joint_id"],
                    "joint_ids": [
                        decision["graph"]["actuator_bindings"][0][
                            "command_coordinate_joint_id"
                        ]
                    ],
                }
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_observation_missing_alias_and_sensor_identity_deny(self):
        base, source = self.accepted_graph_fixture()
        missing = next(
            index
            for index, row in enumerate(
                base["graph"]["observation_bindings"]
            )
            if row["external_sensor_status"] == "missing"
        )
        observed = next(
            index
            for index, row in enumerate(
                base["graph"]["observation_bindings"]
            )
            if row["external_sensor_status"] == "unverified_observation"
        )
        mutations = [
            lambda decision: decision["graph"]["observation_bindings"][
                missing
            ].update(
                {
                    "external_sensor_status": "mapped",
                    "external_sensor_id": "guessed-sensor",
                }
            ),
            lambda decision: decision["graph"]["observation_bindings"][
                observed
            ].__setitem__("external_sensor_id", "wrong-sensor"),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_ros_exact_ten_unique_mapping_and_presence_rules_deny(self):
        base, source = self.accepted_graph_fixture()
        mapped = [
            index
            for index, row in enumerate(base["graph"]["ros_command_bindings"])
            if row["status"] == "mapped"
        ]
        uncommanded = next(
            index
            for index, row in enumerate(base["graph"]["ros_command_bindings"])
            if row["status"] == "uncommanded"
        )
        mutations = [
            lambda decision: decision["graph"]["ros_command_bindings"][
                mapped[1]
            ].__setitem__(
                "ros_joint_id",
                decision["graph"]["ros_command_bindings"][mapped[0]][
                    "ros_joint_id"
                ],
            ),
            lambda decision: decision["graph"]["ros_command_bindings"][
                uncommanded
            ].__setitem__("ros_joint_id", "guessed-joint"),
            lambda decision: decision["graph"]["ros_command_bindings"].pop(),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_reviewer_automation_competence_independence_and_utc_deny(self):
        base, source = self.accepted_graph_fixture()
        mutations = [
            lambda decision: decision["reviewer"].__setitem__(
                "reviewer_id", "codex-automated-reviewer"
            ),
            lambda decision: decision["reviewer"].__setitem__(
                "mechanical_graph_competence_attested", False
            ),
            lambda decision: decision["reviewer"].__setitem__(
                "independence_attested", False
            ),
            lambda decision: decision["reviewer"].__setitem__(
                "reviewed_at", "2026-07-23T01:00:00-07:00"
            ),
            lambda decision: decision["reviewer"].__setitem__(
                "signature_evidence_refs", []
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_digest_subject_admission_support_and_motion_promotion_deny(self):
        base, source = self.accepted_graph_fixture()
        digest = copy.deepcopy(base)
        digest["integrity"]["record_sha256"] = "0" * 64
        with self.assertRaises(manager.GraphReviewError):
            manager.validate_decision(
                digest, accepted_source_decision=source
            )
        mutations = [
            lambda decision: decision["subject"].__setitem__(
                "repository_tree_id", "0" * 40
            ),
            lambda decision: decision.__setitem__(
                "canonical_graph_admissible", False
            ),
            lambda decision: decision.__setitem__("support_granted", True),
            lambda decision: decision.__setitem__(
                "physical_motion_authority", True
            ),
        ]
        for mutation in mutations:
            decision = copy.deepcopy(base)
            self.assert_denied(decision, source, mutation)

    def test_status_schema_is_hash_bound_and_refuses_promotions(self):
        status = json.loads(STATUS_PATH.read_text())
        sources = {row["path"]: row["sha256"] for row in status["sources"]}
        self.assertEqual(
            hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest(),
            sources["generated/dropbear_description/inventory.json"],
        )
        self.assertEqual(0, status["summary"]["accepted_graph_count"])
        self.assertEqual(0, status["summary"]["canonical_graph_count"])
        self.assertEqual(0, status["summary"]["runtime_ros_actuator_mapping_count"])
        validator = Draft202012Validator(STATUS_SCHEMA)
        mutations = [
            lambda value: value["summary"].__setitem__(
                "accepted_graph_count", 1
            ),
            lambda value: value["summary"].__setitem__(
                "canonical_graph_admissible", True
            ),
            lambda value: value.__setitem__("support_granted", True),
            lambda value: value.__setitem__(
                "physical_motion_authority", True
            ),
            lambda value: value["accepted_graph_decision_ids"].append(
                self.template["decision_id"]
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(status)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))

    def test_cli_check_is_read_only_and_canonical(self):
        before = {
            path: path.read_bytes()
            for path in (STATUS_PATH, PACKET_PATH, WORKBENCH_PATH)
        }
        result = subprocess.run(
            ["python3", str(TOOL), "--check"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertIn("questions=161 cohorts=10", result.stdout)
        self.assertIn("accepted=0 canonical=0 mappings=0", result.stdout)
        for path, content in before.items():
            self.assertEqual(content, path.read_bytes())
        self.assertEqual(
            before[STATUS_PATH],
            manager.canonical_bytes(json.loads(before[STATUS_PATH])),
        )


if __name__ == "__main__":
    unittest.main()
