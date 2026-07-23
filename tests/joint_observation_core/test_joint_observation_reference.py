from __future__ import annotations

import json
import math
import unittest
from dataclasses import replace
from pathlib import Path

from myactuator_lib.joint_observation import *  # noqa: F403


FIXTURE = Path(__file__).with_name("golden_runtime.jsonl")


def config() -> ConfigIdentity:  # noqa: F405
    return ConfigIdentity("dropbear-prototype-observation", "1", "1" * 64)  # noqa: F405


def calibration(source=ObservationSourceKind.EXTERNAL_ABSOLUTE, sensor="left-hip-roll-external"):  # noqa: F405
    native = source in (ObservationSourceKind.NATIVE_MOTOR, ObservationSourceKind.NATIVE_OUTPUT)  # noqa: F405
    return CalibrationSnapshot(  # noqa: F405
        "synthetic-left-hip-roll-r1", "left_hip_roll", "actuator-left-hip-roll", sensor,
        config(), "2" * 64, "3" * 64, 7, 100, 1000,
        CalibrationEvidenceClass.SYNTHETIC_FIXTURE, source,  # noqa: F405
        RawObservationUnit.RADIAN if native else RawObservationUnit.COUNT,  # noqa: F405
        0.0, 0.0, 0.0, 2.0 * math.pi / 4096.0, 1, 0.1,
        not native, 0.0 if native else 4096.0, 0.0 if native else 2.0 * math.pi,
        WrapInterval.NONE if native else WrapInterval.CENTERED,  # noqa: F405
    )


def sample(source=ObservationSourceKind.EXTERNAL_ABSOLUTE, sensor="left-hip-roll-external"):  # noqa: F405
    native = source in (ObservationSourceKind.NATIVE_MOTOR, ObservationSourceKind.NATIVE_OUTPUT)  # noqa: F405
    return RawJointObservation(  # noqa: F405
        "left_hip_roll", "actuator-left-hip-roll", sensor, config(), source,
        RawObservationUnit.RADIAN if native else RawObservationUnit.COUNT,  # noqa: F405
        1, 800, 850, 1024.0, False, True,
    )


def observation_policy():
    return ObservationPolicy(200, 150, CalibrationEvidenceClass.SYNTHETIC_FIXTURE)  # noqa: F405


def converted(source, sensor, raw):
    result = convert_joint_observation(calibration(source, sensor), replace(sample(source, sensor), raw_value=raw), observation_policy(), 900)  # noqa: F405
    assert result.observation is not None
    return result.observation


def reconciliation_policy(mode=ReconciliationMode.REQUIRE_BOTH_PREFER_EXTERNAL):  # noqa: F405
    return ReconciliationPolicy(  # noqa: F405
        "left_hip_roll", "actuator-left-hip-roll", "left-hip-roll-external",
        "left-hip-roll-native", config(), 3, mode,
        CalibrationEvidenceClass.SYNTHETIC_FIXTURE, 0.1,  # noqa: F405
    )


def reconciled(position=0.0):
    external = converted(ObservationSourceKind.EXTERNAL_ABSOLUTE, "left-hip-roll-external", 0.0)  # noqa: F405
    result = reconcile_joint_observations(reconciliation_policy(ReconciliationMode.EXTERNAL_ONLY), replace(external, joint_position_rad=position), None)  # noqa: F405
    assert result.observation is not None
    return result.observation


def position_limit():
    return PositionLimitSnapshot(  # noqa: F405
        "left_hip_roll", "actuator-left-hip-roll", config(), "4" * 64,
        2, 100, 1000, True, True, -1.0, 1.0,
    )


