from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from dataclasses import asdict, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib import actuator_plant as plant
from myactuator_lib import rmd_v44
from myactuator_lib import rmd_v44_emulator


FIXTURE = Path(__file__).with_name("synthetic_parameter_set.json")


def parameter_set() -> plant.SyntheticParameterSet:
    return plant.SyntheticParameterSet.load(FIXTURE)


class PlantIdentityTests(unittest.TestCase):
    def test_fixture_is_explicitly_synthetic_and_non_supporting(self) -> None:
        fixture = parameter_set()
        self.assertEqual(fixture.identity.backend_kind, plant.BACKEND_KIND)
        self.assertEqual(fixture.identity.applicability_tuple[0], "SYNTHETIC")
        self.assertFalse(fixture.identity.physical_fidelity)
        self.assertFalse(fixture.identity.support_granted)
        self.assertFalse(plant.IS_PHYSICAL_PLANT)
        self.assertFalse(plant.SUPPORT_GRANTED)
        self.assertFalse(plant.MODEL_FIRMWARE_APPLICABILITY_VERIFIED)

    def test_identity_and_parameter_objects_are_closed(self) -> None:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(value)
        invalid["identity"]["backend_kind"] = "actuator_plant"
        with self.assertRaisesRegex(plant.PlantError, "physical plant"):
            plant.SyntheticParameterSet.from_mapping(invalid)
        invalid = copy.deepcopy(value)
        invalid["identity"]["support_granted"] = True
        with self.assertRaisesRegex(plant.PlantError, "physical plant"):
            plant.SyntheticParameterSet.from_mapping(invalid)
        invalid = copy.deepcopy(value)
        invalid["parameters"]["family_default"] = 1
        with self.assertRaisesRegex(plant.PlantError, "not closed"):
            plant.SyntheticParameterSet.from_mapping(invalid)
        invalid = copy.deepcopy(value)
        invalid["identity"]["applicability_tuple"] = ["SYNTHETIC"] * 6
        with self.assertRaisesRegex(plant.PlantError, "seven"):
            plant.SyntheticParameterSet.from_mapping(invalid)

    def test_invalid_numeric_domains_fail(self) -> None:
        base = parameter_set().parameters
        mutations = {
            "time_step_s": 0.0,
            "phase_inductance_h": float("nan"),
            "gear_efficiency": 1.1,
            "backlash_rad": -0.1,
            "position_lower_rad": base.position_upper_rad,
            "shutdown_temperature_k": base.derate_start_temperature_k,
            "sensor_latency_steps": -1,
        }
        for name, value in mutations.items():
            with self.subTest(name=name):
                invalid = replace(base, **{name: value})
                with self.assertRaises(plant.PlantError):
                    invalid.validate()


