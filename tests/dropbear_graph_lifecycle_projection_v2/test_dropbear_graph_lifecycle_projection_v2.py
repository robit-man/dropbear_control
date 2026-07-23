from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from myactuator_lib.dropbear_graph_lifecycle_v2 import (
    DropbearGraphLifecycleProjectionSetV2,
    GraphLifecycleAdmissionError,
)
from tests.dropbear_graph_registry_v2 import (
    test_dropbear_graph_registry_v2 as registry_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_dropbear_graph_lifecycle_projections_v2.py"
OUTPUT_ROOT = ROOT / "generated/dropbear_graph_lifecycle_projection_v2"

spec = importlib.util.spec_from_file_location(
    "dropbear_graph_lifecycle_projection_v2_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class DropbearGraphLifecycleProjectionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registry_fixtures.DropbearGraphRegistryV2Tests.setUpClass()

    def fixture(self):
        return registry_fixtures.DropbearGraphRegistryV2Tests()

    def accepted(self, marker="accepted"):
        case = self.fixture()
        source = case.active_source_registry()
        envelope = case.envelope(marker, source)
        accept = case.event(
            envelope, source, "accept", 1, "2026-07-23T13:20:00Z"
        )
        registry = case.build_case(source, [envelope], [accept])
        return case, source, envelope, registry

    def consumer(self, values, registry):
        return DropbearGraphLifecycleProjectionSetV2(
            values,
            json.loads(manager.SCHEMA.read_text()),
            registry,
            json.loads(registry_fixtures.manager.REGISTRY_SCHEMA.read_text()),
            manager.canonical_bytes(registry),
        )

    def test_tracked_four_views_are_hash_bound_equal_and_denial_only(self):
        values = manager.build()
        manager.validate_projection_set(values)
        for kind in manager.VIEW_KINDS:
            self.assertEqual(
                values[kind],
                json.loads((OUTPUT_ROOT / f"{kind}.json").read_text()),
            )
            self.assertTrue(values[kind]["outputs"]["status_only"])
            self.assertFalse(values[kind]["support_granted"])
            self.assertFalse(values[kind]["physical_motion_authority"])
        self.assertEqual("absent", values["host"]["lifecycle"]["source_active_state"])
        self.assertEqual("absent", values["host"]["lifecycle"]["graph_active_state"])
        self.assertEqual(0, values["host"]["graph_summary"]["frame_count"])
        self.assertEqual(0, values["ui"]["outputs"]["exposed_local_path_count"])
        consumer = DropbearGraphLifecycleProjectionSetV2.load()
        self.assertEqual(0, consumer.view("host").canonical_graph_count)
        with self.assertRaises(GraphLifecycleAdmissionError):
            consumer.require_canonical_graph()

    def test_accepted_synthetic_graph_projects_exact_positive_shape_without_handles(self):
        _, _, envelope, registry = self.accepted()
        values = manager.build_from_registry(registry, envelope["decision"])
        summary = values["host"]["graph_summary"]
        self.assertEqual("accepted", values["host"]["lifecycle"]["source_active_state"])
        self.assertEqual("accepted", values["host"]["lifecycle"]["graph_active_state"])
        self.assertEqual(1, summary["canonical_graph_count"])
        self.assertEqual(12, summary["actuator_mapping_count"])
        self.assertEqual(12, summary["ros_mapping_count"])
        self.assertEqual(12, summary["independent_coordinate_count"])
        self.assertFalse(values["host"]["outputs"]["status_only"])
        self.assertEqual(12, len(values["host"]["outputs"]["actuator_ids"]))
        self.assertEqual(0, values["host"]["outputs"]["command_handle_count"])
        self.assertEqual(0, values["ros"]["outputs"]["materialized_urdf_fragment_count"])
        self.assertEqual(0, values["simulator"]["outputs"]["physical_plant_count"])
        self.assertEqual(0, values["ui"]["outputs"]["exposed_local_path_count"])
        consumer = self.consumer(values, registry)
        generation = consumer.require_canonical_graph(
            source_registry_generation_sha256=values["host"]["subject"][
                "source_registry_generation_sha256"
            ],
            graph_registry_generation_sha256=values["host"]["subject"][
                "graph_registry_generation_sha256"
            ],
        )
        self.assertEqual(envelope["submission_id"], generation.graph_submission_id)
        with self.assertRaises(GraphLifecycleAdmissionError):
            consumer.require_canonical_graph(
                graph_registry_generation_sha256="0" * 64
            )

    def test_revocation_removes_every_positive_output_and_changes_generation(self):
        case, source, envelope, accepted_registry = self.accepted("revoke")
        accepted_values = manager.build_from_registry(
            accepted_registry, envelope["decision"]
        )
        events = [
            case.event(
                envelope, source, "accept", 1, "2026-07-23T13:20:00Z"
            ),
            case.event(
                envelope, source, "revoke", 2, "2026-07-23T13:30:00Z"
            ),
        ]
        revoked = case.build_case(source, [envelope], events)
        values = manager.build_from_registry(revoked)
        self.assertEqual("absent", values["host"]["lifecycle"]["graph_active_state"])
        self.assertEqual(1, values["host"]["lifecycle"]["graph_counts"]["revoked_count"])
        self.assertEqual(0, values["host"]["graph_summary"]["canonical_graph_count"])
        self.assertEqual([], values["host"]["outputs"]["actuator_ids"])
        self.assertEqual([], values["ros"]["outputs"]["ros_joint_names"])
        self.assertEqual([], values["simulator"]["outputs"]["authoritative_graph_ids"])
        self.assertEqual(1, values["ui"]["outputs"]["revoked_count"])
        self.assertNotEqual(
            accepted_values["host"]["subject"]["graph_registry_generation_sha256"],
            values["host"]["subject"]["graph_registry_generation_sha256"],
        )

    def test_supersession_projects_replacement_and_preserves_lifecycle_count(self):
        case = self.fixture()
        source = case.active_source_registry()
        old = case.envelope("old-projection", source)
        new = case.envelope(
            "new-projection",
            source,
            submitted_at="2026-07-23T13:25:00Z",
            supersedes=old["submission_id"],
        )
        events = [
            case.event(old, source, "accept", 1, "2026-07-23T13:20:00Z"),
            case.event(
                old,
                source,
                "supersede",
                2,
                "2026-07-23T13:30:00Z",
                replacement=new,
            ),
        ]
        registry = case.build_case(source, [old, new], events)
        values = manager.build_from_registry(registry, new["decision"])
        self.assertEqual(
            new["submission_id"],
            values["host"]["subject"]["active_graph_submission_id"],
        )
        self.assertEqual(1, values["host"]["lifecycle"]["graph_counts"]["superseded_count"])
        self.assertEqual(1, values["host"]["graph_summary"]["canonical_graph_count"])
        self.assertEqual(1, values["ui"]["outputs"]["superseded_count"])

    def test_active_identity_hash_semantics_and_inactive_extra_decision_deny(self):
        _, _, envelope, registry = self.accepted("tamper")
        mutations = [
            lambda value: value.__setitem__(
                "active_graph_decision_sha256", "0" * 64
            ),
            lambda value: value["summary"].__setitem__(
                "actuator_mapping_count", 11
            ),
            lambda value: value["integrity"].__setitem__(
                "record_sha256", "0" * 64
            ),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(registry)
            mutation(changed)
            with self.assertRaises(manager.GraphLifecycleProjectionError):
                manager.build_from_registry(changed, envelope["decision"])

        inactive = registry_fixtures.manager.build()
        with self.assertRaises(manager.GraphLifecycleProjectionError):
            manager.build_from_registry(inactive, envelope["decision"])

        changed_decision = copy.deepcopy(envelope["decision"])
        changed_decision["graph"]["frames"][0]["chirality"] = "none"
        with self.assertRaises(manager.GraphLifecycleProjectionError):
            manager.build_from_registry(registry, changed_decision)

    def test_cross_view_parity_digest_redaction_and_failed_build_preserve_outputs(self):
        values = manager.build()
        changed = copy.deepcopy(values)
        changed["ui"]["graph_summary"]["frame_count"] = 1
        changed["ui"]["integrity"]["record_sha256"] = manager.sha_bytes(
            manager.digest_payload(changed["ui"])
        )
        with self.assertRaises(manager.GraphLifecycleProjectionError):
            manager.validate_projection_set(changed)

        changed = copy.deepcopy(values)
        changed["host"]["integrity"]["record_sha256"] = "0" * 64
        with self.assertRaises(manager.GraphLifecycleProjectionError):
            manager.validate_projection_set(changed)

        ui_text = json.dumps(values["ui"])
        self.assertNotIn("/home/", ui_text)
        self.assertNotIn("evidence_refs", ui_text)
        before = {
            path.name: path.read_bytes() for path in OUTPUT_ROOT.glob("*.json")
        }
        with mock.patch.object(
            manager,
            "build",
            side_effect=manager.GraphLifecycleProjectionError("synthetic"),
        ):
            with self.assertRaises(manager.GraphLifecycleProjectionError):
                manager.generate()
        after = {
            path.name: path.read_bytes() for path in OUTPUT_ROOT.glob("*.json")
        }
        self.assertEqual(before, after)

        result = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("views=4", result.stdout)
        self.assertIn("support=false motion=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
