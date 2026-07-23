from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from myactuator_lib.cad_assets import (
    ARTIFACT_NAMES,
    CadAdmissionReason,
    CadAssetSelection,
    CadRegistryError,
    RuntimeCadAssetRegistry,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
DROPBEAR_VIEW_PATH = ROOT / "generated/dropbear/simulator/dropbear_config.json"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def exact_selection(registry: dict, configuration_id: str | None = None) -> CadAssetSelection:
    items = registry["configurations"]
    item = next(
        value
        for value in items
        if configuration_id is None or value["configuration_id"] == configuration_id
    )
    return CadAssetSelection(item["series"], item["model"], item["configuration_id"])


def accepted_fixture(base: dict, root: Path) -> tuple[dict, CadAssetSelection]:
    registry = copy.deepcopy(base)
    item = registry["configurations"][0]
    selection = exact_selection(registry, item["configuration_id"])
    item["selector_status"] = "reviewed"
    item["selector_key"] = "reviewed-test-fixture"
    item["canonical_variant_id"] = item["source_variant_ids"][0]
    item["review_status"] = "accepted_local"
    item["local_runtime_loadable"] = True
    item["browser_loadable"] = False
    item["candidate_reports"] = []
    item["local_assets"] = {}
    directory = Path("released_assets") / item["configuration_id"]
    for index, name in enumerate(ARTIFACT_NAMES, start=1):
        suffix = ".step" if name.endswith("step") else ".glb"
        relative = directory / f"{name}{suffix}"
        payload = f"reviewed-{name}-{index}".encode("ascii")
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        item["local_assets"][name] = {
            "path": relative.as_posix(),
            "sha256": sha256(payload),
            "bytes": len(payload),
        }
    registry["summary"]["accepted_configurations"] = 1
    registry["summary"]["local_runtime_loadable_configurations"] = 1
    registry["summary"]["browser_loadable_configurations"] = 0
    registry["summary"]["candidate_reports"] = sum(
        len(value["candidate_reports"]) for value in registry["configurations"]
    )
    return registry, selection


class HostCadAssetAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.dropbear = json.loads(DROPBEAR_VIEW_PATH.read_text(encoding="utf-8"))

    def test_baseline_denies_every_configuration_and_names_x12_candidate(self) -> None:
        registry = RuntimeCadAssetRegistry(self.baseline, asset_root=ROOT)
        self.assertEqual(registry.configuration_count, 53)
        decisions = [registry.admit(exact_selection(self.baseline, item["configuration_id"])) for item in self.baseline["configurations"]]
        self.assertTrue(all(not decision.allowed for decision in decisions))
        x12 = next(
            decision
            for item, decision in zip(self.baseline["configurations"], decisions)
            if item["model"] == "X12-320"
        )
        self.assertEqual(x12.reason, CadAdmissionReason.CANDIDATE_NOT_REVIEWED)

    def test_exact_id_never_falls_back_across_identity_or_unknown_id(self) -> None:
        registry = RuntimeCadAssetRegistry(self.baseline, asset_root=ROOT)
        selection = exact_selection(self.baseline)
        mismatch = registry.admit(
            CadAssetSelection("wrong-series", selection.model, selection.configuration_id)
        )
        missing = registry.admit(
            CadAssetSelection(selection.series, selection.model, "cadcfg-00000000000000000000")
        )
        self.assertEqual(mismatch.reason, CadAdmissionReason.CONFIGURATION_IDENTITY_MISMATCH)
        self.assertEqual(missing.reason, CadAdmissionReason.CONFIGURATION_NOT_FOUND)

    def test_synthetic_reviewed_artifacts_admit_and_reverify_at_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value, selection = accepted_fixture(self.baseline, root)
            registry = RuntimeCadAssetRegistry(value, asset_root=root)
            decision = registry.admit(selection)
            self.assertTrue(decision.allowed, decision)
            self.assertEqual(decision.reason, CadAdmissionReason.ALLOWED_LOCAL)
            self.assertIsNotNone(decision.assets)
            assert decision.assets is not None
            self.assertEqual(len(decision.assets.artifacts), 5)
            artifact = decision.assets.artifact("housing_glb")
            original = artifact.read_verified()
            self.assertTrue(original)
            artifact.path.write_bytes(original + b"tamper")
            with self.assertRaises(CadRegistryError):
                artifact.read_verified()

    def test_missing_or_changed_artifact_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value, selection = accepted_fixture(self.baseline, root)
            record = value["configurations"][0]["local_assets"]["output_glb"]
            (root / record["path"]).write_bytes(b"changed")
            decision = RuntimeCadAssetRegistry(value, asset_root=root).admit(selection)
            self.assertEqual(decision.reason, CadAdmissionReason.ARTIFACT_MISSING_OR_CHANGED)

    def test_vendor_source_hash_is_denied_even_if_registry_calls_it_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value, selection = accepted_fixture(self.baseline, root)
            item = value["configurations"][0]
            record = item["local_assets"]["housing_step"]
            source = next(
                entry
                for entry in value["source_variants"]
                if entry["variant_id"] == item["canonical_variant_id"]
            )
            source["step_sha256"] = record["sha256"]
            decision = RuntimeCadAssetRegistry(value, asset_root=root).admit(selection)
            self.assertEqual(decision.reason, CadAdmissionReason.SOURCE_ASSET_FORBIDDEN)

    def test_candidate_and_procedural_paths_are_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate, selection = accepted_fixture(self.baseline, root)
            record = candidate["configurations"][0]["local_assets"]["housing_glb"]
            record["path"] = "generated/myactuator/cad/candidate_exports/housing.glb"
            denied = RuntimeCadAssetRegistry(candidate, asset_root=root).admit(selection)
            self.assertEqual(denied.reason, CadAdmissionReason.CANDIDATE_ASSET_FORBIDDEN)

            procedural, selection = accepted_fixture(self.baseline, root)
            procedural["configurations"][0]["local_assets"]["housing_glb"]["path"] = "procedural://housing.glb"
            denied = RuntimeCadAssetRegistry(procedural, asset_root=root).admit(selection)
            self.assertEqual(denied.reason, CadAdmissionReason.ARTIFACT_PATH_INVALID)

    def test_path_traversal_and_symlink_escape_are_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            traversal, selection = accepted_fixture(self.baseline, root)
            traversal["configurations"][0]["local_assets"]["collision_glb"]["path"] = "../escape.glb"
            denied = RuntimeCadAssetRegistry(traversal, asset_root=root).admit(selection)
            self.assertEqual(denied.reason, CadAdmissionReason.ARTIFACT_PATH_INVALID)

            symlinked, selection = accepted_fixture(self.baseline, root)
            outside_path = Path(outside) / "escape.glb"
            outside_path.write_bytes(b"outside")
            link = root / "linked.glb"
            link.symlink_to(outside_path)
            record = symlinked["configurations"][0]["local_assets"]["collision_glb"]
            record.update(path="linked.glb", sha256=sha256(b"outside"), bytes=7)
            denied = RuntimeCadAssetRegistry(symlinked, asset_root=root).admit(selection)
            self.assertEqual(denied.reason, CadAdmissionReason.ARTIFACT_PATH_INVALID)

    def test_malformed_registry_is_rejected_before_queries(self) -> None:
        invalid = copy.deepcopy(self.baseline)
        invalid["policy"]["source_step_is_never_runtime_asset"] = False
        with self.assertRaises(CadRegistryError):
            RuntimeCadAssetRegistry(invalid, asset_root=ROOT)
        invalid = copy.deepcopy(self.baseline)
        invalid["configurations"].append(copy.deepcopy(invalid["configurations"][0]))
        invalid["summary"]["geometry_configurations"] += 1
        with self.assertRaises(CadRegistryError):
            RuntimeCadAssetRegistry(invalid, asset_root=ROOT)

    def test_current_dropbear_binding_is_unverified_even_with_valid_local_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value, selection = accepted_fixture(self.baseline, root)
            decision = RuntimeCadAssetRegistry(value, asset_root=root).admit_dropbear_joint(
                selection, self.dropbear, "left_hip_yaw"
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, CadAdmissionReason.DROPBEAR_BINDING_UNVERIFIED)

    def test_verified_dropbear_binding_can_only_refine_exact_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value, selection = accepted_fixture(self.baseline, root)
            item = value["configurations"][0]
            source = next(
                entry
                for entry in value["source_variants"]
                if entry["variant_id"] == item["canonical_variant_id"]
            )
            asset_id = "cad-asset-test-reviewed"
            value["dropbear"]["bound_cad_asset_ids"] = [asset_id]
            view = copy.deepcopy(self.dropbear)
            dropbear_registry = view["registry"]
            dropbear_registry["cad_assets"] = [
                {
                    "asset_id": asset_id,
                    "model": selection.model,
                    "source_step_sha256": source["step_sha256"],
                    "housing_member": "housing",
                    "output_member": "output",
                    "source_to_robot_transform": [
                        1, 0, 0, 0,
                        0, 1, 0, 0,
                        0, 0, 1, 0,
                        0, 0, 0, 1,
                    ],
                    "review_status": "verified",
                    "source_refs": ["myactuator-step-manifest"],
                }
            ]
            joint = next(
                record
                for record in dropbear_registry["joints"]
                if record["canonical_name"] == "left_hip_yaw"
            )
            joint["cad_binding"] = {
                "asset_id": asset_id,
                "housing_member": "housing",
                "output_member": "output",
                "joint_origin_xyz_m": [0.0, 0.0, 0.0],
                "joint_axis_xyz": [0.0, 0.0, 1.0],
                "status": "verified",
            }
            decision = RuntimeCadAssetRegistry(value, asset_root=root).admit_dropbear_joint(
                selection, view, "left_hip_yaw"
            )
            self.assertTrue(decision.allowed, decision)
            self.assertEqual(decision.dropbear_asset_id, asset_id)
            self.assertEqual(decision.dropbear_joint_name, "left_hip_yaw")


if __name__ == "__main__":
    unittest.main()
