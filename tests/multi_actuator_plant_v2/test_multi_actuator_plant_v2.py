from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib import actuator_plant_v2 as plant
from myactuator_lib import multi_actuator_plant_v2 as multi


ACTUATOR_IDS = tuple(
    sorted(
        (
            "actuator-left-hip-yaw",
            "actuator-left-hip-roll",
            "actuator-left-hip-pitch",
            "actuator-left-knee",
            "actuator-left-inner-calf",
            "actuator-left-outer-calf",
            "actuator-right-hip-yaw",
            "actuator-right-hip-roll",
            "actuator-right-hip-pitch",
            "actuator-right-knee",
            "actuator-right-inner-calf",
            "actuator-right-outer-calf",
        )
    )
)

PINNED_TRACE_SHA256 = (
    "139b5626d38569be00b4034204c9fb9e"
    "463650a40ec73aa5a35358790c14ab10"
)


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
        "command_delay_s": 0.0,
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


def plant_configuration(
    actuator_id: str,
    *,
    parameter_overrides: dict[str, float] | None = None,
    rotation_direction: str = "bidirectional",
) -> plant.PlantV2Configuration:
    result = plant.PlantV2Configuration(
        parameter_set_id=f"synthetic-bank-{actuator_id}",
        parameters=parameters(**(parameter_overrides or {})),
        semantics=plant.PlantV2Semantics(
            torque_regime="peak_one_shot_per_reset",
            rotation_direction=rotation_direction,
            jitter_application="command_and_feedback",
        ),
    )
    result.validate()
    return result


def scene(
    *,
    budget: float = 24.0,
    member_overrides: dict[
        str,
        plant.PlantV2Configuration,
    ]
    | None = None,
) -> multi.MultiActuatorV2Configuration:
    overrides = member_overrides or {}
    result = multi.MultiActuatorV2Configuration(
        scene_id="dropbear-shaped-synthetic-bank-v2",
        members=tuple(
            multi.MultiActuatorV2Member(
                actuator_id,
                overrides.get(
                    actuator_id,
                    plant_configuration(actuator_id),
                ),
            )
            for actuator_id in ACTUATOR_IDS
        ),
        maximum_aggregate_absolute_command_current_a=budget,
    )
    result.validate()
    return result


def batch(
    bank: multi.DeterministicMultiActuatorPlantV2,
    *,
    target: float = 1.0,
    enabled: bool = True,
    deadline_delta: int = 4,
    targets: dict[str, float] | None = None,
    commands: tuple[multi.MultiActuatorV2Command, ...] | None = None,
    scene_sha256: str | None = None,
    reset_generation: int | None = None,
    sequence: int | None = None,
    issued_step_index: int | None = None,
) -> multi.MultiActuatorV2CommandBatch:
    per_axis = targets or {}
    selected_commands = commands or tuple(
        multi.MultiActuatorV2Command(
            actuator_id,
            enabled,
            per_axis.get(actuator_id, target) if enabled else 0.0,
        )
        for actuator_id in ACTUATOR_IDS
    )
    issued = (
        bank.step_index
        if issued_step_index is None
        else issued_step_index
    )
    return multi.MultiActuatorV2CommandBatch(
        scene_configuration_sha256=(
            bank.configuration.configuration_sha256
            if scene_sha256 is None
            else scene_sha256
        ),
        reset_generation=(
            bank.reset_generation
            if reset_generation is None
            else reset_generation
        ),
        sequence=(
            bank.next_batch_sequence if sequence is None else sequence
        ),
        issued_step_index=issued,
        deadline_step_index=issued + deadline_delta,
        commands=selected_commands,
    )


def loads(
    *,
    values: dict[str, float] | None = None,
) -> tuple[multi.MultiActuatorV2Load, ...]:
    selected = values or {}
    return tuple(
        multi.MultiActuatorV2Load(
            actuator_id,
            selected.get(actuator_id, 0.0),
        )
        for actuator_id in ACTUATOR_IDS
    )


