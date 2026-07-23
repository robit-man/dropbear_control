from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_dropbear_graph_v2.py"
STATUS = ROOT / "generated/dropbear_graph_v2/status.json"
DECISION_SCHEMA = json.loads(
    (ROOT / "schemas/dropbear-graph-v2-decision.schema.json").read_text()
)
STATUS_SCHEMA = json.loads(
    (ROOT / "schemas/dropbear-graph-v2-status.schema.json").read_text()
)

spec = importlib.util.spec_from_file_location(
    "dropbear_graph_v2_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


def evidence(label: str):
    return [f"tests/dropbear_graph_v2/synthetic-{label}"]


def transform(parent, xyz=(0.0, 0.0, 0.0)):
    return {
        "expressed_in_parent_frame_id": parent,
        "translation_xyz_m": list(xyz),
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
    }


class DropbearGraphV2Tests(unittest.TestCase):
    def graph(self):
        frames = [
            {
                "frame_id": "base-frame",
                "kind": "base",
                "parent_frame_id": None,
                "chirality": "center",
                "transform": transform(None),
                "source_evidence_refs": evidence("base-frame"),
            },
            {
                "frame_id": "left-prox-frame",
                "kind": "link",
                "parent_frame_id": "base-frame",
                "chirality": "left",
                "transform": transform("base-frame", (0.0, 0.1, 0.0)),
                "source_evidence_refs": evidence("left-prox-frame"),
            },
            {
                "frame_id": "right-prox-frame",
                "kind": "link",
                "parent_frame_id": "base-frame",
                "chirality": "right",
                "transform": transform("base-frame", (0.0, -0.1, 0.0)),
                "source_evidence_refs": evidence("right-prox-frame"),
            },
            {
                "frame_id": "left-toe-frame",
                "kind": "link",
                "parent_frame_id": "left-prox-frame",
                "chirality": "left",
                "transform": transform("left-prox-frame", (0.0, 0.0, -0.2)),
                "source_evidence_refs": evidence("left-toe-frame"),
            },
            {
                "frame_id": "right-toe-frame",
                "kind": "link",
                "parent_frame_id": "right-prox-frame",
                "chirality": "right",
                "transform": transform("right-prox-frame", (0.0, 0.0, -0.2)),
                "source_evidence_refs": evidence("right-toe-frame"),
            },
        ]
        links = [
            {
                "link_id": "base-link",
                "frame_id": "base-frame",
                "chirality": "center",
                "source_evidence_refs": evidence("base-link"),
            }
        ]
        for side in ("left", "right"):
            for part in ("prox", "toe"):
                links.append(
                    {
                        "link_id": f"{side}-{part}-link",
                        "frame_id": f"{side}-{part}-frame",
                        "chirality": side,
                        "source_evidence_refs": evidence(f"{side}-{part}-link"),
                    }
                )
        joints = []
        coordinates = []
        ownership = []
        couplings = []
        singularities = []
        dependencies = []
        actuators = []
        ros_mappings = []
        for side in ("left", "right"):
            drive_joint = f"{side}-drive-joint"
            mimic_joint = f"{side}-mimic-joint"
            drive_coordinate = f"{side}-drive-coordinate"
            mimic_coordinate = f"{side}-mimic-coordinate"
            joints.extend(
                [
                    {
                        "joint_id": drive_joint,
                        "parent_link_id": "base-link",
                        "child_link_id": f"{side}-prox-link",
                        "joint_type": "revolute",
                        "activity": "active",
                        "chirality": side,
                        "origin_frame_id": f"{side}-prox-frame",
                        "axis": {
                            "expressed_in_frame_id": "base-frame",
                            "xyz_unit": [1.0, 0.0, 0.0],
                        },
                        "coordinate_id": drive_coordinate,
                        "source_evidence_refs": evidence(drive_joint),
                    },
                    {
                        "joint_id": mimic_joint,
                        "parent_link_id": f"{side}-prox-link",
                        "child_link_id": f"{side}-toe-link",
                        "joint_type": "revolute",
                        "activity": "mimic",
                        "chirality": side,
                        "origin_frame_id": f"{side}-toe-frame",
                        "axis": {
                            "expressed_in_frame_id": f"{side}-prox-frame",
                            "xyz_unit": [1.0, 0.0, 0.0],
                        },
                        "coordinate_id": mimic_coordinate,
                        "source_evidence_refs": evidence(mimic_joint),
                    },
                ]
            )
            coordinates.extend(
                [
                    {
                        "coordinate_id": drive_coordinate,
                        "joint_id": drive_joint,
                        "classification": "independent",
                        "unit": "rad",
                        "commandable": True,
                    },
                    {
                        "coordinate_id": mimic_coordinate,
                        "joint_id": mimic_joint,
                        "classification": "dependent",
                        "unit": "rad",
                        "commandable": False,
                    },
                ]
            )
            ownership.append(
                {
                    "coordinate_id": drive_coordinate,
                    "writer_kind": "gateway",
                    "writer_id": f"{side}-gateway-writer",
                    "state_policy_id": f"{side}-state-policy",
                    "diagnostic_bypass_allowed": False,
                }
            )
            coupling_id = f"{side}-mimic-coupling"
            couplings.append(
                {
                    "coupling_id": coupling_id,
                    "kind": "mimic",
                    "input_coordinate_ids": [drive_coordinate],
                    "output_coordinate_id": mimic_coordinate,
                    "equation": {
                        "form": "affine",
                        "terms": [
                            {
                                "coordinate_id": drive_coordinate,
                                "coefficient": -1.0 if side == "right" else 1.0,
                            }
                        ],
                        "offset_si": 0.0,
                    },
                    "valid_domain": [
                        {
                            "coordinate_id": drive_coordinate,
                            "lower": -1.0,
                            "upper": 1.0,
                            "unit": "rad",
                        }
                    ],
                    "owner": "physical_mechanism",
                    "source_evidence_refs": evidence(coupling_id),
                }
            )
            singularities.append(
                {
                    "singularity_id": f"{side}-mimic-singularity",
                    "coupling_id": coupling_id,
                    "detection": {
                        "coordinate_id": drive_coordinate,
                        "operator": "abs_gt",
                        "threshold": 0.95,
                        "unit": "rad",
                    },
                    "handling_policy": "fault",
                    "owner": "safety",
                    "evidence_refs": evidence(f"{side}-singularity"),
                }
            )
            dependency_ids = []
            for kind in ("cad", "calibration", "limit", "route"):
                dependency_id = f"{side}-{kind}-dependency"
                dependency_ids.append(dependency_id)
                dependencies.append(
                    {
                        "dependency_id": dependency_id,
                        "kind": kind,
                        "state": "admitted",
                        "subject_id": f"synthetic-{side}-{kind}",
                        "evidence_refs": evidence(dependency_id),
                    }
                )
            actuator_id = f"actuator-{side}-hip-yaw"
            actuators.append(
                {
                    "actuator_id": actuator_id,
                    "chirality": side,
                    "command_coordinate_id": drive_coordinate,
                    "joint_ids": [drive_joint, mimic_joint],
                    "dependency_ids": dependency_ids,
                    "source_evidence_refs": evidence(actuator_id),
                }
            )
            ros_mappings.append(
                {
                    "mapping_id": f"{side}-ros-mapping",
                    "ros_joint_name": f"{side}_hip_yaw_joint",
                    "coordinate_id": drive_coordinate,
                    "actuator_ids": [actuator_id],
                    "status": "mapped",
                    "source_evidence_refs": evidence(f"{side}-ros"),
                }
            )
        symmetry_pairs = []
        for kind, pairs in (
            (
                "link",
                (
                    ("left-prox-link", "right-prox-link"),
                    ("left-toe-link", "right-toe-link"),
                ),
            ),
            (
                "joint",
                (
                    ("left-drive-joint", "right-drive-joint"),
                    ("left-mimic-joint", "right-mimic-joint"),
                ),
            ),
            (
                "actuator",
                (("actuator-left-hip-yaw", "actuator-right-hip-yaw"),),
            ),
        ):
            for index, (left_id, right_id) in enumerate(pairs, 1):
                symmetry_pairs.append(
                    {
                        "symmetry_id": f"{kind}-symmetry-{index}",
                        "entity_kind": kind,
                        "left_id": left_id,
                        "right_id": right_id,
                        "relation": (
                            "transformed" if kind == "joint" else "exact_mirror"
                        ),
                        "reflection_plane": "xz",
                        "coordinate_sign": -1.0 if kind == "joint" else 1.0,
                        "coordinate_offset_si": 0.0,
                        "rationale": f"Synthetic explicit {kind} symmetry.",
                        "evidence_refs": evidence(f"{kind}-symmetry-{index}"),
                    }
                )
        return {
            "graph_id": "dropbeargraphv2-" + "a" * 20,
            "graph_revision": 2,
            "base_frame_id": "base-frame",
            "frames": frames,
            "aliases": [
                {
                    "alias_namespace": "ros",
                    "alias": "left_hip_yaw_joint",
                    "target_kind": "joint",
                    "target_id": "left-drive-joint",
                    "source_evidence_refs": evidence("left-alias"),
                },
                {
                    "alias_namespace": "ros",
                    "alias": "right_hip_yaw_joint",
                    "target_kind": "joint",
                    "target_id": "right-drive-joint",
                    "source_evidence_refs": evidence("right-alias"),
                },
            ],
            "links": links,
            "joints": joints,
            "symmetry_pairs": symmetry_pairs,
            "couplings": couplings,
            "singularities": singularities,
            "closures": [
                {
                    "closure_id": "physical-closure",
                    "kind": "physical_closed_chain",
                    "endpoint_frame_ids": [
                        "left-toe-frame",
                        "right-toe-frame",
                    ],
                    "joint_ids": ["left-mimic-joint", "right-mimic-joint"],
                    "solver_owner": "physical_mechanism",
                    "physical_counterpart_status": "reviewed",
                    "source_evidence_refs": evidence("physical-closure"),
                },
                {
                    "closure_id": "simulator-closure",
                    "kind": "simulator_only",
                    "endpoint_frame_ids": [
                        "left-prox-frame",
                        "right-prox-frame",
                    ],
                    "joint_ids": ["left-drive-joint", "right-drive-joint"],
                    "solver_owner": "rigid_body_simulator",
                    "physical_counterpart_status": "not_applicable",
                    "source_evidence_refs": evidence("simulator-closure"),
                },
            ],
            "dof_ledger": {
                "coordinates": coordinates,
                "summary": {
                    "independent": 2,
                    "dependent": 2,
                    "passive": 0,
                    "fixed": 0,
                    "simulator_only": 0,
                    "total_coordinates": 4,
                    "physical_generalized_dof": 2,
                },
            },
            "ownership": ownership,
            "dependencies": dependencies,
            "actuator_bindings": actuators,
            "ros_mappings": ros_mappings,
        }

    def mutate_rejects(self, mutation):
        value = self.graph()
        mutation(value)
        with self.assertRaises(manager.GraphV2Error):
            manager.validate_graph(value)

    def test_tracked_v1_migration_is_exact_incomplete_and_denial_only(self):
        candidate_path, candidate, status = manager.build()
        manager.validate_decision(candidate)
        manager.validate_status(status, candidate_path, candidate)
        self.assertEqual(
            candidate,
            json.loads(candidate_path.read_text(encoding="utf-8")),
        )
        self.assertEqual(status, json.loads(STATUS.read_text(encoding="utf-8")))
        self.assertEqual(161, candidate["migration"]["unresolved_v1_question_count"])
        self.assertFalse(candidate["migration"]["migration_complete"])
        self.assertEqual([], candidate["graph"]["frames"])
        self.assertIsNone(status["active_graph_decision_id"])
        self.assertEqual(0, status["summary"]["canonical_graph_count"])
        self.assertFalse(status["support_granted"])
        self.assertFalse(status["physical_motion_authority"])

    def test_structured_tree_mimic_symmetry_closures_and_dependencies_pass(self):
        value = self.graph()
        manager.validate_graph(value)
        self.assertEqual(2, value["dof_ledger"]["summary"]["independent"])
        self.assertEqual(2, value["dof_ledger"]["summary"]["dependent"])
        self.assertEqual(
            {"physical_closed_chain", "simulator_only"},
            {row["kind"] for row in value["closures"]},
        )

    def test_frame_cycle_parent_expression_quaternion_and_axis_deny(self):
        mutations = [
            lambda value: value["frames"][0].update(
                parent_frame_id="left-prox-frame",
                transform=transform("left-prox-frame"),
            ),
            lambda value: value["frames"][1]["transform"].__setitem__(
                "expressed_in_parent_frame_id", "right-prox-frame"
            ),
            lambda value: value["frames"][1]["transform"].__setitem__(
                "rotation_xyzw", [0.0, 0.0, 0.0, 2.0]
            ),
            lambda value: value["joints"][0]["axis"].__setitem__(
                "xyz_unit", [2.0, 0.0, 0.0]
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_alias_collision_missing_target_and_chirality_deny(self):
        mutations = [
            lambda value: value["aliases"][1].update(
                alias=value["aliases"][0]["alias"]
            ),
            lambda value: value["aliases"][0].update(target_id="missing-joint"),
            lambda value: value["links"][1].update(chirality="right"),
            lambda value: value["actuator_bindings"][0].update(
                chirality="right"
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_physical_topology_multi_parent_cycle_and_disconnect_deny(self):
        mutations = [
            lambda value: value["joints"][2].update(
                child_link_id="left-prox-link"
            ),
            lambda value: value["joints"][1].update(
                parent_link_id="left-toe-link",
                child_link_id="left-prox-link",
            ),
            lambda value: value["joints"][2].update(
                parent_link_id="right-toe-link",
                child_link_id="right-prox-link",
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_dof_classification_units_counts_and_commandability_deny(self):
        mutations = [
            lambda value: value["dof_ledger"]["coordinates"][0].update(
                classification="passive"
            ),
            lambda value: value["dof_ledger"]["coordinates"][0].update(
                commandable=False
            ),
            lambda value: value["dof_ledger"]["coordinates"][0].update(unit="m"),
            lambda value: value["dof_ledger"]["summary"].update(independent=3),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_structured_coupling_equation_domain_and_output_deny(self):
        mutations = [
            lambda value: value["couplings"][0]["equation"]["terms"][0].update(
                coefficient=0.0
            ),
            lambda value: value["couplings"][0]["equation"]["terms"][0].update(
                coordinate_id="right-drive-coordinate"
            ),
            lambda value: value["couplings"][0]["valid_domain"][0].update(
                lower=1.0, upper=-1.0
            ),
            lambda value: value["couplings"][1].update(
                output_coordinate_id="left-mimic-coordinate"
            ),
            lambda value: value["couplings"][0].update(kind="linear"),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_singularity_and_closure_partition_deny(self):
        mutations = [
            lambda value: value["singularities"][0].update(
                coupling_id="missing-coupling"
            ),
            lambda value: value["singularities"][0]["detection"].update(
                coordinate_id="right-drive-coordinate"
            ),
            lambda value: value["closures"][0].update(
                physical_counterpart_status="missing"
            ),
            lambda value: value["closures"][1].update(
                solver_owner="controller"
            ),
            lambda value: value["closures"][1].update(
                physical_counterpart_status="reviewed"
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_symmetry_coverage_pair_identity_and_intentional_difference_pass(self):
        value = self.graph()
        value["symmetry_pairs"][0].update(
            relation="intentional_difference",
            reflection_plane="not_applicable",
            rationale="Synthetic reviewed asymmetry.",
        )
        manager.validate_graph(value)
        mutations = [
            lambda graph: graph["symmetry_pairs"].pop(),
            lambda graph: graph["symmetry_pairs"][0].update(
                right_id="left-toe-link"
            ),
            lambda graph: graph["symmetry_pairs"][1].update(
                left_id="left-prox-link"
            ),
            lambda graph: graph["symmetry_pairs"][0].update(
                coordinate_sign=0.0
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_ownership_dependency_actuator_and_ros_closure_deny(self):
        mutations = [
            lambda value: value["ownership"].pop(),
            lambda value: value["ownership"][1].update(
                coordinate_id="left-drive-coordinate"
            ),
            lambda value: value["dependencies"][0].update(state="missing"),
            lambda value: value["actuator_bindings"][0]["dependency_ids"].pop(),
            lambda value: value["actuator_bindings"][1].update(
                command_coordinate_id="left-drive-coordinate"
            ),
            lambda value: value["ros_mappings"][1].update(
                ros_joint_name="left_hip_yaw_joint"
            ),
            lambda value: value["ros_mappings"][0].update(
                coordinate_id="left-mimic-coordinate"
            ),
        ]
        for mutation in mutations:
            self.mutate_rejects(mutation)

    def test_generic_fixture_cannot_claim_canonical_dropbear_graph(self):
        with self.assertRaises(manager.GraphV2Error):
            manager.validate_graph(self.graph(), require_dropbear=True)

    def test_decision_subject_migration_digest_review_and_acceptance_deny(self):
        baseline = manager.template()
        mutations = [
            lambda value: value["subject"].__setitem__(
                "source_registry_generation_sha256", "0" * 64
            ),
            lambda value: value["migration"].update(
                resolved_v1_question_count=1
            ),
            lambda value: value["migration"].update(migration_complete=True),
            lambda value: value["integrity"].__setitem__(
                "record_sha256", "0" * 64
            ),
        ]
        for mutation in mutations:
            value = copy.deepcopy(baseline)
            mutation(value)
            if value["integrity"]["record_sha256"] != "0" * 64:
                manager.set_digest(value)
            with self.assertRaises(manager.GraphV2Error):
                manager.validate_decision(value)

        promoted = copy.deepcopy(baseline)
        promoted["record_state"] = "submitted"
        promoted["reviewer"] = {
            "reviewer_id": "independent-mechanical-reviewer",
            "organization_or_team": "external-mechanical-team",
            "mechanical_graph_competence_attested": True,
            "independence_attested": True,
            "reviewed_at": "2026-07-23T18:00:00Z",
            "review_assertion": "Synthetic acceptance attempt.",
            "signature_evidence_refs": evidence("reviewer"),
        }
        promoted["disposition"] = "accept_graph"
        promoted["decision_complete"] = True
        promoted["canonical_graph_admissible"] = True
        promoted["migration"].update(
            resolved_v1_question_count=161,
            unresolved_v1_question_count=0,
            migration_complete=True,
            evidence_refs=evidence("migration"),
        )
        promoted["graph"] = self.graph()
        manager.set_digest(promoted)
        with self.assertRaises(manager.GraphV2Error):
            manager.validate_decision(promoted)

    def test_schema_strictness_status_digest_and_cli_check(self):
        bad = manager.template()
        bad["graph"]["inferred_aliases"] = []
        validator = Draft202012Validator(DECISION_SCHEMA)
        self.assertTrue(list(validator.iter_errors(bad)))

        status = json.loads(STATUS.read_text())
        changed = copy.deepcopy(status)
        changed["summary"]["frame_count"] = 1
        self.assertTrue(
            list(Draft202012Validator(STATUS_SCHEMA).iter_errors(changed))
        )
        changed = copy.deepcopy(status)
        changed["blockers"][0] = "forged"
        with self.assertRaises(manager.GraphV2Error):
            manager.validate_status(
                changed,
                ROOT / status["candidate"]["path"],
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
        self.assertIn("canonical=0", result.stdout)
        self.assertIn("support=false motion=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
