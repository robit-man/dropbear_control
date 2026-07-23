from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
import unittest
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib import actuator_plant as plant_v1
from myactuator_lib import actuator_plant_v2 as plant


def parameters(**overrides: float) -> plant.PlantV2Parameters:
    values = {
        "current_loop_period_s": 0.001,
        "phase_resistance_ohm": 0.2,
        "phase_inductance_h": 0.002,
        "torque_constant_nm_per_a": 0.1,
        "back_emf_v_s_per_rad": 0.01,
        "maximum_qaxis_current_a": 8.0,
        "rotor_inertia_kg_m2": 0.002,
        "output_inertia_kg_m2": 0.02,
        "coulomb_friction_nm": 0.01,
        "viscous_friction_nm_s_per_rad": 0.01,
        "gear_ratio_motor_per_output": 10.0,
        "forward_efficiency_ratio": 0.9,
        "reverse_efficiency_ratio": 0.7,
        "transmission_stiffness_nm_per_rad": 80.0,
        "transmission_damping_nm_s_per_rad": 0.2,
        "backlash_rad": 0.002,
        "maximum_motor_speed_rad_s": 100.0,
        "maximum_output_speed_rad_s": 10.0,
        "maximum_continuous_output_torque_nm": 2.0,
        "maximum_peak_output_torque_nm": 4.0,
        "peak_duration_s": 0.003,
        "winding_to_case_resistance_k_per_w": 1.5,
        "case_to_ambient_resistance_k_per_w": 3.0,
        "winding_thermal_capacity_j_per_k": 5.0,
        "case_thermal_capacity_j_per_k": 20.0,
        "maximum_winding_temperature_k": 360.0,
        "maximum_case_temperature_k": 350.0,
        "position_quantum_rad": 0.001,
        "position_noise_stddev_rad": 0.0008,
        "velocity_noise_stddev_rad_s": 0.002,
        "current_noise_stddev_a": 0.003,
        "command_delay_s": 0.0015,
        "state_sample_period_s": 0.0015,
        "feedback_delay_s": 0.00225,
        "delay_jitter_s": 0.0003,
        "supply_voltage_v": 24.0,
        "ambient_temperature_k": 298.15,
        "position_lower_rad": -2.0,
        "position_upper_rad": 2.0,
        "output_load_torque_bound_nm": 3.0,
        "current_controller_kp_v_per_a": 0.5,
        "winding_derate_start_temperature_k": 340.0,
        "case_derate_start_temperature_k": 330.0,
    }
    values.update(overrides)
    return plant.PlantV2Parameters(**values)


def configuration(
    *,
    parameter_overrides: dict[str, float] | None = None,
    torque_regime: str = "peak_one_shot_per_reset",
    rotation_direction: str = "bidirectional",
    jitter_application: str = "command_and_feedback",
    parameter_set_id: str = "synthetic-v2-conformance",
) -> plant.PlantV2Configuration:
    result = plant.PlantV2Configuration(
        parameter_set_id=parameter_set_id,
        parameters=parameters(**(parameter_overrides or {})),
        semantics=plant.PlantV2Semantics(
            torque_regime=torque_regime,
            rotation_direction=rotation_direction,
            jitter_application=jitter_application,
        ),
    )
    result.validate()
    return result


def state(
    config: plant.PlantV2Configuration,
    *,
    step_index: int = 0,
    **overrides: float,
) -> plant_v1.PlantState:
    values = {
        "step_index": step_index,
        "monotonic_s": (
            step_index * config.parameters.current_loop_period_s
        ),
        "qaxis_current_a": 0.0,
        "rotor_position_rad": 0.0,
        "rotor_velocity_rad_s": 0.0,
        "output_position_rad": 0.0,
        "output_velocity_rad_s": 0.0,
        "winding_temperature_k": config.parameters.ambient_temperature_k,
        "case_temperature_k": config.parameters.ambient_temperature_k,
    }
    values.update(overrides)
    return plant_v1.PlantState(**values)


