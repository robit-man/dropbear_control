from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/offline_gate_report.py"
SCHEMA = json.loads((ROOT / "schemas/offline-gate-report.schema.json").read_text())

spec = importlib.util.spec_from_file_location("offline_gate_report_test_module", TOOL)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class OfflineGateReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.temporary.name) / "report.json"
        module.atomic_write(self.path, module.initial_report())

    def tearDown(self):
        self.temporary.cleanup()

    def load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_initial_report_binds_workspace_tools_artifacts_and_false_claims(self):
        value = self.load()
        self.assertEqual("RUNNING", value["result"])
        self.assertTrue(value["workspace_identity"]["source_manifest_file_count"])
        self.assertEqual(45, len(value["artifact_hashes"]))
        self.assertEqual(
            53,
            value["claim_invariants"]["download_index_archive_url_count"],
        )
        self.assertTrue(
            value["claim_invariants"]["download_index_tracked_exact_match"]
        )
        self.assertEqual(
            17,
            value["claim_invariants"]["reviewer_role_count"],
        )
        self.assertEqual(
            145,
            value["claim_invariants"]["evidence_review_queue_item_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "evidence_review_queue_physical_action_count"
            ],
        )
        self.assertEqual(
            97,
            value["claim_invariants"]["evidence_intake_packet_count"],
        )
        self.assertEqual(
            85,
            value["claim_invariants"]["evidence_intake_ready_packet_count"],
        )
        self.assertEqual(
            12,
            value["claim_invariants"]["evidence_intake_blocked_packet_count"],
        )
        self.assertEqual(
            2361,
            value["claim_invariants"]["evidence_intake_task_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "evidence_intake_physical_action_count"
            ],
        )
        self.assertEqual(
            77,
            value["claim_invariants"]["coverage_requirement_count"],
        )
        self.assertEqual(
            140,
            value["claim_invariants"]["coverage_catalog_test_count"],
        )
        self.assertEqual(
            105,
            value["claim_invariants"]["coverage_exists_offline_test_count"],
        )
        self.assertEqual(
            28,
            value["claim_invariants"]["coverage_planned_test_count"],
        )
        self.assertEqual(
            7,
            value["claim_invariants"]["coverage_physical_hold_test_count"],
        )
        self.assertEqual(
            3,
            value["claim_invariants"][
                "coverage_objective_criterion_met_count"
            ],
        )
        self.assertFalse(
            value["claim_invariants"][
                "coverage_objective_evidence_complete"
            ]
        )
        self.assertFalse(
            value["claim_invariants"]["coverage_release_authorized"]
        )
        self.assertEqual(
            9,
            value["claim_invariants"]["claim_surface_lexical_rule_count"],
        )
        self.assertEqual(
            3,
            value["claim_invariants"]["claim_surface_structured_rule_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["claim_surface_finding_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["claim_surface_exception_count"],
        )
        self.assertTrue(value["claim_invariants"]["claim_surface_passed"])
        self.assertEqual(
            44,
            value["claim_invariants"]["protocol_applicability_model_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "accepted_protocol_applicability_count"
            ],
        )
        self.assertEqual(
            53,
            value["claim_invariants"]["cad_campaign_configuration_count"],
        )
        self.assertEqual(
            689,
            value["claim_invariants"][
                "cad_campaign_unanswered_question_count"
            ],
        )
        self.assertEqual(
            1496,
            value["claim_invariants"][
                "plant_model_parameter_requirement_count"
            ],
        )
        self.assertEqual(
            176,
            value["claim_invariants"][
                "plant_model_operating_envelope_requirement_count"
            ],
        )
        self.assertEqual(
            15,
            value["claim_invariants"]["plant_spec_manual_occurrence_count"],
        )
        self.assertEqual(
            215,
            value["claim_invariants"]["plant_spec_page_count"],
        )
        self.assertEqual(
            44,
            value["claim_invariants"]["plant_spec_model_count"],
        )
        self.assertEqual(
            531,
            value["claim_invariants"]["plant_spec_candidate_count"],
        )
        self.assertEqual(
            89,
            value["claim_invariants"][
                "plant_spec_direct_mapping_candidate_count"
            ],
        )
        self.assertEqual(
            317,
            value["claim_invariants"][
                "plant_spec_semantic_review_candidate_count"
            ],
        )
        self.assertEqual(
            125,
            value["claim_invariants"]["plant_spec_unmapped_candidate_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_spec_accepted_candidate_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_spec_runtime_admissible_candidate_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_candidate_submission_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_candidate_event_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_candidate_active_source_fact_count"
            ],
        )
        self.assertFalse(
            value["claim_invariants"][
                "plant_candidate_reviewer_assignment_complete"
            ]
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_parameter_set_assembled_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_parameter_set_assembled_model_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_parameter_set_runtime_loadable_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_runtime_profile_submission_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_runtime_contract_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_runtime_loadable_parameter_set_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_runtime_loadable_model_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_runtime_physically_validated_contract_count"
            ],
        )
        self.assertEqual(
            38,
            value["claim_invariants"]["plant_runtime_source_semantic_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_runtime_v2_profile_submission_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_runtime_v2_contract_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "plant_runtime_v2_loadable_model_count"
            ],
        )
        self.assertEqual(
            38,
            value["claim_invariants"][
                "plant_runtime_v2_source_semantic_count"
            ],
        )
        self.assertEqual(
            "semi-implicit-euler-event-scheduled-v2",
            value["claim_invariants"]["plant_runtime_v2_solver_id"],
        )
        self.assertEqual(
            "sha256-box-muller-counter-v1",
            value["claim_invariants"]["plant_runtime_v2_noise_algorithm"],
        )
        self.assertEqual(
            "sha256-bounded-uniform-counter-v1",
            value["claim_invariants"]["plant_runtime_v2_jitter_algorithm"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["plant_accepted_source_fact_count"],
        )
        self.assertEqual(
            44, value["claim_invariants"]["simulator_runtime_model_count"]
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["exact_model_simulation_ready_count"],
        )
        self.assertEqual(
            10,
            value["claim_invariants"][
                "rigid_body_benchmark_passed_case_count"
            ],
        )
        self.assertEqual(
            764,
            value["claim_invariants"]["rigid_body_trace_event_count"],
        )
        self.assertTrue(
            value["claim_invariants"]["generic_rigid_body_fixture_passed"]
        )
        self.assertFalse(
            value["claim_invariants"][
                "dropbear_production_rigid_body_engine_selected"
            ]
        )
        self.assertEqual(
            10,
            value["claim_invariants"]["ros2_cpp_handoff_passed_case_count"],
        )
        self.assertEqual(
            6,
            value["claim_invariants"]["ros2_cpp_parity_line_count"],
        )
        self.assertTrue(
            value["claim_invariants"]["ros2_cpp_handoff_compiles"]
        )
        self.assertTrue(
            value["claim_invariants"]["ros2_cpp_semantic_parity"]
        )
        self.assertTrue(value["claim_invariants"]["ros2_cpp_plugin_loads"])
        self.assertTrue(value["claim_invariants"]["ros2_cpp_fail_closed"])
        self.assertFalse(
            value["claim_invariants"]["ros2_cpp_physical_adapter_present"]
        )
        self.assertEqual(
            1,
            value["claim_invariants"]["security_platform_profile_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "security_platform_selected_profile_count"
            ],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["security_trust_anchor_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"]["security_key_assignment_count"],
        )
        self.assertEqual(
            0,
            value["claim_invariants"][
                "security_private_key_material_count"
            ],
        )
        self.assertFalse(
            value["claim_invariants"][
                "security_observed_secure_boot_enabled"
            ]
        )
        self.assertTrue(
            value["claim_invariants"][
                "security_observed_legacy_tls_enabled"
            ]
        )
        self.assertFalse(
            value["claim_invariants"][
                "security_authenticated_transport_adapter_present"
            ]
        )
        self.assertFalse(
            value["claim_invariants"][
                "security_signed_artifact_verifier_adapter_present"
            ]
        )
        self.assertFalse(value["evidence_class"]["physical_evidence_present"])
        self.assertFalse(value["claim_invariants"]["motion_enable_allowed"])
        module.validate(value)

    def test_pass_finalization_requires_all_executed_stages_to_pass(self):
        module.stage_start(self.path, "one", "true")
        module.stage_end(self.path, "one", "PASS", 0)
        module.stage_start(self.path, "two", "true")
        module.stage_end(self.path, "two", "PASS", 0)
        module.finalize(self.path, "PASS", 0, None)
        value = self.load()
        self.assertEqual("PASS", value["result"])
        self.assertEqual(["PASS", "PASS"], [row["result"] for row in value["stages"]])

    def test_failure_preserves_prior_pass_and_exact_failed_stage(self):
        module.stage_start(self.path, "completed", "true")
        module.stage_end(self.path, "completed", "PASS", 0)
        module.stage_start(self.path, "failed", "false")
        module.stage_end(self.path, "failed", "FAIL", 23)
        module.finalize(self.path, "FAIL", 23, "failed")
        value = self.load()
        self.assertEqual("FAIL", value["result"])
        self.assertEqual("failed", value["failure_stage"])
        self.assertEqual(23, value["exit_code"])
        self.assertEqual("PASS", value["stages"][0]["result"])
        self.assertEqual("FAIL", value["stages"][1]["result"])

    def test_denied_stage_does_not_allow_false_pass(self):
        module.stage_start(self.path, "failed", "false")
        module.stage_end(self.path, "failed", "FAIL", 1)
        with self.assertRaises(module.GateReportError):
            module.finalize(self.path, "PASS", 0, None)
        self.assertEqual("RUNNING", self.load()["result"])

    def test_stage_order_duplicate_and_completion_mismatch_deny(self):
        module.stage_start(self.path, "one", "true")
        with self.assertRaises(module.GateReportError):
            module.stage_start(self.path, "two", "true")
        with self.assertRaises(module.GateReportError):
            module.stage_end(self.path, "other", "PASS", 0)
        module.stage_end(self.path, "one", "PASS", 0)
        with self.assertRaises(module.GateReportError):
            module.stage_start(self.path, "one", "true")

    def test_schema_rejects_physical_support_cad_plant_mapping_and_motion_claims(self):
        baseline = self.load()
        mutations = [
            lambda value: value["evidence_class"].__setitem__(
                "physical_evidence_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "supported_catalog_model_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "download_index_tracked_exact_match", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "reviewer_assigned_role_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_review_queue_item_count", 144
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_review_queue_physical_action_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_intake_packet_count", 96
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_intake_task_count", 2360
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_intake_accepted_packet_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "evidence_intake_physical_action_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_requirement_count", 76
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_exists_offline_test_count", 89
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_planned_test_count", 36
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_objective_criterion_met_count", 4
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_objective_evidence_complete", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "coverage_release_authorized", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "claim_surface_finding_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "claim_surface_exception_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "claim_surface_passed", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "accepted_protocol_applicability_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "accepted_cad_configuration_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "cad_campaign_unanswered_question_count", 688
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "real_plant_parameter_set_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_source_fact_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_missing_parameter_requirement_count", 1495
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_spec_candidate_count", 530
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_spec_accepted_candidate_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_spec_runtime_admissible_candidate_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_candidate_accepted_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_candidate_reviewer_assignment_complete", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_parameter_set_assembled_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_profile_submission_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_contract_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_loadable_parameter_set_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_loadable_model_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_physically_validated_contract_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_source_semantic_count", 37
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_profile_submission_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_contract_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_loadable_model_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_source_semantic_count", 37
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_solver_id", "other-solver"
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_noise_algorithm", "other-noise"
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "plant_runtime_v2_jitter_algorithm", "other-jitter"
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "exact_model_simulation_ready_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "browser_articulated_asset_ready_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_whole_robot_simulation_ready_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "rigid_body_benchmark_passed_case_count", 9
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "rigid_body_trace_event_count", 763
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "generic_rigid_body_fixture_passed", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_production_rigid_body_engine_selected", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "ros2_cpp_handoff_passed_case_count", 9
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "ros2_cpp_parity_line_count", 5
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "ros2_cpp_handoff_compiles", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "ros2_cpp_semantic_parity", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "ros2_cpp_physical_adapter_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_ros_actuator_mapping_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_graph_accepted_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_source_registry_active_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_graph_registry_active_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_graph_unanswered_question_count", 160
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "dropbear_graph_transform_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "selected_can_controller_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "selected_can_adapter_manifest_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "physical_can_adapter_factory_enabled", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_platform_selected_profile_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_trust_anchor_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_private_key_material_count", 1
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_observed_secure_boot_enabled", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_observed_legacy_tls_enabled", False
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_authenticated_transport_adapter_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_signed_artifact_verifier_adapter_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_persistent_replay_adapter_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_durable_audit_adapter_present", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "security_physical_io_enabled", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "unpowered_discovery_ready_for_execution", True
            ),
            lambda value: value["claim_invariants"].__setitem__(
                "motion_enable_allowed", True
            ),
        ]
        validator = Draft202012Validator(SCHEMA)
        for mutation in mutations:
            value = copy.deepcopy(baseline)
            mutation(value)
            self.assertTrue(list(validator.iter_errors(value)))

    def test_atomic_file_is_canonical_json(self):
        raw = self.path.read_bytes()
        value = json.loads(raw)
        self.assertEqual(module.canonical(value), raw)


if __name__ == "__main__":
    unittest.main()