class PlantDynamicsTests(unittest.TestCase):
    def test_zero_input_is_exact_rest_equilibrium(self) -> None:
        instance = plant.DeterministicActuatorPlant(parameter_set())
        for _ in range(1000):
            result = instance.step(plant.PlantCommand(False, 0.0))
        self.assertEqual(result.state.qaxis_current_a, 0.0)
        self.assertEqual(result.state.rotor_velocity_rad_s, 0.0)
        self.assertEqual(result.state.output_velocity_rad_s, 0.0)
        self.assertEqual(result.state.output_position_rad, 0.0)
        self.assertEqual(
            result.state.winding_temperature_k,
            instance.parameters.ambient_temperature_k,
        )
        self.assertTrue(result.diagnostics.finite)
        self.assertEqual(result.diagnostics.stored_energy_j, 0.0)

    def test_first_electrical_step_matches_declared_equation(self) -> None:
        fixture = parameter_set()
        instance = plant.DeterministicActuatorPlant(fixture)
        result = instance.step(plant.PlantCommand(True, 1.0))
        p = fixture.parameters
        voltage = p.phase_resistance_ohm + p.current_controller_kp_v_per_a
        expected_current = voltage / p.phase_inductance_h * p.time_step_s
        self.assertAlmostEqual(result.state.qaxis_current_a, expected_current, places=15)
        self.assertAlmostEqual(result.diagnostics.applied_voltage_v, voltage, places=15)
        self.assertGreater(result.state.rotor_velocity_rad_s, 0.0)
        self.assertEqual(result.state.output_velocity_rad_s, 0.0)

    def test_current_voltage_transmission_speed_and_position_saturations(self) -> None:
        fixture = parameter_set()
        saturated_parameters = replace(
            fixture.parameters, current_controller_kp_v_per_a=3.0
        )
        saturated_parameters.validate()
        fixture = replace(fixture, parameters=saturated_parameters)
        instance = plant.DeterministicActuatorPlant(fixture)
        observed_current = False
        observed_voltage = False
        observed_torque = False
        for _ in range(30000):
            result = instance.step(plant.PlantCommand(True, 1000.0))
            observed_current |= result.diagnostics.current_saturated
            observed_voltage |= result.diagnostics.voltage_saturated
            observed_torque |= result.diagnostics.output_torque_saturated
        self.assertTrue(observed_current)
        self.assertTrue(observed_voltage)
        self.assertTrue(observed_torque)
        self.assertLessEqual(
            abs(result.state.qaxis_current_a), fixture.parameters.maximum_qaxis_current_a
        )
        self.assertLessEqual(
            abs(result.state.output_velocity_rad_s),
            fixture.parameters.maximum_output_speed_rad_s,
        )
        self.assertLessEqual(
            result.state.output_position_rad, fixture.parameters.position_upper_rad
        )
        self.assertTrue(result.diagnostics.finite)

    def test_backlash_delays_output_motion_and_friction_holds_small_load(self) -> None:
        instance = plant.DeterministicActuatorPlant(parameter_set())
        first = instance.step(plant.PlantCommand(True, 1.0))
        self.assertGreater(first.state.rotor_position_rad, 0.0)
        self.assertEqual(first.state.output_position_rad, 0.0)
        moved = False
        for _ in range(5000):
            result = instance.step(plant.PlantCommand(True, 1.0))
            moved |= result.state.output_position_rad > 0.0
        self.assertTrue(moved)

        held = plant.DeterministicActuatorPlant(parameter_set())
        for _ in range(1000):
            result = held.step(plant.PlantCommand(False, 0.0, -0.05))
        self.assertEqual(result.state.output_position_rad, 0.0)
        self.assertEqual(result.state.output_velocity_rad_s, 0.0)

    def test_thermal_rise_cooldown_derate_and_shutdown(self) -> None:
        fixture = parameter_set()
        # Accelerate the synthetic thermal scenario without changing identity.
        hot_parameters = replace(
            fixture.parameters,
            winding_thermal_capacity_j_per_k=0.1,
            case_thermal_capacity_j_per_k=0.2,
            derate_start_temperature_k=298.2,
            shutdown_temperature_k=298.4,
        )
        hot_parameters.validate()
        hot_fixture = replace(fixture, parameters=hot_parameters)
        instance = plant.DeterministicActuatorPlant(hot_fixture)
        derated = False
        shutdown = False
        for _ in range(10000):
            result = instance.step(plant.PlantCommand(True, 10.0))
            derated |= result.diagnostics.command_derate < 1.0
            shutdown |= result.diagnostics.thermal_shutdown
            if shutdown:
                break
        self.assertTrue(derated)
        self.assertTrue(shutdown)
        peak = result.state.winding_temperature_k
        for _ in range(20000):
            result = instance.step(plant.PlantCommand(False, 0.0))
        self.assertLess(result.state.winding_temperature_k, peak)

    def test_sensor_quantization_and_exact_latency(self) -> None:
        instance = plant.DeterministicActuatorPlant(parameter_set())
        steps = [instance.step(plant.PlantCommand(True, 1.0)) for _ in range(4)]
        self.assertEqual(steps[0].sample.source_step_index, 0)
        self.assertEqual(steps[1].sample.source_step_index, 0)
        self.assertEqual(steps[2].sample.source_step_index, 1)
        self.assertEqual(steps[3].sample.source_step_index, 2)
        p = instance.parameters
        self.assertAlmostEqual(
            steps[-1].sample.qaxis_current_a / p.current_quantum_a,
            round(steps[-1].sample.qaxis_current_a / p.current_quantum_a),
        )

    def test_fixed_input_trace_hash_is_reproducible(self) -> None:
        commands = [
            plant.PlantCommand(True, ((index % 11) - 5) * 0.25, 0.1)
            for index in range(2000)
        ]
        first = plant.deterministic_trace_sha256(parameter_set(), commands)
        second = plant.deterministic_trace_sha256(parameter_set(), commands)
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            "2cfca5c638918c938802e91bc189f40e42413b1c230cb5b3d6adb0868e296a3b",
        )
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_reset_and_command_validation(self) -> None:
        instance = plant.DeterministicActuatorPlant(parameter_set())
        instance.step(plant.PlantCommand(True, 1.0))
        reset = instance.reset()
        self.assertEqual(reset.state.step_index, 0)
        self.assertEqual(reset.state.output_position_rad, 0.0)
        with self.assertRaisesRegex(plant.PlantError, "finite"):
            instance.step(plant.PlantCommand(True, float("nan")))
        invalid = replace(
            instance.state,
            output_position_rad=instance.parameters.position_upper_rad + 1.0,
        )
        with self.assertRaisesRegex(plant.PlantError, "outside limits"):
            instance.reset(invalid)


