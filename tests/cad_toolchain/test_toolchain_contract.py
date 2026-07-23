from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ToolchainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock_path = ROOT / "tools" / "cad-toolchain-lock.json"
        cls.lock = json.loads(cls.lock_path.read_text(encoding="utf-8"))
        cls.proof = json.loads(
            (ROOT / "generated" / "myactuator" / "cad" / "toolchain_proof.json").read_text(
                encoding="utf-8"
            )
        )

    def test_toolchain_is_exact_platform_specific_and_hash_pinned(self) -> None:
        self.assertEqual(self.lock["environment"]["python_major_minor"], "3.12")
        self.assertEqual(self.lock["environment"]["machine"], "x86_64")
        self.assertEqual(self.lock["kernel"]["occt_version"], "7.9.3.1")
        requirements = ROOT / self.lock["packages"]["requirements_lock"]
        wheels = ROOT / self.lock["packages"]["wheel_lock"]
        self.assertEqual(
            hashlib.sha256(requirements.read_bytes()).hexdigest(),
            self.lock["packages"]["requirements_lock_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(wheels.read_bytes()).hexdigest(),
            self.lock["packages"]["wheel_lock_sha256"],
        )
        self.assertEqual(sum(1 for line in wheels.read_text().splitlines()[1:] if line), 44)

    def test_glb_scaling_is_explicit_not_an_exporter_default(self) -> None:
        mesh = self.lock["mesh"]
        self.assertEqual(mesh["occt_internal_length_unit"], "MM")
        self.assertEqual(mesh["explicit_shape_scale_to_glb_metres"], 0.001)
        self.assertEqual(mesh["glb_coordinate_unit"], "metre")
        for result in (
            self.proof["glb"]["housing"],
            self.proof["glb"]["output_zero"],
            self.proof["glb"]["output_rotated"],
        ):
            self.assertLess(result["coordinate_abs_max_m"], 0.1)

    def test_synthetic_proof_moves_only_output_and_round_trips(self) -> None:
        articulation = self.proof["articulation"]
        self.assertTrue(articulation["housing_fixed"])
        self.assertTrue(articulation["output_vertices_follow_rigid_rotation"])
        self.assertTrue(articulation["output_volume_preserved"])
        self.assertNotEqual(
            self.proof["geometry"]["output_centroid_zero_mm"],
            self.proof["geometry"]["output_centroid_rotated_mm"],
        )
        self.assertTrue(self.proof["step_round_trip"]["valid_breps"])

    def test_proof_carries_no_vendor_or_support_authority(self) -> None:
        self.assertEqual(self.proof["evidence_class"], "offline-synthetic-cad")
        self.assertFalse(self.proof["source_is_vendor_geometry"])
        self.assertFalse(self.proof["motor_model_supported"])
        self.assertFalse(self.proof["physical_or_plant_evidence"])
        limits = self.lock["authority_limits"]
        self.assertTrue(all(value is False for value in limits.values()))

    def test_proof_is_bound_to_exact_toolchain_lock(self) -> None:
        self.assertEqual(
            self.proof["toolchain_lock_sha256"],
            hashlib.sha256(self.lock_path.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

