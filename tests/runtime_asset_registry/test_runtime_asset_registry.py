from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_cad_runtime_registry", ROOT / "tools/generate_cad_runtime_registry.py"
)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


class RuntimeAssetRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "generated/myactuator/cad/runtime_asset_registry.json").read_text()
        )
        cls.browser = json.loads(
            (ROOT / "web/assets/cad_support.generated.json").read_text()
        )

    def test_schema_and_exact_baseline(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/myactuator-cad-runtime-asset-registry.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.registry)
        generator.validate_registry(copy.deepcopy(self.registry))
        self.assertEqual(self.registry["summary"]["models"], 44)
        self.assertEqual(self.registry["summary"]["source_variants"], 53)
        self.assertEqual(self.registry["summary"]["geometry_configurations"], 53)
        self.assertEqual(self.registry["summary"]["local_runtime_loadable_configurations"], 0)

    def test_local_only_and_browser_states_are_distinct(self) -> None:
        registry = copy.deepcopy(self.registry)
        item = registry["configurations"][0]
        item["review_status"] = "accepted_local"
        item["local_runtime_loadable"] = True
        item["local_assets"] = {name: {"path": f"local/{name}", "sha256": "a" * 64, "bytes": 1} for name in ("housing_step", "output_step", "housing_glb", "output_glb", "collision_glb")}
        registry["summary"]["accepted_configurations"] = 1
        registry["summary"]["local_runtime_loadable_configurations"] = 1
        generator.validate_registry(registry)
        item["browser_loadable"] = True
        registry["summary"]["browser_loadable_configurations"] = 1
        with self.assertRaises(generator.RuntimeRegistryError):
            generator.validate_registry(registry)

    def test_browser_projection_matches_exact_status_and_redacts_local_assets(self) -> None:
        runtime = {item["configuration_id"]: item for item in self.registry["configurations"]}
        browser = {item["configuration_id"]: item for item in self.browser["configurations"]}
        self.assertEqual(set(runtime), set(browser))
        for configuration_id, local in runtime.items():
            public = browser[configuration_id]
            self.assertEqual(public["review_status"], local["review_status"])
            self.assertEqual(public["browser_loadable"], local["browser_loadable"])
            self.assertNotIn("local_assets", public)
            if not public["browser_loadable"]:
                self.assertIsNone(public["assets"])

    def test_sources_candidates_and_dropbear_remain_denied(self) -> None:
        self.assertTrue(all(not item["source_step_is_runtime_asset"] for item in self.registry["source_variants"]))
        candidates = [candidate for item in self.registry["configurations"] for candidate in item["candidate_reports"]]
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0]["accepted_asset"])
        self.assertFalse(candidates[0]["support_granted"])
        self.assertFalse(self.registry["dropbear"]["motion_enable_allowed"])
        self.assertEqual(self.registry["dropbear"]["bound_cad_asset_ids"], [])


if __name__ == "__main__":
    unittest.main()