def canonical_digest(value: object) -> str:
    payload = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ContractAndValidationTests(unittest.TestCase):
    def test_authority_is_permanently_false_and_contract_is_closed(self) -> None:
        self.assertFalse(plant.SUPPORT_GRANTED)
        self.assertFalse(plant.PHYSICAL_VALIDATION)
        self.assertFalse(plant.PHYSICAL_IO)
        self.assertFalse(plant.MOTION_AUTHORITY)
        config = configuration()
        self.assertRegex(config.configuration_sha256, r"^[0-9a-f]{64}$")
        integer_equivalent = replace(
            config,
            parameters=replace(
                config.parameters,
                maximum_qaxis_current_a=8,
            ),
        )
        self.assertEqual(
            integer_equivalent.configuration_sha256,
            config.configuration_sha256,
        )
        exact = plant.PlantV2Time(3, 2000)
        self.assertEqual(exact.as_fraction(), Fraction(3, 2000))
        self.assertEqual(exact.seconds, 0.0015)
        with self.assertRaisesRegex(plant.PlantV2Error, "rational time"):
            plant.PlantV2Time(1, 0).as_fraction()

    def test_parameter_and_semantic_domains_fail_closed(self) -> None:
        base = configuration()
        mutations = (
            ("forward_efficiency_ratio", 1.1),
            ("state_sample_period_s", 0.0005),
            ("maximum_peak_output_torque_nm", 1.0),
            ("position_lower_rad", 0.0),
            ("maximum_case_temperature_k", 320.0),
        )
        for name, value in mutations:
            with self.subTest(name=name):
                invalid = replace(
                    base,
                    parameters=replace(
                        base.parameters,
                        **{name: value},
                    ),
                )
                with self.assertRaises(plant.PlantV2Error):
                    invalid.validate()
        invalid_semantics = replace(
            base,
            semantics=replace(
                base.semantics,
                peak_recovery_policy="invented-cooldown",
            ),
        )
        with self.assertRaisesRegex(
            plant.PlantV2Error,
            "recovery",
        ):
            invalid_semantics.validate()

    def test_invalid_commands_and_loads_do_not_mutate_state(self) -> None:
        instance = plant.DeterministicActuatorPlantV2(configuration())
        before = instance.snapshot()
        invalid = (
            plant.PlantV2Command(2, 0, True, 1.0),
            plant.PlantV2Command(1, 1, True, 1.0),
            plant.PlantV2Command(1, 0, False, 1.0),
            plant.PlantV2Command(1, 0, True, 9.0),
        )
        for command in invalid:
            with self.subTest(command=command):
                with self.assertRaises(plant.PlantV2Error):
                    instance.submit(command)
                self.assertEqual(instance.snapshot(), before)
        with self.assertRaisesRegex(
            plant.PlantV2Error,
            "reviewed bound",
        ):
            instance.step(output_load_torque_nm=3.1)
        self.assertEqual(instance.snapshot(), before)