def rehash_snapshot(value: dict[str, object]) -> None:
    payload = {
        key: item
        for key, item in value.items()
        if key != "snapshot_sha256"
    }
    value["snapshot_sha256"] = hashlib.sha256(
        (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


class ContractAndIdentityTests(unittest.TestCase):
    def test_twelve_axis_scene_is_closed_and_permanently_non_authoritative(
        self,
    ) -> None:
        config = scene()
        self.assertEqual(config.actuator_ids, ACTUATOR_IDS)
        self.assertEqual(len(config.members), 12)
        self.assertRegex(config.configuration_sha256, r"^[0-9a-f]{64}$")
        for value in (
            multi.SUPPORT_GRANTED,
            multi.EXACT_MODEL_FIDELITY,
            multi.DROPBEAR_CANONICAL,
            multi.MODELS_RIGID_BODY,
            multi.MODELS_SHARED_POWER_BUS,
            multi.PHYSICAL_VALIDATION,
            multi.PHYSICAL_IO,
            multi.MOTION_AUTHORITY,
        ):
            self.assertFalse(value)
        state = multi.DeterministicMultiActuatorPlantV2(config).last_step
        self.assertFalse(state.support_granted)
        self.assertFalse(state.exact_model_fidelity)
        self.assertFalse(state.dropbear_canonical)
        self.assertFalse(state.models_rigid_body)
        self.assertFalse(state.models_shared_power_bus)
        self.assertFalse(state.physical_validation)
        self.assertFalse(state.physical_io)
        self.assertFalse(state.motion_authority)

    def test_scene_order_identity_clock_policy_budget_and_authority_deny(
        self,
    ) -> None:
        base = scene()
        mutations = (
            replace(base, members=tuple(reversed(base.members))),
            replace(base, members=base.members[:-1] + (base.members[-2],)),
            replace(
                base,
                members=(
                    replace(
                        base.members[0],
                        configuration=replace(
                            base.members[0].configuration,
                            parameters=replace(
                                base.members[0].configuration.parameters,
                                current_loop_period_s=0.002,
                                state_sample_period_s=0.002,
                            ),
                        ),
                    ),
                    *base.members[1:],
                ),
            ),
            replace(
                base,
                maximum_aggregate_absolute_command_current_a=0.0,
            ),
            replace(base, command_set_policy="partial-updates"),
            replace(base, support_granted=True),
            replace(base, dropbear_canonical=True),
            replace(base, models_rigid_body=True),
            replace(base, models_shared_power_bus=True),
            replace(base, physical_io=True),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(multi.MultiActuatorPlantV2Error):
                    mutation.validate()

    def test_per_axis_seed_derivation_is_stable_distinct_and_reset_bound(
        self,
    ) -> None:
        first = multi.DeterministicMultiActuatorPlantV2(scene(), seed=9)
        second = multi.DeterministicMultiActuatorPlantV2(scene(), seed=9)
        first_seeds = tuple(
            row.derived_seed for row in first.last_step.members
        )
        second_seeds = tuple(
            row.derived_seed for row in second.last_step.members
        )
        self.assertEqual(first_seeds, second_seeds)
        self.assertEqual(len(set(first_seeds)), 12)
        generation = first.reset_generation
        first.reset(seed=10)
        self.assertEqual(first.reset_generation, generation + 1)
        self.assertNotEqual(
            first_seeds,
            tuple(row.derived_seed for row in first.last_step.members),
        )


class AtomicBatchAndStepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bank = multi.DeterministicMultiActuatorPlantV2(
            scene(),
            seed=42,
        )

    def test_full_batch_drives_all_axes_on_one_synchronized_clock(self) -> None:
        self.bank.submit(batch(self.bank, target=1.0))
        for _ in range(6):
            result = self.bank.advance(loads())
        self.assertEqual(result.step_index, 6)
        self.assertEqual(
            {row.state.step_index for row in result.members},
            {6},
        )
        self.assertTrue(
            all(row.state.qaxis_current_a > 0.0 for row in result.members)
        )
        self.assertGreater(
            result.aggregate_absolute_qaxis_current_a,
            0.0,
        )
        self.assertEqual(result.next_batch_sequence, 2)

    def test_identity_generation_sequence_time_partition_limit_and_budget_deny_without_mutation(
        self,
    ) -> None:
        baseline = self.bank.snapshot()
        wrong_order = tuple(
            reversed(batch(self.bank).commands)
        )
        missing = batch(self.bank).commands[:-1]
        over_limit = {
            ACTUATOR_IDS[0]: 8.1,
        }
        cases = (
            batch(self.bank, scene_sha256="0" * 64),
            batch(self.bank, reset_generation=2),
            batch(self.bank, sequence=2),
            batch(self.bank, issued_step_index=1),
            batch(self.bank, commands=wrong_order),
            batch(self.bank, commands=missing),
            batch(self.bank, targets=over_limit),
            batch(self.bank, target=3.0),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(multi.MultiActuatorPlantV2Error):
                    self.bank.submit(invalid)
                self.assertEqual(self.bank.snapshot(), baseline)

    def test_disabled_and_directional_commands_fail_closed(self) -> None:
        disabled_nonzero = tuple(
            multi.MultiActuatorV2Command(actuator_id, False, 1.0)
            for actuator_id in ACTUATOR_IDS
        )
        with self.assertRaisesRegex(
            multi.MultiActuatorPlantV2Error,
            "disabled target",
        ):
            self.bank.submit(
                batch(self.bank, commands=disabled_nonzero)
            )
        positive_id = ACTUATOR_IDS[0]
        positive_config = scene(
            member_overrides={
                positive_id: plant_configuration(
                    positive_id,
                    rotation_direction="positive",
                )
            }
        )
        positive_bank = multi.DeterministicMultiActuatorPlantV2(
            positive_config
        )
        with self.assertRaisesRegex(
            multi.MultiActuatorPlantV2Error,
            "direction",
        ):
            positive_bank.submit(
                batch(
                    positive_bank,
                    targets={positive_id: -1.0},
                )
            )

    def test_unexpected_mid_batch_failure_rolls_back_every_axis(self) -> None:
        baseline = self.bank.snapshot()
        failing_id = ACTUATOR_IDS[1]
        engine = self.bank._engines[failing_id]
        original_submit = engine.submit

        def fail_submit(command: plant.PlantV2Command) -> None:
            raise plant.PlantV2Error("injected submit failure")

        engine.submit = fail_submit  # type: ignore[method-assign]
        try:
            with self.assertRaisesRegex(
                multi.MultiActuatorPlantV2Error,
                "atomic command batch",
            ):
                self.bank.submit(batch(self.bank))
        finally:
            engine.submit = original_submit  # type: ignore[method-assign]
        self.assertEqual(self.bank.snapshot(), baseline)
        self.assertEqual(self.bank.next_batch_sequence, 1)

    def test_load_partition_and_bound_fail_before_any_step(self) -> None:
        baseline = self.bank.snapshot()
        invalid_loads = (
            tuple(reversed(loads())),
            loads()[:-1],
            loads(values={ACTUATOR_IDS[0]: 3.1}),
        )
        for invalid in invalid_loads:
            with self.subTest(invalid=invalid):
                with self.assertRaises(multi.MultiActuatorPlantV2Error):
                    self.bank.advance(invalid)
                self.assertEqual(self.bank.snapshot(), baseline)

    def test_unexpected_mid_step_failure_rolls_back_every_axis(self) -> None:
        self.bank.submit(batch(self.bank))
        baseline = self.bank.snapshot()
        failing_id = ACTUATOR_IDS[1]
        engine = self.bank._engines[failing_id]
        original_step = engine.step

        def fail_step(*, output_load_torque_nm: float = 0.0):
            raise plant.PlantV2Error("injected step failure")

        engine.step = fail_step  # type: ignore[method-assign]
        try:
            with self.assertRaisesRegex(
                multi.MultiActuatorPlantV2Error,
                "atomic synchronized step",
            ):
                self.bank.advance(loads())
        finally:
            engine.step = original_step  # type: ignore[method-assign]
        self.assertEqual(self.bank.snapshot(), baseline)
        self.assertEqual(self.bank.step_index, 0)

    def test_deadline_expiration_remains_per_axis_and_synchronized(self) -> None:
        self.bank.submit(batch(self.bank, deadline_delta=1))
        self.bank.advance(loads())
        second = self.bank.advance(loads())
        self.assertEqual(
            {row.diagnostics.expired_command_count for row in second.members},
            {1},
        )
        self.assertEqual(
            {
                row.diagnostics.active_command_sequence
                for row in second.members
            },
            {0},
        )


class FaultSnapshotAndReplayTests(unittest.TestCase):
    def test_one_axis_thermal_shutdown_latches_bank_and_clears_all_commands(
        self,
    ) -> None:
        hot_id = ACTUATOR_IDS[0]
        hot = plant_configuration(
            hot_id,
            parameter_overrides={
                "winding_thermal_capacity_j_per_k": 0.001,
                "winding_derate_start_temperature_k": 298.151,
                "maximum_winding_temperature_k": 298.152,
            },
        )
        bank = multi.DeterministicMultiActuatorPlantV2(
            scene(
                budget=96.0,
                member_overrides={hot_id: hot},
            )
        )
        bank.submit(batch(bank, target=8.0))
        result = bank.advance(loads())
        if not result.fault_latched:
            result = bank.advance(loads())
        self.assertTrue(result.fault_latched)
        self.assertEqual(
            result.fault_reason,
            f"thermal-shutdown:{hot_id}",
        )
        self.assertTrue(
            all(
                row["plant_snapshot"]["active_command"] is None
                and not row["plant_snapshot"]["pending_commands"]
                for row in bank.snapshot()["actuator_snapshots"]
            )
        )
        with self.assertRaisesRegex(
            multi.MultiActuatorPlantV2Error,
            "fault is latched",
        ):
            bank.advance(loads())
        with self.assertRaisesRegex(
            multi.MultiActuatorPlantV2Error,
            "fault is latched",
        ):
            bank.submit(batch(bank, target=0.0))
        bank.reset(seed=1)
        self.assertFalse(bank.fault_latched)
        self.assertEqual(bank.fault_reason, "no-fault")

    def test_snapshot_is_byte_stable_and_restore_replays_exactly(self) -> None:
        config = scene()
        uninterrupted = multi.DeterministicMultiActuatorPlantV2(
            config,
            seed=17,
        )
        uninterrupted.submit(
            batch(
                uninterrupted,
                targets={
                    actuator_id: (
                        0.25 + index * 0.05
                    )
                    for index, actuator_id in enumerate(ACTUATOR_IDS)
                },
            )
        )
        for _ in range(5):
            uninterrupted.advance(loads())
        snapshot = uninterrupted.snapshot()
        self.assertEqual(snapshot, uninterrupted.snapshot())
        expected: list[bytes] = []
        for _ in range(8):
            expected.append(
                multi.canonical_json(
                    uninterrupted.advance(loads())
                )
            )

        restored = multi.DeterministicMultiActuatorPlantV2(
            config,
            seed=999,
        )
        restored.restore(snapshot)
        actual = [
            multi.canonical_json(restored.advance(loads()))
            for _ in range(8)
        ]
        self.assertEqual(actual, expected)

    def test_snapshot_integrity_identity_partition_seed_authority_and_projection_tamper_deny(
        self,
    ) -> None:
        bank = multi.DeterministicMultiActuatorPlantV2(scene(), seed=5)
        bank.submit(batch(bank))
        bank.advance(loads())
        baseline = bank.snapshot()

        digest = copy.deepcopy(baseline)
        digest["step_index"] = 9

        scene_drift = copy.deepcopy(baseline)
        scene_drift["scene_configuration_sha256"] = "0" * 64
        rehash_snapshot(scene_drift)

        partition = copy.deepcopy(baseline)
        partition["actuator_snapshots"] = list(
            reversed(partition["actuator_snapshots"])
        )
        rehash_snapshot(partition)

        seed = copy.deepcopy(baseline)
        seed["actuator_snapshots"][0]["derived_seed"] += 1
        rehash_snapshot(seed)

        authority = copy.deepcopy(baseline)
        authority["dropbear_canonical"] = True
        rehash_snapshot(authority)

        projection = copy.deepcopy(baseline)
        projection["last_step"][
            "aggregate_absolute_qaxis_current_a"
        ] += 1.0
        rehash_snapshot(projection)

        for invalid in (
            digest,
            scene_drift,
            partition,
            seed,
            authority,
            projection,
        ):
            with self.subTest(invalid=invalid):
                target = multi.DeterministicMultiActuatorPlantV2(
                    scene(),
                    seed=7,
                )
                before = target.snapshot()
                with self.assertRaises(multi.MultiActuatorPlantV2Error):
                    target.restore(invalid)
                self.assertEqual(target.snapshot(), before)

    def test_fixed_scenario_trace_is_reproducible_and_pinned(self) -> None:
        config = scene()
        prototype = multi.DeterministicMultiActuatorPlantV2(
            config,
            seed=23,
        )
        first = batch(
            prototype,
            targets={
                actuator_id: (
                    0.2 + 0.03 * index
                )
                for index, actuator_id in enumerate(ACTUATOR_IDS)
            },
        )
        second = multi.MultiActuatorV2CommandBatch(
            scene_configuration_sha256=config.configuration_sha256,
            reset_generation=1,
            sequence=2,
            issued_step_index=4,
            deadline_step_index=9,
            commands=tuple(
                multi.MultiActuatorV2Command(
                    actuator_id,
                    True,
                    -0.1 - index * 0.01,
                )
                for index, actuator_id in enumerate(ACTUATOR_IDS)
            ),
        )
        events = (
            (first, loads()),
            (None, loads()),
            (None, loads(values={ACTUATOR_IDS[0]: 0.2})),
            (None, loads()),
            (second, loads()),
            (None, loads()),
            (None, loads()),
            (None, loads()),
        )
        one = multi.deterministic_multi_actuator_trace_sha256(
            config,
            events,
            seed=23,
        )
        two = multi.deterministic_multi_actuator_trace_sha256(
            config,
            events,
            seed=23,
        )
        self.assertEqual(one, two)
        self.assertEqual(one, PINNED_TRACE_SHA256)


if __name__ == "__main__":
    unittest.main()