def run_case(row: dict):
    variant = row["variant"]
    if row["operation"] == "convert":
        cal = calibration()
        raw = sample()
        policy = observation_policy()
        now = 900
        if variant == "external_centered_wrap": raw = replace(raw, raw_value=4095.0)
        elif variant == "native_motor_negative":
            cal = replace(calibration(ObservationSourceKind.NATIVE_MOTOR, "left-hip-roll-native"), motor_to_joint_sign=-1)  # noqa: F405
            raw = replace(sample(ObservationSourceKind.NATIVE_MOTOR, "left-hip-roll-native"), raw_value=2.0)  # noqa: F405
        elif variant == "native_output":
            cal = calibration(ObservationSourceKind.NATIVE_OUTPUT, "left-hip-roll-native")  # noqa: F405
            raw = replace(sample(ObservationSourceKind.NATIVE_OUTPUT, "left-hip-roll-native"), raw_value=0.25)  # noqa: F405
        elif variant == "synthetic_plant":
            cal = calibration(ObservationSourceKind.SYNTHETIC_PLANT, "synthetic-sensor")  # noqa: F405
            raw = sample(ObservationSourceKind.SYNTHETIC_PLANT, "synthetic-sensor")  # noqa: F405
        elif variant == "calibration_invalid": cal = replace(cal, generation=0)
        elif variant == "identity_mismatch": raw = replace(raw, sensor_id="another-sensor")
        elif variant == "source_mismatch": raw = replace(raw, source_kind=ObservationSourceKind.EXTERNAL_INCREMENTAL)  # noqa: F405
        elif variant == "unit_mismatch": raw = replace(raw, raw_unit=RawObservationUnit.VOLT)  # noqa: F405
        elif variant == "evidence_mismatch": policy = replace(policy, required_evidence_class=CalibrationEvidenceClass.PHYSICAL_BENCH)  # noqa: F405
        elif variant == "not_yet_valid": now = 99
        elif variant == "expired": now = 1001
        elif variant == "sample_future": raw = replace(raw, sample_time_ns=901)
        elif variant == "receive_future": raw = replace(raw, receive_time_ns=901)
        elif variant == "time_order": raw = replace(raw, receive_time_ns=799)
        elif variant == "sample_stale": raw = replace(raw, sample_time_ns=699)
        elif variant == "receive_stale": raw = replace(raw, sample_time_ns=700, receive_time_ns=749)
        elif variant == "source_fault": raw = replace(raw, source_fault=True)
        elif variant == "quality_invalid": raw = replace(raw, quality_valid=False)
        elif variant == "sample_outside_calibration":
            raw = replace(raw, sample_time_ns=99, receive_time_ns=100)
            policy = replace(policy, maximum_sample_age_ns=1000, maximum_receive_age_ns=1000)
        result = convert_joint_observation(cal, raw, policy, now)  # noqa: F405
        numeric = result.observation.joint_position_rad if result.observation else None
        return result.code.name, numeric

    if row["operation"] == "stream":
        guard = ObservationStreamGuard()  # noqa: F405
        first = guard.convert(calibration(), sample(), observation_policy(), 900)
        assert first.code == ObservationCode.OK  # noqa: F405
        raw = replace(sample(), sequence=2, sample_time_ns=810, receive_time_ns=860)
        cal = calibration()
        if variant == "sequence_replay": raw = replace(raw, sequence=1)
        elif variant == "sample_regression": raw = replace(raw, sample_time_ns=799)
        elif variant == "receive_regression": raw = replace(raw, receive_time_ns=849)
        elif variant == "calibration_generation_regression": cal = replace(cal, generation=6)
        result = guard.convert(cal, raw, observation_policy(), 900)
        return result.code.name, None

    if row["operation"] == "reconcile":
        ext = converted(ObservationSourceKind.EXTERNAL_ABSOLUTE, "left-hip-roll-external", 0.0)  # noqa: F405
        native = replace(converted(ObservationSourceKind.NATIVE_OUTPUT, "left-hip-roll-native", 0.05), joint_position_rad=0.05)  # noqa: F405
        mode = ReconciliationMode.REQUIRE_BOTH_PREFER_EXTERNAL  # noqa: F405
        policy = reconciliation_policy(mode)
        if variant == "external_only": policy = reconciliation_policy(ReconciliationMode.EXTERNAL_ONLY); native = None  # noqa: E702,F405
        elif variant == "native_only": policy = reconciliation_policy(ReconciliationMode.NATIVE_ONLY); ext = None  # noqa: E702,F405
        elif variant == "prefer_native": policy = reconciliation_policy(ReconciliationMode.REQUIRE_BOTH_PREFER_NATIVE)  # noqa: F405
        elif variant == "external_missing": ext = None
        elif variant == "native_missing": native = None
        elif variant == "sensor_alias": policy = replace(policy, native_sensor_id=policy.external_sensor_id)
        elif variant == "disagreement": native = replace(native, joint_position_rad=1.0)
        result = reconcile_joint_observations(policy, ext, native)  # noqa: F405
        numeric = result.observation.joint_position_rad if result.observation else None
        return result.code.name, numeric

    limit = position_limit()
    observation = reconciled()
    now = 500
    if variant == "below": observation = replace(observation, joint_position_rad=-1.01)
    elif variant == "above": observation = replace(observation, joint_position_rad=1.01)
    elif variant == "not_yet_valid": now = 99
    elif variant == "expired": now = 1001
    elif variant == "invalid_snapshot": limit = replace(limit, lower_rad=2.0)
    elif variant == "identity_mismatch": observation = replace(observation, actuator_id="actuator-right-hip-roll")
    code = check_position_limit(limit, observation, now)  # noqa: F405
    return code.name, observation.joint_position_rad if code == PositionLimitCode.OK else None  # noqa: F405


class JointObservationReferenceTests(unittest.TestCase):
    def test_corpus_is_canonical_unique_and_matches_reference(self):
        seen = set()
        count = 0
        for line in FIXTURE.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            self.assertEqual(line, json.dumps(row, sort_keys=True, separators=(",", ":")))
            self.assertNotIn(row["case"], seen)
            seen.add(row["case"])
            code, numeric = run_case(row)
            self.assertEqual(row["expected_code"], code, row["case"])
            if row["expected_numeric"] == "NONE":
                self.assertIsNone(numeric, row["case"])
            else:
                self.assertAlmostEqual(float(row["expected_numeric"]), numeric, places=12, msg=row["case"])
            count += 1
        self.assertEqual(39, count)

    def test_replay_is_deterministic_and_denials_do_not_advance(self):
        def trace():
            guard = ObservationStreamGuard()  # noqa: F405
            values = []
            for seq, sample_time, receive_time in ((1, 800, 850), (2, 810, 860), (2, 810, 860), (3, 820, 870)):
                result = guard.convert(calibration(), replace(sample(), sequence=seq, sample_time_ns=sample_time, receive_time_ns=receive_time), observation_policy(), 900)
                values.append((result.code.name, result.observation.joint_position_rad if result.observation else None))
            return values
        self.assertEqual(trace(), trace())
        self.assertEqual(["OK", "OK", "SEQUENCE_REPLAY", "OK"], [item[0] for item in trace()])

    def test_closed_enums_match_native_numeric_contract(self):
        self.assertEqual(22, ObservationCode.CONVERSION_NONFINITE)  # noqa: F405
        self.assertEqual(8, ReconciliationCode.DISAGREEMENT_EXCEEDED)  # noqa: F405
        self.assertEqual(6, PositionLimitCode.ABOVE_UPPER)  # noqa: F405


if __name__ == "__main__":
    unittest.main()