class SchedulingAndObservationTests(unittest.TestCase):
    def test_command_activates_on_first_solver_boundary_at_or_after_delay(
        self,
    ) -> None:
        config = configuration(
            parameter_overrides={"delay_jitter_s": 0.0},
            jitter_application="command_only",
        )
        instance = plant.DeterministicActuatorPlantV2(config)
        instance.submit(plant.PlantV2Command(1, 0, True, 1.0))
        first = instance.step()
        second = instance.step()
        third = instance.step()
        self.assertEqual(first.diagnostics.active_command_sequence, 0)
        self.assertEqual(second.diagnostics.active_command_sequence, 0)
        self.assertTrue(third.diagnostics.command_activated_this_step)
        self.assertEqual(third.diagnostics.active_command_sequence, 1)
        self.assertEqual(
            third.diagnostics.active_command_eligible_time.as_fraction(),
            Fraction(3, 2000),
        )
        self.assertEqual(
            third.diagnostics.active_command_activation_time.as_fraction(),
            Fraction(1, 500),
        )
        self.assertEqual(
            third.diagnostics.active_command_activation_step_index,
            2,
        )

    def test_command_jitter_is_seeded_bounded_and_reproducible(self) -> None:
        config = configuration(
            parameter_overrides={
                "command_delay_s": 0.002,
                "delay_jitter_s": 0.001,
            },
            jitter_application="command_only",
        )

        def queued(seed: int) -> dict[str, object]:
            instance = plant.DeterministicActuatorPlantV2(
                config,
                seed=seed,
            )
            instance.submit(plant.PlantV2Command(1, 0, True, 1.0))
            return instance.snapshot()["pending_commands"][0]

        first = queued(11)
        second = queued(11)
        other = queued(12)
        self.assertEqual(first, second)
        self.assertNotEqual(first["jitter_s"], other["jitter_s"])
        self.assertLessEqual(abs(first["jitter_s"]), 0.001)

    def test_newest_command_sequence_cannot_regress_after_reordering(
        self,
    ) -> None:
        config = configuration(
            parameter_overrides={
                "command_delay_s": 0.004,
                "delay_jitter_s": 0.004,
            },
            jitter_application="command_only",
        )
        selected: plant.DeterministicActuatorPlantV2 | None = None
        for seed in range(1000):
            candidate = plant.DeterministicActuatorPlantV2(
                config,
                seed=seed,
            )
            candidate.submit(plant.PlantV2Command(1, 0, True, 1.0))
            candidate.submit(plant.PlantV2Command(2, 0, True, 2.0))
            queued = candidate.snapshot()["pending_commands"]
            eligible = {
                row["command"]["sequence"]: Fraction(
                    row["eligible_time"]["numerator"],
                    row["eligible_time"]["denominator"],
                )
                for row in queued
            }
            boundary = {
                sequence: math.ceil(
                    float(value)
                    / config.parameters.current_loop_period_s
                    - 1.0e-14
                )
                for sequence, value in eligible.items()
            }
            if boundary[2] < boundary[1]:
                selected = candidate
                break
        self.assertIsNotNone(selected)
        seen: list[int] = []
        stale = 0
        for _ in range(20):
            result = selected.step()
            seen.append(result.diagnostics.active_command_sequence)
            stale += result.diagnostics.stale_command_count
        first_two = seen.index(2)
        self.assertNotIn(1, seen[first_two:])
        self.assertGreaterEqual(stale, 1)

    def test_delayed_command_cannot_activate_after_its_deadline(
        self,
    ) -> None:
        config = configuration(
            parameter_overrides={
                "command_delay_s": 0.005,
                "delay_jitter_s": 0.0,
            },
            jitter_application="command_only",
        )
        instance = plant.DeterministicActuatorPlantV2(config)
        instance.submit(
            plant.PlantV2Command(
                1,
                0,
                True,
                2.0,
                deadline_step_index=3,
            )
        )
        expired = 0
        for _ in range(8):
            result = instance.step()
            expired += result.diagnostics.expired_command_count
            self.assertEqual(
                result.diagnostics.active_command_sequence,
                0,
            )
        self.assertEqual(expired, 1)
        self.assertEqual(instance.state.qaxis_current_a, 0.0)

        active_config = configuration(
            parameter_overrides={
                "command_delay_s": 0.0,
                "delay_jitter_s": 0.0,
            },
            jitter_application="command_only",
        )
        active = plant.DeterministicActuatorPlantV2(active_config)
        active.submit(
            plant.PlantV2Command(
                1,
                0,
                True,
                2.0,
                deadline_step_index=3,
            )
        )
        first_three = [active.step() for _ in range(3)]
        self.assertTrue(
            all(
                item.diagnostics.active_command_sequence == 1
                for item in first_three
            )
        )
        lease_end = active.step()
        self.assertEqual(
            lease_end.diagnostics.active_command_sequence,
            0,
        )
        self.assertEqual(
            lease_end.diagnostics.expired_command_count,
            1,
        )

    def test_multirate_capture_interpolates_and_arbitrary_delay_delivers(
        self,
    ) -> None:
        config = configuration(
            parameter_overrides={
                "position_noise_stddev_rad": 0.0,
                "velocity_noise_stddev_rad_s": 0.0,
                "current_noise_stddev_a": 0.0,
                "delay_jitter_s": 0.0,
                "feedback_delay_s": 0.0006,
            },
            jitter_application="feedback_only",
        )
        instance = plant.DeterministicActuatorPlantV2(config)
        first = instance.step()
        second = instance.step()
        third = instance.step()
        self.assertEqual(first.sample.sample_sequence, 1)
        self.assertEqual(first.sample.delivered_step_index, 1)
        self.assertEqual(second.sample.sample_sequence, 1)
        self.assertEqual(third.sample.sample_sequence, 2)
        self.assertEqual(
            third.sample.capture_time.as_fraction(),
            Fraction(3, 2000),
        )
        self.assertEqual(
            (
                third.sample.source_lower_step_index,
                third.sample.source_upper_step_index,
            ),
            (1, 2),
        )
        self.assertEqual(
            third.sample.eligible_delivery_time.as_fraction(),
            Fraction(21, 10000),
        )
        self.assertEqual(
            third.sample.delivery_time.as_fraction(),
            Fraction(3, 1000),
        )

    def test_noise_quantization_and_feedback_order_are_deterministic(
        self,
    ) -> None:
        base = plant.DeterministicActuatorPlantV2(
            configuration(
                parameter_overrides={
                    "feedback_delay_s": 0.0,
                    "delay_jitter_s": 0.0,
                },
                jitter_application="feedback_only",
            ),
            seed=55,
        )
        same = plant.DeterministicActuatorPlantV2(
            base.configuration,
            seed=55,
        )
        other = plant.DeterministicActuatorPlantV2(
            base.configuration,
            seed=56,
        )
        self.assertEqual(base.last_step.sample, same.last_step.sample)
        self.assertNotEqual(
            base.last_step.sample.position_noise_rad,
            other.last_step.sample.position_noise_rad,
        )
        observed = base.last_step.sample.output_position_rad
        quantum = base.parameters.position_quantum_rad
        self.assertAlmostEqual(observed / quantum, round(observed / quantum))

        reorder_config = configuration(
            parameter_overrides={
                "state_sample_period_s": 0.001,
                "feedback_delay_s": 0.010,
                "delay_jitter_s": 0.008,
            },
            jitter_application="feedback_only",
        )
        reordered: plant.DeterministicActuatorPlantV2 | None = None
        for seed in range(1000):
            candidate = plant.DeterministicActuatorPlantV2(
                reorder_config,
                seed=seed,
            )
            candidate.step()
            rows = candidate.snapshot()["pending_samples"]
            if len(rows) < 2:
                continue
            times = {
                row["sample"]["sample_sequence"]: Fraction(
                    row["eligible_time"]["numerator"],
                    row["eligible_time"]["denominator"],
                )
                for row in rows
            }
            boundary = {
                sequence: math.ceil(float(value) / 0.001 - 1.0e-14)
                for sequence, value in times.items()
            }
            if boundary[2] < boundary[1]:
                reordered = candidate
                break
        self.assertIsNotNone(reordered)
        delivered_sequences: list[int] = []
        stale = 0
        for _ in range(40):
            result = reordered.step()
            stale += result.diagnostics.stale_sample_count
            if result.sample is not None:
                delivered_sequences.append(result.sample.sample_sequence)
        self.assertEqual(delivered_sequences, sorted(delivered_sequences))
        self.assertGreaterEqual(stale, 1)

    def test_nonzero_reset_aligns_next_capture_without_backfilling(self) -> None:
        config = configuration(
            parameter_overrides={
                "feedback_delay_s": 0.0,
                "delay_jitter_s": 0.0,
            },
            jitter_application="feedback_only",
        )
        instance = plant.DeterministicActuatorPlantV2(config)
        reset = instance.reset(state=state(config, step_index=2))
        self.assertIsNone(reset.sample)
        snapshot = instance.snapshot()
        self.assertEqual(snapshot["capture_sequence"], 0)
        self.assertEqual(
            Fraction(
                snapshot["next_capture_time"]["numerator"],
                snapshot["next_capture_time"]["denominator"],
            ),
            Fraction(3, 1000),
        )
        result = instance.step()
        self.assertEqual(result.sample.sample_sequence, 1)
        self.assertEqual(
            result.sample.capture_time.as_fraction(),
            Fraction(3, 1000),
        )


