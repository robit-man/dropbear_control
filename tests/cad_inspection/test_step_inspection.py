from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "inspect_step_sources", ROOT / "tools" / "inspect_step_sources.py"
)
assert SPEC is not None and SPEC.loader is not None
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


def step_file(*entities: bytes, schema: bytes = b"CONFIG_CONTROL_DESIGN") -> bytes:
    return b"\n".join(
        (
            b"ISO-10303-21;",
            b"HEADER;",
            b"FILE_DESCRIPTION(('synthetic'),'2;1');",
            b"FILE_SCHEMA(('" + schema + b"'));",
            b"ENDSEC;",
            b"DATA;",
            *entities,
            b"ENDSEC;",
            b"END-ISO-10303-21;",
            b"",
        )
    )


def row_for(data: bytes, structure: str = "flattened") -> dict[str, str]:
    return {
        "series": "TEST",
        "model": "T-1",
        "vendor_relative_path": "TEST/T-1/vendor/model.step",
        "step_sha256": hashlib.sha256(data).hexdigest(),
        "bytes": str(len(data)),
        "step_structure": structure,
        "simulation_review": "unreviewed",
        "output_member": "not_separately_named",
        "axis_origin_units_review": "unreviewed",
        "redistribution_status": "license_review_required",
    }


class StaticInspectionTests(unittest.TestCase):
    def test_flattened_metre_source_remains_unreviewed_and_unsupported(self) -> None:
        data = step_file(
            b"#1=PRODUCT('Motor','','',());",
            b"#2=SI_UNIT($,.METRE.);",
            b"#3=CARTESIAN_POINT('',(1.0,-2.5,3.25));",
            b"#4=MANIFOLD_SOLID_BREP('',#5);",
        )
        result = inspector.inspect_bytes(row_for(data), data)
        self.assertEqual(result["length_unit_candidate"], "metre")
        self.assertFalse(result["length_unit_reviewed"])
        self.assertFalse(result["simulation_supported"])
        self.assertEqual(result["cartesian_points"]["untransformed_min"], [1.0, -2.5, 3.25])
        self.assertFalse(result["cartesian_points"]["authoritative_bounding_box"])

    def test_assembly_relationship_resolves_candidate_product_names(self) -> None:
        data = step_file(
            b"#1=PRODUCT('Housing','','',());",
            b"#2=PRODUCT('Output flange','','',());",
            b"#3=PRODUCT_DEFINITION_FORMATION('','',#1);",
            b"#4=PRODUCT_DEFINITION_FORMATION('','',#2);",
            b"#5=PRODUCT_DEFINITION('','',#3,#20);",
            b"#6=PRODUCT_DEFINITION('','',#4,#20);",
            b"#7=NEXT_ASSEMBLY_USAGE_OCCURRENCE('NAUO1','','',#5,#6,$);",
            b"#8=SI_UNIT(.MILLI.,.METRE.);",
        )
        result = inspector.inspect_bytes(row_for(data, "assembly"), data)
        self.assertEqual(result["length_unit_candidate"], "millimetre")
        self.assertEqual(len(result["assembly_relationships"]), 1)
        relationship = result["assembly_relationships"][0]
        self.assertEqual(relationship["relating_product_name"], "Housing")
        self.assertEqual(relationship["related_product_name"], "Output flange")
        self.assertFalse(result["output_member_identified"])

    def test_gb18030_name_is_retained_raw_and_decoded_as_candidate(self) -> None:
        name = "输出法兰".encode("gb18030")
        data = step_file(
            b"#1=PRODUCT('" + name + b"','','',());",
            b"#2=SI_UNIT(.MILLI.,.METRE.);",
        )
        result = inspector.inspect_bytes(row_for(data), data)
        product = result["products"][0]
        self.assertEqual(product["decoded"], "输出法兰")
        self.assertEqual(product["encoding"], "gb18030")
        self.assertEqual(product["raw_latin1"].encode("latin-1"), name)

    def test_mixed_length_contexts_are_ambiguous_not_defaulted(self) -> None:
        data = step_file(
            b"#1=SI_UNIT(.MILLI.,.METRE.);",
            b"#2=SI_UNIT($,.METRE.);",
        )
        result = inspector.inspect_bytes(row_for(data), data)
        self.assertEqual(result["length_unit_candidate"], "ambiguous")
        self.assertFalse(result["length_unit_reviewed"])

    def test_hash_byte_structure_and_part21_boundaries_fail_closed(self) -> None:
        data = step_file(b"#1=SI_UNIT(.MILLI.,.METRE.);")
        cases = []
        bad_hash = row_for(data)
        bad_hash["step_sha256"] = "0" * 64
        cases.append((bad_hash, data))
        bad_bytes = row_for(data)
        bad_bytes["bytes"] = str(len(data) + 1)
        cases.append((bad_bytes, data))
        bad_structure = row_for(data, "assembly")
        cases.append((bad_structure, data))
        missing_header = data.replace(b"ISO-10303-21;", b"NOT-A-STEP-FILE")
        cases.append((row_for(missing_header), missing_header))
        missing_trailer = data.replace(b"END-ISO-10303-21;", b"END")
        cases.append((row_for(missing_trailer), missing_trailer))
        for row, payload in cases:
            with self.subTest(path=row["vendor_relative_path"]):
                with self.assertRaises(inspector.InspectionError):
                    inspector.inspect_bytes(row, payload)

    def test_variant_id_includes_path_so_duplicate_geometry_stays_distinct(self) -> None:
        data = step_file(b"#1=SI_UNIT(.MILLI.,.METRE.);")
        first = row_for(data)
        second = dict(first)
        second["vendor_relative_path"] = "TEST/T-1/vendor/copy.step"
        self.assertEqual(first["step_sha256"], second["step_sha256"])
        self.assertNotEqual(inspector.variant_id(first), inspector.variant_id(second))


class TrackedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = inspector.read_manifest()
        cls.path = ROOT / "generated" / "myactuator" / "cad" / "step_inspection.json"
        cls.report = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_report_joins_all_sources_without_support_promotion(self) -> None:
        inspector.validate_report_against_manifest(self.report, self.rows)
        summary = self.report["summary"]
        self.assertEqual(summary["models"], 44)
        self.assertEqual(summary["variants"], 53)
        self.assertEqual(summary["unique_step_hashes"], 48)
        self.assertEqual(summary["duplicate_hash_groups"], 5)
        self.assertEqual(summary["simulation_supported_models"], 0)

    def test_exact_unit_outlier_is_explicit_but_not_reviewed(self) -> None:
        outliers = [
            item
            for item in self.report["variants"]
            if item["length_unit_candidate"] != "millimetre"
        ]
        self.assertEqual([(item["series"], item["model"]) for item in outliers], [("FL-FLO", "FL-85-23")])
        self.assertEqual(outliers[0]["length_unit_candidate"], "metre")
        self.assertFalse(outliers[0]["length_unit_reviewed"])

    def test_duplicate_hash_group_does_not_collapse_variant_provenance(self) -> None:
        groups = self.report["duplicate_geometry_groups"]
        self.assertEqual(len(groups), 5)
        self.assertTrue(all(len(group["variant_ids"]) == 2 for group in groups))
        all_ids = [item["variant_id"] for item in self.report["variants"]]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_static_report_cannot_be_mutated_into_geometry_authority(self) -> None:
        promoted = copy.deepcopy(self.report)
        promoted["variants"][0]["output_member_identified"] = True
        with self.assertRaises(inspector.InspectionError):
            inspector.validate_report_against_manifest(promoted, self.rows)

    def test_report_is_canonical_json(self) -> None:
        self.assertEqual(self.path.read_text(encoding="utf-8"), inspector.canonical_json(self.report))


if __name__ == "__main__":
    unittest.main(verbosity=2)