class ProtocolBridgeTests(unittest.TestCase):
    def test_iq_request_drives_only_synthetic_bridge(self) -> None:
        instance = plant.DeterministicActuatorPlant(parameter_set())
        bridge = plant.SyntheticIqPlantBridge(1, instance)
        request = rmd_v44.encode_iq_control_raw(1, 125)
        decoded = bridge.apply_request(request)
        self.assertEqual(decoded.iq_raw, 125)
        self.assertTrue(bridge.enabled)
        self.assertEqual(bridge.target_qaxis_current_a, 1.25)
        result = bridge.advance(1000)
        self.assertGreater(result.state.qaxis_current_a, 0.0)
        self.assertFalse(plant.IS_PHYSICAL_PLANT)

        bridge.apply_request(rmd_v44.encode_request(1, rmd_v44.Command.STOP))
        self.assertFalse(bridge.enabled)
        self.assertEqual(bridge.target_qaxis_current_a, 0.0)

    def test_unsupported_motion_mode_and_wrong_node_fail(self) -> None:
        bridge = plant.SyntheticIqPlantBridge(
            1, plant.DeterministicActuatorPlant(parameter_set())
        )
        with self.assertRaises(plant.PlantError):
            bridge.apply_request(
                rmd_v44.encode_speed_control_raw(
                    1, 100, max_torque_percent_raw=10
                )
            )
        with self.assertRaises(rmd_v44.CodecError):
            bridge.apply_request(rmd_v44.encode_iq_control_raw(2, 100))
        with self.assertRaisesRegex(plant.PlantError, "positive integer"):
            bridge.advance(0)

    def test_quantized_sample_can_feed_protocol_emulator_without_plant_claim(self) -> None:
        bridge = plant.SyntheticIqPlantBridge(
            1, plant.DeterministicActuatorPlant(parameter_set())
        )
        bridge.apply_request(rmd_v44.encode_iq_control_raw(1, 125))
        bridge.advance(1000)
        node = bridge.node_state()
        emulator = rmd_v44_emulator.RmdV44Emulator([node])
        submitted = emulator.submit(
            rmd_v44.encode_request(1, rmd_v44.Command.READ_STATUS_2)
        )
        self.assertTrue(submitted.accepted, submitted.reason)
        deliveries = emulator.poll()
        self.assertEqual(len(deliveries), 1)
        observed = rmd_v44.decode_response(deliveries[0].frame)
        self.assertEqual(observed.iq_raw, node.iq_raw)
        self.assertFalse(emulator.is_physical_plant)
        self.assertFalse(emulator.model_firmware_applicability_verified)

    def test_real_registry_remains_empty_and_model_complete_unsupported(self) -> None:
        registry = json.loads(
            (ROOT / "generated" / "myactuator" / "plant" / "runtime_registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(registry["summary"]["models"], 44)
        self.assertEqual(registry["summary"]["sourced_parameter_sets"], 0)
        self.assertEqual(registry["summary"]["runtime_loadable_parameter_sets"], 0)
        self.assertEqual(len(registry["model_coverage"]), 44)
        self.assertTrue(
            all(row["status"] == "unsupported" for row in registry["model_coverage"])
        )


if __name__ == "__main__":
    unittest.main()