class DynamicsAndReplayTests(unittest.TestCase):
    def test_directional_efficiencies_are_selected_without_averaging(
        self,
    ) -> None:
        config = configuration(
            parameter_overrides={
                "delay_jitter_s": 0.0,
                "position_noise_stddev_rad": 0.0,
                "velocity_noise_stddev_rad_s": 0.0,
                "current_noise_stddev_a": 0.0,
            }
        )
        positive = plant.DeterministicActuatorPlantV2(config)
        positive.reset(
            state=state(config, rotor_position_rad=0.1),
        )
        positive_step = positive.step()
        negative = plant.DeterministicActuatorPlantV2(config)
        negative.reset(
            state=state(config, rotor_position_rad=-0.1),
        )
        negative_step = negative.step()
        self.assertGreater(
            positive_step.diagnostics.transmission_torque_nm,
            0.0,
        )
        self.assertLess(
            negative_step.diagnostics.transmission_torque_nm,
            0.0,
        )
        self.assertEqual(
            positive_step.diagnostics.active_efficiency_ratio,
            0.9,
        )
        self.assertEqual(
            negative_step.diagnostics.active_efficiency_ratio,
            0.7,
        )
        self.assertNotEqual(
            positive_step.diagnostics.active_efficiency_ratio,
            0.8,
        )

    def test_peak_budget_is_exact_one_shot_and_continuous_mode_has_none(
        self,
    ) -> None:
        overrides = {
            "maximum_continuous_output_torque_nm": 1.0,
            "maximum_peak_output_torque_nm": 4.0,
            "peak_duration_s": 0.003,
            "rotor_inertia_kg_m2": 100.0,
            "output_inertia_kg_m2": 100.0,
            "delay_jitter_s": 0.0,
        }
        peak_config = configuration(parameter_overrides=overrides)
        peak = plant.DeterministicActuatorPlantV2(peak_config)
        peak.reset(state=state(peak_config, rotor_position_rad=1.0))
        limits = [peak.step().diagnostics for _ in range(8)]
        self.assertEqual(
            [item.active_output_torque_limit_nm for item in limits[:4]],
            [4.0, 4.0, 4.0, 1.0],
        )
        self.assertEqual(limits[-1].peak_time_used_s, 0.003)
        self.assertTrue(limits[-1].peak_budget_exhausted)
        for _ in range(100):
            peak.step()
        self.assertEqual(
            peak.last_step.diagnostics.active_output_torque_limit_nm,
            1.0,
        )
        self.assertEqual(
            peak.last_step.diagnostics.peak_time_used_s,
            0.003,
        )

        continuous_config = configuration(
            parameter_overrides=overrides,
            torque_regime="continuous_only",
        )
        continuous = plant.DeterministicActuatorPlantV2(
            continuous_config
        )
        continuous.reset(
            state=state(continuous_config, rotor_position_rad=1.0)
        )
        for _ in range(8):
            continuous_result = continuous.step()
            self.assertEqual(
                continuous_result.diagnostics.active_output_torque_limit_nm,
                1.0,
            )
            self.assertFalse(
                continuous_result.diagnostics.peak_budget_exhausted
            )
            self.assertEqual(
                continuous_result.diagnostics.peak_time_used_s,
                0.0,
            )

    def test_motor_output_position_current_and_thermal_limits(self) -> None:
        limited_config = configuration(
            parameter_overrides={
                "maximum_motor_speed_rad_s": 0.01,
                "maximum_output_speed_rad_s": 0.02,
                "position_upper_rad": 0.001,
                "current_controller_kp_v_per_a": 100.0,
                "delay_jitter_s": 0.0,
                "command_delay_s": 0.0,
            }
        )
        instance = plant.DeterministicActuatorPlantV2(limited_config)
        instance.reset(
            state=state(
                limited_config,
                rotor_velocity_rad_s=0.01,
                output_position_rad=0.00099,
                output_velocity_rad_s=0.02,
            )
        )
        instance.submit(plant.PlantV2Command(1, 0, True, 8.0))
        result = instance.step(output_load_torque_nm=-3.0)
        self.assertTrue(result.diagnostics.voltage_saturated)
        self.assertTrue(result.diagnostics.current_saturated)
        self.assertTrue(result.diagnostics.motor_speed_saturated)
        self.assertTrue(result.diagnostics.output_speed_saturated)
        self.assertTrue(result.diagnostics.position_limited)
        self.assertEqual(result.state.output_position_rad, 0.001)
        self.assertEqual(result.state.output_velocity_rad_s, 0.0)

        hot_config = configuration(
            parameter_overrides={
                "maximum_winding_temperature_k": 340.0,
                "winding_derate_start_temperature_k": 330.0,
                "maximum_case_temperature_k": 350.0,
                "case_derate_start_temperature_k": 340.0,
                "delay_jitter_s": 0.0,
            }
        )
        winding = plant.DeterministicActuatorPlantV2(hot_config)
        winding.reset(
            state=state(
                hot_config,
                winding_temperature_k=339.0,
            )
        )
        self.assertAlmostEqual(
            winding.step().diagnostics.command_derate,
            0.1,
        )
        case = plant.DeterministicActuatorPlantV2(hot_config)
        case.reset(
            state=state(
                hot_config,
                case_temperature_k=349.0,
            )
        )
        self.assertAlmostEqual(case.step().diagnostics.command_derate, 0.1)
        shutdown = plant.DeterministicActuatorPlantV2(hot_config)
        shutdown.reset(
            state=state(
                hot_config,
                winding_temperature_k=341.0,
                case_temperature_k=351.0,
            )
        )
        stopped = shutdown.step()
        self.assertEqual(stopped.diagnostics.command_derate, 0.0)
        self.assertTrue(stopped.diagnostics.thermal_shutdown)

    def test_snapshot_replay_is_exact_and_tampering_is_rejected(self) -> None:
        config = configuration()
        uninterrupted = plant.DeterministicActuatorPlantV2(
            config,
            seed=8721,
        )
        uninterrupted.submit(plant.PlantV2Command(1, 0, True, 1.5))
        for _ in range(5):
            uninterrupted.step(output_load_torque_nm=0.2)
        uninterrupted.submit(plant.PlantV2Command(2, 5, True, -0.5))
        for _ in range(2):
            uninterrupted.step(output_load_torque_nm=-0.1)
        checkpoint = uninterrupted.snapshot()

        restored = plant.DeterministicActuatorPlantV2(config)
        restored.restore(checkpoint)
        self.assertEqual(restored.snapshot(), checkpoint)
        for index in range(80):
            if index == 15:
                command = plant.PlantV2Command(
                    uninterrupted.next_command_sequence,
                    uninterrupted.state.step_index,
                    False,
                    0.0,
                )
                uninterrupted.submit(command)
                restored.submit(command)
            left = uninterrupted.step(
                output_load_torque_nm=((index % 7) - 3) * 0.1
            )
            right = restored.step(
                output_load_torque_nm=((index % 7) - 3) * 0.1
            )
            self.assertEqual(left, right)
        self.assertEqual(uninterrupted.snapshot(), restored.snapshot())

        corrupted = copy.deepcopy(checkpoint)
        corrupted["state"]["qaxis_current_a"] += 0.01
        with self.assertRaisesRegex(
            plant.PlantV2Error,
            "integrity",
        ):
            restored.restore(corrupted)

        semantic_corruption = copy.deepcopy(checkpoint)
        row = semantic_corruption["pending_samples"][0]["sample"]
        row["position_noise_rad"] += 0.01
        payload = {
            key: value
            for key, value in semantic_corruption.items()
            if key != "snapshot_sha256"
        }
        semantic_corruption["snapshot_sha256"] = canonical_digest(payload)
        with self.assertRaisesRegex(
            plant.PlantV2Error,
            "deterministic noise",
        ):
            restored.restore(semantic_corruption)

        foreign = plant.DeterministicActuatorPlantV2(
            configuration(parameter_set_id="foreign")
        )
        with self.assertRaisesRegex(
            plant.PlantV2Error,
            "identity/configuration",
        ):
            foreign.restore(checkpoint)

    def test_canonical_trace_hash_is_pinned(self) -> None:
        config = configuration()
        events: list[tuple[plant.PlantV2Command | None, float]] = []
        command_sequence = 1
        for index in range(240):
            command = None
            if index % 40 == 0:
                target = ((index // 40) % 5 - 2) * 0.75
                command = plant.PlantV2Command(
                    command_sequence,
                    index,
                    True,
                    target,
                )
                command_sequence += 1
            events.append((command, ((index % 9) - 4) * 0.1))
        first = plant.deterministic_trace_sha256(
            config,
            events,
            seed=20260723,
        )
        second = plant.deterministic_trace_sha256(
            config,
            events,
            seed=20260723,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            "1e601fed12104a5c3251a8e1f3a3b0a94470df923c319127dee7c4cfddba743d",
        )


if __name__ == "__main__":
    unittest.main()
