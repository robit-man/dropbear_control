from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "plant_parameter_set_generator_under_test",
    ROOT / "tools/generate_plant_parameter_sets.py",
)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


def stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


PARAMETER_VALUES = {
    "electrical.phase_resistance_ohm": 0.5,
    "electrical.phase_inductance_h": 0.001,
    "electrical.torque_constant_nm_per_a": 0.2,
    "electrical.back_emf_v_s_per_rad": 0.2,
    "electrical.max_qaxis_current_a": 10.0,
    "mechanical.rotor_inertia_kg_m2": 0.001,
    "mechanical.output_inertia_kg_m2": 0.01,
    "mechanical.coulomb_friction_nm": 0.1,
    "mechanical.viscous_friction_nm_s_per_rad": 0.01,
    "transmission.ratio_motor_per_output": 10.0,
    "transmission.forward_efficiency_ratio": 0.9,
    "transmission.reverse_efficiency_ratio": 0.85,
    "transmission.torsional_stiffness_nm_per_rad": 100.0,
    "transmission.backlash_rad": 0.01,
    "saturation.max_motor_speed_rad_s": 100.0,
    "saturation.max_output_speed_rad_s": 10.0,
    "saturation.max_continuous_output_torque_nm": 10.0,
    "saturation.max_peak_output_torque_nm": 20.0,
    "saturation.peak_duration_s": 5.0,
    "thermal.winding_resistance_k_per_w": 1.0,
    "thermal.case_resistance_k_per_w": 2.0,
    "thermal.winding_heat_capacity_j_per_k": 100.0,
    "thermal.case_heat_capacity_j_per_k": 200.0,
    "thermal.max_winding_temperature_k": 400.0,
    "thermal.max_case_temperature_k": 380.0,
    "sensor.position_quantization_rad": 0.001,
    "sensor.position_noise_stddev_rad": 0.0001,
    "sensor.velocity_noise_stddev_rad_s": 0.001,
    "sensor.current_noise_stddev_a": 0.01,
    "latency.command_delay_s": 0.001,
    "latency.current_loop_period_s": 0.001,
    "latency.state_sample_period_s": 0.002,
    "latency.feedback_delay_s": 0.002,
    "latency.delay_jitter_s": 0.0001,
}
ENVELOPE_VALUES = {
    "operating_envelope.supply_voltage_v": (40.0, 52.0),
    "operating_envelope.ambient_temperature_k": (273.15, 323.15),
    "operating_envelope.output_speed_rad_s": (-8.0, 8.0),
    "operating_envelope.output_torque_nm": (-15.0, 15.0),
}


