from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools import manage_plant_candidate_decisions as decisions


ROOT = Path(__file__).resolve().parents[2]


class PlantCandidateDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.submissions = self.root / "submissions"
        self.events = self.root / "events"
        self.output = self.root / "output"
        self.submissions.mkdir()
        self.events.mkdir()
        self.candidate_path = (
            ROOT
            / "generated/myactuator/plant/spec_candidates/registry.json"
        )
        self.registry = json.loads(
            self.candidate_path.read_text(encoding="utf-8")
        )
        self.table, self.candidate = next(
            (table, candidate)
            for table in self.registry["model_tables"]
            for candidate in table["candidates"]
            if candidate["candidate_id"]
            == "plantspeccandidate-10343b7196c9e64f5e7e"
        )
        self.assignment_path = self.root / "assignments.json"
        assignment = json.loads(
            (
                ROOT / "assets/myactuator/reviewer_assignments.json"
            ).read_text(encoding="utf-8")
        )
        assignment["record_state"] = "submitted"
        for index, item in enumerate(assignment["assignments"]):
            item["assignee_id"] = f"qualified-human-{index:02d}"
            item["organization_or_team"] = f"review-team-{index:02d}"
            item["competence_evidence_refs"] = [
                f"evidence://competence/{index:02d}"
            ]
            item["acknowledged"] = True
            item["due_at_utc"] = "2026-08-01T00:00:00Z"
        assignment["summary"] = {
            "role_count": 17,
            "assigned_role_count": 17,
            "acknowledged_role_count": 17,
            "assignment_complete": True,
        }
        decisions.set_digest(assignment)
        self.assignment = assignment
        self._write_json(self.assignment_path, assignment)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            decisions.canonical_json(value),
            encoding="utf-8",
            newline="\n",
        )

    def _assignment(self, role_id: str) -> dict:
        return next(
            item
            for item in self.assignment["assignments"]
            if item["role_id"] == role_id
        )

    def _submission(
        self,
        *,
        disposition: str = "accept_source_fact",
        submitted_at: str = "2026-07-23T01:00:00Z",
        supersedes: str | None = None,
    ) -> dict:
        extractor = self._assignment(decisions.EXTRACTOR_ROLE)
        fact = None
        if disposition == "accept_source_fact":
            source = self.candidate["parse"]["numbers"][0]
            fact = {
                "mapping_action": "accept_suggested_target",
                "target": {
                    "requirement_kind": "parameter",
                    "domain": "electrical",
                    "name": "phase_inductance_h",
                    "canonical_unit": "H",
                },
                "observation": {
                    "shape": "scalar",
                    "source_value": source,
                    "source_unit": self.candidate["source"]["unit_text"],
                    "normalized_value": source * 0.001,
                    "normalized_unit": "H",
                    "conversion": {
                        "kind": "exact_linear_si",
                        "scale": 0.001,
                        "offset": 0.0,
                        "expression": "mH * 0.001 = H",
                    },
                },
                "source_interpretation": {
                    "selected_number_indices": [0],
                    "qualifier_resolution": None,
                    "annotation_resolution": None,
                    "alternative_resolution": None,
                },
                "evidence_class": "official_stated",
                "extraction_method": "machine_text_assisted",
                "uncertainty": {
                    "class": "transcribed_display_resolution",
                    "lower": -0.000005,
                    "upper": 0.000005,
                    "unit": "H",
                    "coverage_probability": 1.0,
                },
                "operating_condition": {
                    "supply_voltage_v": None,
                    "ambient_temperature_k": None,
                    "rotation_direction": "not_stated",
                    "notes": "The product table does not state conditions.",
                },
            }
        value = {
            "schema_version": "myactuator-plant-candidate-submission/1",
            "submission_id": "plantcandidatesubmission-" + "0" * 20,
            "submitted_at_utc": submitted_at,
            "supersedes_submission_id": supersedes,
            "subject": {
                "candidate_registry_sha256": decisions.sha_file(
                    self.candidate_path
                ),
                "candidate_id": self.candidate["candidate_id"],
                "candidate_sha256": decisions.sha_bytes(
                    decisions.canonical_bytes(self.candidate)
                ),
                "table_id": self.table["table_id"],
                "model_key": self.table["model_identity"]["model_key"],
            },
            "extractor": {
                "role_id": decisions.EXTRACTOR_ROLE,
                "actor_id": extractor["assignee_id"],
                "organization_or_team": extractor[
                    "organization_or_team"
                ],
                "human_attested": True,
                "assignment_register_revision": self.assignment[
                    "record_revision"
                ],
                "competence_evidence_refs": extractor[
                    "competence_evidence_refs"
                ],
                "extraction_assertion": (
                    "I checked the PDF page, table, label, unit, and value."
                ),
            },
            "proposal": {
                "requested_disposition": disposition,
                "fact": fact,
                "blocker_resolutions": [],
                "rationale": (
                    "The exact table cell and SI conversion were checked."
                    if fact
                    else "The candidate is not suitable for this fact."
                ),
            },
            "evidence_refs": [
                "evidence://manual-page-and-coordinate-review"
            ],
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        return decisions.finalize_submission(value)

    def _event(
        self,
        submission: dict,
        *,
        sequence: int = 1,
        event_type: str = "accept",
        reviewed_at: str = "2026-07-23T02:00:00Z",
        replacement: dict | None = None,
    ) -> dict:
        reviewer = self._assignment(decisions.REVIEWER_ROLE)
        value = {
            "schema_version": "myactuator-plant-candidate-event/1",
            "event_id": "plantcandidateevent-" + "0" * 20,
            "sequence": sequence,
            "event_type": event_type,
            "subject": {
                "submission_id": submission["submission_id"],
                "submission_sha256": decisions.sha_bytes(
                    decisions.canonical_bytes(submission)
                ),
                "candidate_id": submission["subject"]["candidate_id"],
                "candidate_sha256": submission["subject"][
                    "candidate_sha256"
                ],
                "superseding_submission_id": (
                    replacement["submission_id"] if replacement else None
                ),
                "superseding_submission_sha256": (
                    decisions.sha_bytes(
                        decisions.canonical_bytes(replacement)
                    )
                    if replacement
                    else None
                ),
            },
            "transition": decisions._expected_transition(event_type),
            "reviewer": {
                "role_id": decisions.REVIEWER_ROLE,
                "actor_id": reviewer["assignee_id"],
                "organization_or_team": reviewer[
                    "organization_or_team"
                ],
                "human_attested": True,
                "independence_attested": True,
                "assignment_register_revision": self.assignment[
                    "record_revision"
                ],
                "competence_evidence_refs": reviewer[
                    "competence_evidence_refs"
                ],
                "reviewed_at_utc": reviewed_at,
                "decision_assertion": (
                    "I independently checked source and normalization."
                ),
                "signature_evidence_refs": [
                    "evidence://reviewer-signature/fixture"
                ],
            },
            "reason": "Independent review supports this lifecycle action.",
            "evidence_refs": ["evidence://independent-review/fixture"],
            "support_granted": False,
            "physical_motion_authority": False,
            "integrity": {"record_sha256": "0" * 64},
        }
        return decisions.finalize_event(value)

    def _store_submission(self, submission: dict) -> None:
        self._write_json(
            self.submissions / f"{submission['submission_id']}.json",
            submission,
        )

    def _store_event(self, event: dict) -> None:
        self._write_json(
            self.events / f"{event['event_id']}.json",
            event,
        )

    def _build(self) -> tuple[dict, dict]:
        return decisions.build(
            candidate_registry_path=self.candidate_path,
            assignment_path=self.assignment_path,
            submission_directory=self.submissions,
            event_directory=self.events,
        )

    def test_empty_project_baseline_is_exact_and_fail_closed(self) -> None:
        registry, facts = decisions.build()
        self.assertEqual(registry["summary"]["candidate_count"], 531)
        self.assertEqual(registry["summary"]["submission_count"], 0)
        self.assertEqual(registry["summary"]["event_count"], 0)
        self.assertEqual(facts, {})
        self.assertEqual(
            registry["blockers"],
            [
                "reviewer_assignments_incomplete",
                "no_accepted_candidate_decisions",
            ],
        )
        decisions.check_outputs(registry, facts)

    def test_independent_acceptance_materializes_v2_prov_fact(self) -> None:
        submission = self._submission()
        event = self._event(submission)
        self._store_submission(submission)
        self._store_event(event)
        registry, facts = self._build()
        self.assertEqual(registry["summary"]["accepted_count"], 1)
        self.assertEqual(len(facts), 1)
        fact = next(iter(facts.values()))
        self.assertEqual(
            fact["schema_version"], "myactuator-plant-source-fact/2"
        )
        self.assertEqual(
            fact["review"]["submission_id"], submission["submission_id"]
        )
        self.assertEqual(
            fact["review"]["acceptance_event_id"], event["event_id"]
        )
        self.assertEqual(len(fact["prov"]["was_derived_from_urns"]), 2)
        self.assertNotEqual(
            fact["prov"]["extractor_agent_urn"],
            fact["prov"]["reviewer_agent_urn"],
        )
        decisions.write_outputs(registry, facts, output_root=self.output)
        decisions.check_outputs(registry, facts, output_root=self.output)

    def test_draft_or_incomplete_assignments_cannot_accept(self) -> None:
        broken = copy.deepcopy(self.assignment)
        broken["record_state"] = "draft"
        decisions.set_digest(broken)
        self._write_json(self.assignment_path, broken)
        self._store_submission(self._submission())
        with self.assertRaisesRegex(
            decisions.PlantCandidateDecisionError,
            "submitted complete reviewer assignment",
        ):
            self._build()

    def test_candidate_hash_table_and_model_binding_are_exact(self) -> None:
        for key, value in (
            ("candidate_sha256", "0" * 64),
            ("table_id", "plantspectable-" + "0" * 20),
            ("model_key", "model-" + "0" * 20),
        ):
            with self.subTest(key=key):
                submission = self._submission()
                submission["subject"][key] = value
                submission = decisions.finalize_submission(submission)
                self._store_submission(submission)
                with self.assertRaises(
                    decisions.PlantCandidateDecisionError
                ):
                    self._build()
                for path in self.submissions.iterdir():
                    path.unlink()

    def test_source_value_unit_conversion_and_shape_drift_are_denied(self) -> None:
        mutations = (
            ("source value", lambda f: f["observation"].update(
                source_value=999.0
            )),
            ("source unit", lambda f: f["observation"].update(
                source_unit="H"
            )),
            ("conversion", lambda f: f["observation"].update(
                normalized_value=999.0
            )),
            ("shape", lambda f: f["target"].update(
                requirement_kind="operating_envelope"
            )),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                submission = self._submission()
                mutate(submission["proposal"]["fact"])
                submission = decisions.finalize_submission(submission)
                self._store_submission(submission)
                with self.assertRaises(
                    decisions.PlantCandidateDecisionError
                ):
                    self._build()
                for path in self.submissions.iterdir():
                    path.unlink()

    def test_mapping_blockers_and_alternatives_require_resolution(self) -> None:
        table, candidate = next(
            (table, candidate)
            for table in self.registry["model_tables"]
            for candidate in table["candidates"]
            if candidate["parse"]["kind"] == "alternatives"
            and candidate["mapping"]["target_field_id"]
            == "transmission.ratio_motor_per_output"
        )
        self.table, self.candidate = table, candidate
        submission = self._submission()
        fact = submission["proposal"]["fact"]
        fact["target"] = {
            "requirement_kind": "parameter",
            "domain": "transmission",
            "name": "ratio_motor_per_output",
            "canonical_unit": "1",
        }
        fact["observation"] = {
            "shape": "scalar",
            "source_value": candidate["parse"]["numbers"][0],
            "source_unit": candidate["source"]["unit_text"],
            "normalized_value": candidate["parse"]["numbers"][0],
            "normalized_unit": "1",
            "conversion": {
                "kind": "exact_linear_si",
                "scale": 1.0,
                "offset": 0.0,
                "expression": "source dash is dimensionless ratio",
            },
        }
        submission = decisions.finalize_submission(submission)
        self._store_submission(submission)
        with self.assertRaisesRegex(
            decisions.PlantCandidateDecisionError,
            "mapping blocker",
        ):
            self._build()

    def test_automation_and_same_actor_reviews_are_denied(self) -> None:
        for mode in ("automation", "same_actor"):
            with self.subTest(mode=mode):
                submission = self._submission()
                if mode == "automation":
                    assignment = self._assignment(
                        decisions.EXTRACTOR_ROLE
                    )
                    assignment["assignee_id"] = "codex-agent"
                    decisions.set_digest(self.assignment)
                    self._write_json(self.assignment_path, self.assignment)
                    submission["extractor"]["actor_id"] = "codex-agent"
                    submission = decisions.finalize_submission(submission)
                    self._store_submission(submission)
                else:
                    reviewer = self._assignment(
                        decisions.REVIEWER_ROLE
                    )
                    reviewer["assignee_id"] = submission["extractor"][
                        "actor_id"
                    ]
                    decisions.set_digest(self.assignment)
                    self._write_json(self.assignment_path, self.assignment)
                    event = self._event(submission)
                    self._store_submission(submission)
                    self._store_event(event)
                with self.assertRaises(
                    decisions.PlantCandidateDecisionError
                ):
                    self._build()
                for directory in (self.submissions, self.events):
                    for path in directory.iterdir():
                        path.unlink()
                self.setUp_assignment_again()

    def setUp_assignment_again(self) -> None:
        self.assignment = json.loads(
            self.assignment_path.read_text(encoding="utf-8")
        )
        for index, item in enumerate(self.assignment["assignments"]):
            item["assignee_id"] = f"qualified-human-{index:02d}"
        decisions.set_digest(self.assignment)
        self._write_json(self.assignment_path, self.assignment)

    def test_event_sequence_transition_and_time_are_replayed(self) -> None:
        cases = ("sequence", "transition", "time")
        for case in cases:
            with self.subTest(case=case):
                submission = self._submission()
                event = self._event(
                    submission,
                    sequence=2 if case == "sequence" else 1,
                    reviewed_at=(
                        "2026-07-23T00:00:00Z"
                        if case == "time"
                        else "2026-07-23T02:00:00Z"
                    ),
                )
                if case == "transition":
                    event["transition"]["next_state"] = "rejected"
                    event = decisions.finalize_event(event)
                self._store_submission(submission)
                self._store_event(event)
                with self.assertRaises(
                    decisions.PlantCandidateDecisionError
                ):
                    self._build()
                for directory in (self.submissions, self.events):
                    for path in directory.iterdir():
                        path.unlink()

    def test_reject_and_defer_never_materialize_facts(self) -> None:
        for disposition, event_type in (
            ("reject_candidate", "reject"),
            ("defer_candidate", "defer"),
        ):
            with self.subTest(disposition=disposition):
                submission = self._submission(disposition=disposition)
                event = self._event(
                    submission, event_type=event_type
                )
                self._store_submission(submission)
                self._store_event(event)
                registry, facts = self._build()
                self.assertEqual(facts, {})
                self.assertEqual(
                    registry["summary"][
                        "deferred_count"
                        if event_type == "defer"
                        else "rejected_count"
                    ],
                    1,
                )
                for directory in (self.submissions, self.events):
                    for path in directory.iterdir():
                        path.unlink()

    def test_revocation_removes_previously_active_fact(self) -> None:
        submission = self._submission()
        accept = self._event(submission)
        revoke = self._event(
            submission,
            sequence=2,
            event_type="revoke",
            reviewed_at="2026-07-23T03:00:00Z",
        )
        self._store_submission(submission)
        self._store_event(accept)
        self._store_event(revoke)
        registry, facts = self._build()
        self.assertEqual(registry["summary"]["revoked_count"], 1)
        self.assertEqual(facts, {})

    def test_supersede_atomically_replaces_active_fact(self) -> None:
        original = self._submission()
        accept = self._event(original)
        replacement = self._submission(
            submitted_at="2026-07-23T03:00:00Z",
            supersedes=original["submission_id"],
        )
        replacement["proposal"]["fact"]["uncertainty"]["lower"] = -0.000001
        replacement["proposal"]["fact"]["uncertainty"]["upper"] = 0.000001
        replacement = decisions.finalize_submission(replacement)
        supersede = self._event(
            original,
            sequence=2,
            event_type="supersede",
            reviewed_at="2026-07-23T04:00:00Z",
            replacement=replacement,
        )
        for submission in (original, replacement):
            self._store_submission(submission)
        for event in (accept, supersede):
            self._store_event(event)
        registry, facts = self._build()
        self.assertEqual(registry["summary"]["superseded_count"], 1)
        self.assertEqual(registry["summary"]["accepted_count"], 1)
        self.assertEqual(len(facts), 1)
        fact = next(iter(facts.values()))
        self.assertEqual(
            fact["review"]["submission_id"], replacement["submission_id"]
        )
        self.assertEqual(
            fact["review"]["acceptance_event_id"], supersede["event_id"]
        )

    def test_duplicate_active_candidate_is_a_conflict(self) -> None:
        first = self._submission()
        second = self._submission(submitted_at="2026-07-23T01:30:00Z")
        first_event = self._event(first)
        second_event = self._event(
            second,
            sequence=2,
            reviewed_at="2026-07-23T03:00:00Z",
        )
        for submission in (first, second):
            self._store_submission(submission)
        for event in (first_event, second_event):
            self._store_event(event)
        with self.assertRaisesRegex(
            decisions.PlantCandidateDecisionError,
            "multiple active facts for candidate",
        ):
            self._build()

    def test_source_drift_fails_without_overwriting_last_output(self) -> None:
        registry, facts = self._build()
        decisions.write_outputs(registry, facts, output_root=self.output)
        before = {
            path.relative_to(self.output): path.read_bytes()
            for path in self.output.rglob("*")
            if path.is_file()
        }
        broken = self._submission()
        broken["subject"]["candidate_registry_sha256"] = "0" * 64
        broken = decisions.finalize_submission(broken)
        self._store_submission(broken)
        with self.assertRaises(
            decisions.PlantCandidateDecisionError
        ):
            self._build()
        after = {
            path.relative_to(self.output): path.read_bytes()
            for path in self.output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_authority_mutations_are_schema_denied(self) -> None:
        for key in ("support_granted", "physical_motion_authority"):
            with self.subTest(key=key):
                submission = self._submission()
                submission[key] = True
                submission = decisions.finalize_submission(submission)
                self._store_submission(submission)
                with self.assertRaises(
                    decisions.PlantCandidateDecisionError
                ):
                    self._build()
                for path in self.submissions.iterdir():
                    path.unlink()


if __name__ == "__main__":
    unittest.main()
