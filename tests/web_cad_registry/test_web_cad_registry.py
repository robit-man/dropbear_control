from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_web_cad_registry", ROOT / "tools/generate_web_cad_registry.py"
)
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)


class WebCadRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "web/assets/cad_support.generated.json").read_text()
        )

    def test_registry_covers_exact_sources_and_exposes_no_asset(self) -> None:
        generator.validate_registry(copy.deepcopy(self.registry))
        self.assertEqual(self.registry["summary"]["models"], 44)
        self.assertEqual(self.registry["summary"]["source_variants"], 53)
        self.assertEqual(self.registry["summary"]["geometry_configurations"], 53)
        self.assertEqual(self.registry["summary"]["accepted_configurations"], 0)
        self.assertEqual(self.registry["summary"]["browser_loadable_configurations"], 0)
        self.assertTrue(all(item["assets"] is None for item in self.registry["configurations"]))

    def test_real_candidate_stays_unloadable(self) -> None:
        candidates = [
            (configuration, candidate)
            for configuration in self.registry["configurations"]
            for candidate in configuration["candidate_reports"]
        ]
        self.assertEqual(len(candidates), 1)
        configuration, candidate = candidates[0]
        self.assertFalse(configuration["browser_loadable"])
        self.assertFalse(candidate["accepted_asset"])
        self.assertFalse(candidate["support_granted"])
        self.assertGreater(candidate["unresolved_question_count"], 0)

    def test_dropbear_incomplete_view_cannot_bind_cad(self) -> None:
        self.assertFalse(self.registry["dropbear"]["motion_enable_allowed"])
        self.assertEqual(self.registry["dropbear"]["bound_cad_asset_ids"], [])
        self.assertEqual(self.registry["summary"]["dropbear_bound_cad_assets"], 0)

    def test_unreviewed_browser_exposure_is_rejected(self) -> None:
        tampered = copy.deepcopy(self.registry)
        item = tampered["configurations"][0]
        item["browser_loadable"] = True
        item["assets"] = {
            "housing_glb": {},
            "output_glb": {},
            "collision_glb": {},
        }
        with self.assertRaises(generator.RegistryError):
            generator.validate_registry(tampered)


if __name__ == "__main__":
    unittest.main()