class Fixture:
    def __init__(self) -> None:
        self.catalog = generator.load_catalog()
        self.protocol = json.loads(
            generator.PROTOCOL_REGISTRY.read_text(encoding="utf-8")
        )
        self.parameter_schema = json.loads(
            generator.PLANT_REGISTRY_SCHEMA.read_text(encoding="utf-8")
        )
        self.row = self.catalog[0]
        self.model_key = generator.model_key(
            self.row["series"], self.row["model"]
        )
        self.facts = {
            field_id: self.fact(field_id)
            for field_id in generator.ALL_FIELDS
        }
        self.decision = self.accepted_decision()
        self.protocol["accepted_applicability_decisions"] = [self.decision]
        model = next(
            item
            for item in self.protocol["models"]
            if item["model_key"] == self.model_key
        )
        model["accepted_decision_ids"] = [self.decision["decision_id"]]

    def fact(self, field_id: str) -> dict:
        domain, name = field_id.split(".", 1)
        fact_id = stable_id("plantfact-", field_id)
        unit = {
            **generator.PARAMETER_FIELDS,
            **generator.ENVELOPE_FIELDS,
        }[field_id]
        if field_id in PARAMETER_VALUES:
            value = PARAMETER_VALUES[field_id]
            observation = {
                "shape": "scalar",
                "normalized_value": value,
                "normalized_unit": unit,
            }
            if value == 0.0:
                lower, upper = 0.0, 0.0
            else:
                lower, upper = value * 0.9, value * 1.1
        else:
            lower, upper = ENVELOPE_VALUES[field_id]
            observation = {
                "shape": "range",
                "normalized_minimum": lower,
                "normalized_maximum": upper,
                "normalized_unit": unit,
            }
        return {
            "fact_id": fact_id,
            "model_identity": {
                "model_key": self.model_key,
                "series": self.row["series"],
                "model": self.row["model"],
                "package_revision": self.row["package_revision"],
            },
            "target": {
                "requirement_kind": (
                    "parameter"
                    if field_id in generator.PARAMETER_FIELDS
                    else "operating_envelope"
                ),
                "domain": domain,
                "name": name,
                "canonical_unit": unit,
            },
            "observation": observation,
            "provenance": {
                "document_occurrence_id": stable_id("dococc-", field_id),
                "pdf_page_index": 1,
                "candidate_id": stable_id(
                    "plantspeccandidate-", field_id
                ),
            },
            "evidence": {
                "class": "official_stated",
                "uncertainty": {
                    "class": "source_stated_bound",
                    "lower": lower,
                    "upper": upper,
                    "unit": unit,
                    "coverage_probability": 1.0,
                },
                "operating_condition": {
                    "supply_voltage_v": 48.0,
                    "ambient_temperature_k": 298.15,
                    "rotation_direction": "not_stated",
                    "notes": None,
                },
            },
            "review": {
                "status": "accepted",
                "candidate_decision_registry_generation_sha256": "a" * 64,
                "reviewed_at_utc": "2026-07-23T10:00:00Z",
            },
            "support_granted": False,
            "physical_motion_authority": False,
        }

    def accepted_decision(self, suffix: str = "one") -> dict:
        return {
            "decision_id": stable_id("protocoldecision-", suffix),
            "subject": {
                "model_key": self.model_key,
                "series": self.row["series"],
                "model": self.row["model"],
                "package_revision": self.row["package_revision"],
                "hardware_revision": "drive-rev-a",
                "drive_firmware": "fw-1.2.3",
                "protocol_revision": "V4.4",
                "transport": "classic_can",
                "control_mode": "q-axis-current",
            },
        }

    def inputs(self) -> dict:
        facts = {fact["fact_id"]: fact for fact in self.facts.values()}
        fact_hashes = {
            identifier: generator.sha_bytes(generator.canonical_bytes(fact))
            for identifier, fact in facts.items()
        }
        return {
            "catalog": self.catalog,
            "protocol_registry": self.protocol,
            "candidate_decision_registry": {
                "registry_generation_sha256": "a" * 64
            },
            "facts": facts,
            "fact_hashes": fact_hashes,
            "sources": {
                "catalog_sha256": "1" * 64,
                "protocol_applicability_registry_sha256": "2" * 64,
                "candidate_decision_registry_sha256": "3" * 64,
                "candidate_decision_registry_generation_sha256": "a" * 64,
                "source_fact_schema_sha256": "4" * 64,
                "plant_registry_schema_sha256": "5" * 64,
                "materializer_sha256": "6" * 64,
                "source_fact_file_sha256": fact_hashes,
            },
            "parameter_schema": self.parameter_schema,
        }


class PlantParameterSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tracked = json.loads(
            generator.OUTPUT_REGISTRY.read_text(encoding="utf-8")
        )

    def test_tracked_baseline_is_schema_valid_and_fully_blocked(self) -> None:
        schema = json.loads(generator.REGISTRY_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.tracked)
        value, sets = generator.build()
        generator.validate(value, sets, verify_sources=False)
        self.assertEqual(44, value["summary"]["model_count"])
        self.assertEqual(0, value["summary"]["active_source_fact_count"])
        self.assertEqual(0, value["summary"]["assembled_parameter_set_count"])
        self.assertTrue(
            all(model["assembly_status"] == "blocked" for model in value["models"])
        )

    def test_complete_reviewed_fixture_materializes_one_source_only_set(self) -> None:
        fixture = Fixture()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        generator.validate(value, sets, verify_sources=False)
        self.assertEqual(1, value["summary"]["assembled_parameter_set_count"])
        item = next(iter(sets.values()))
        self.assertEqual("sourced", item["status"])
        self.assertFalse(item["runtime_loadable"])
        self.assertIsNone(item["runtime_adapter_id"])
        self.assertIsNone(item["runtime_contract_id"])
        self.assertFalse(item["support_granted"])
        self.assertFalse(item["physical_motion_authority"])
        self.assertEqual(38, len(item["assembly"]["source_fact_ids"]))
        self.assertEqual(38, len(item["sources"]))
        self.assertEqual("bidirectional", item["operating_envelopes"][0]["rotation_direction"])
        self.assertIn(
            "runtime_plant_adapter_missing", value["models"][0]["blockers"]
        )

    def test_each_missing_field_blocks_materialization(self) -> None:
        for field_id in generator.ALL_FIELDS:
            fixture = Fixture()
            del fixture.facts[field_id]
            value, sets = generator.build_from_inputs(**fixture.inputs())
            with self.subTest(field_id=field_id):
                self.assertFalse(sets)
                model = value["models"][0]
                self.assertIn(field_id, model["missing_field_ids"])
                self.assertIn("source_fact_matrix_incomplete", model["blockers"])

    def test_conflicting_active_fact_for_one_target_is_rejected(self) -> None:
        fixture = Fixture()
        inputs = fixture.inputs()
        duplicate = copy.deepcopy(
            fixture.facts["electrical.phase_resistance_ohm"]
        )
        duplicate["fact_id"] = stable_id("plantfact-", "duplicate")
        inputs["facts"][duplicate["fact_id"]] = duplicate
        inputs["fact_hashes"][duplicate["fact_id"]] = generator.sha_bytes(
            generator.canonical_bytes(duplicate)
        )
        with self.assertRaisesRegex(
            generator.PlantParameterSetError, "conflicting active source facts"
        ):
            generator.build_from_inputs(**inputs)

    def test_wrong_shape_unit_model_and_uncertainty_deny(self) -> None:
        mutations = []
        wrong_shape = Fixture()
        wrong_shape.facts["electrical.phase_resistance_ohm"]["observation"] = {
            "shape": "range",
            "normalized_minimum": 0.4,
            "normalized_maximum": 0.6,
            "normalized_unit": "ohm",
        }
        mutations.append(wrong_shape)
        wrong_unit = Fixture()
        wrong_unit.facts["electrical.phase_inductance_h"]["observation"][
            "normalized_unit"
        ] = "mH"
        mutations.append(wrong_unit)
        wrong_model = Fixture()
        wrong_model.facts["mechanical.rotor_inertia_kg_m2"]["model_identity"][
            "model"
        ] = "X6-60"
        mutations.append(wrong_model)
        outside = Fixture()
        outside.facts["electrical.max_qaxis_current_a"]["evidence"][
            "uncertainty"
        ]["upper"] = 5.0
        mutations.append(outside)
        for index, fixture in enumerate(mutations):
            with self.subTest(index=index):
                value, sets = generator.build_from_inputs(**fixture.inputs())
                self.assertFalse(sets)
                self.assertIn(
                    "parameter_set_semantic_incompatibility",
                    value["models"][0]["blockers"],
                )

    def test_operating_condition_and_direction_conflicts_deny(self) -> None:
        outside = Fixture()
        outside.facts["electrical.phase_resistance_ohm"]["evidence"][
            "operating_condition"
        ]["supply_voltage_v"] = 60.0
        value, sets = generator.build_from_inputs(**outside.inputs())
        self.assertFalse(sets)
        self.assertIn(
            "parameter_set_semantic_incompatibility",
            value["models"][0]["blockers"],
        )
        direction = Fixture()
        direction.facts["operating_envelope.output_torque_nm"]["observation"][
            "normalized_minimum"
        ] = 0.0
        direction.facts["operating_envelope.output_torque_nm"]["evidence"][
            "uncertainty"
        ]["lower"] = 0.0
        value, sets = generator.build_from_inputs(**direction.inputs())
        self.assertFalse(sets)

    def test_cross_field_peak_speed_and_thermal_conflicts_deny(self) -> None:
        cases = []
        peak = Fixture()
        peak.facts["saturation.max_peak_output_torque_nm"]["observation"][
            "normalized_value"
        ] = 5.0
        peak.facts["saturation.max_peak_output_torque_nm"]["evidence"][
            "uncertainty"
        ].update(lower=4.0, upper=6.0)
        cases.append(peak)
        speed = Fixture()
        speed.facts["saturation.max_output_speed_rad_s"]["observation"][
            "normalized_value"
        ] = 5.0
        speed.facts["saturation.max_output_speed_rad_s"]["evidence"][
            "uncertainty"
        ].update(lower=4.0, upper=6.0)
        cases.append(speed)
        thermal = Fixture()
        thermal.facts["thermal.max_case_temperature_k"]["observation"][
            "normalized_value"
        ] = 300.0
        thermal.facts["thermal.max_case_temperature_k"]["evidence"][
            "uncertainty"
        ].update(lower=290.0, upper=310.0)
        cases.append(thermal)
        for index, fixture in enumerate(cases):
            value, sets = generator.build_from_inputs(**fixture.inputs())
            with self.subTest(index=index):
                self.assertFalse(sets)
                self.assertEqual("blocked", value["models"][0]["assembly_status"])

    def test_same_tuple_decisions_coalesce_and_distinct_tuple_splits(self) -> None:
        fixture = Fixture()
        second = fixture.accepted_decision("two")
        fixture.protocol["accepted_applicability_decisions"].append(second)
        model = fixture.protocol["models"][0]
        model["accepted_decision_ids"].append(second["decision_id"])
        model["accepted_decision_ids"].sort()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        self.assertEqual(1, len(sets))
        self.assertEqual(
            2,
            len(next(iter(sets.values()))["assembly"]["accepted_protocol_decision_ids"]),
        )
        third = fixture.accepted_decision("three")
        third["subject"]["drive_firmware"] = "fw-1.2.4"
        fixture.protocol["accepted_applicability_decisions"].append(third)
        model["accepted_decision_ids"].append(third["decision_id"])
        model["accepted_decision_ids"].sort()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        self.assertEqual(2, len(sets))
        self.assertEqual(2, len(value["models"][0]["plant_ids"]))

    def test_fact_or_applicability_revocation_removes_set_and_changes_generation(self) -> None:
        fixture = Fixture()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        self.assertEqual(1, len(sets))
        generation = value["registry_generation_sha256"]
        del fixture.facts["sensor.current_noise_stddev_a"]
        revoked, revoked_sets = generator.build_from_inputs(**fixture.inputs())
        self.assertFalse(revoked_sets)
        self.assertNotEqual(generation, revoked["registry_generation_sha256"])
        fixture = Fixture()
        fixture.protocol["accepted_applicability_decisions"] = []
        fixture.protocol["models"][0]["accepted_decision_ids"] = []
        revoked, revoked_sets = generator.build_from_inputs(**fixture.inputs())
        self.assertFalse(revoked_sets)
        self.assertIn(
            "accepted_protocol_applicability_missing",
            revoked["models"][0]["blockers"],
        )

    def test_registry_digest_summary_and_authority_tamper_are_rejected(self) -> None:
        fixture = Fixture()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        mutations = []
        digest = copy.deepcopy(value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        summary = copy.deepcopy(value)
        summary["summary"]["assembled_parameter_set_count"] = 0
        generator.set_digest(summary)
        mutations.append(summary)
        authority = copy.deepcopy(value)
        authority["support_granted"] = True
        generator.set_digest(authority)
        mutations.append(authority)
        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                generator.PlantParameterSetError
            ):
                generator.validate(mutated, sets, verify_sources=False)

    def test_registry_entry_and_parameter_bytes_are_hash_bound(self) -> None:
        fixture = Fixture()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        broken_sets = copy.deepcopy(sets)
        item = next(iter(broken_sets.values()))
        item["parameters"]["electrical"]["phase_resistance_ohm"]["value"] = 0.6
        with self.assertRaises(generator.PlantParameterSetError):
            generator.validate(value, broken_sets, verify_sources=False)
        broken_registry = copy.deepcopy(value)
        broken_registry["parameter_sets"][0]["parameter_set_sha256"] = "0" * 64
        generator.set_digest(broken_registry)
        with self.assertRaises(generator.PlantParameterSetError):
            generator.validate(broken_registry, sets, verify_sources=False)

    def test_transactional_output_replaces_stale_files(self) -> None:
        fixture = Fixture()
        value, sets = generator.build_from_inputs(**fixture.inputs())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "parameter_sets"
            root.mkdir()
            (root / "stale.txt").write_text("stale", encoding="utf-8")
            original = generator.OUTPUT_ROOT
            try:
                generator.OUTPUT_ROOT = root
                generator._transactional_write(value, sets)
            finally:
                generator.OUTPUT_ROOT = original
            self.assertFalse((root / "stale.txt").exists())
            self.assertEqual(
                set(sets),
                {path.stem for path in (root / "sets").glob("*.json")},
            )


if __name__ == "__main__":
    unittest.main()
