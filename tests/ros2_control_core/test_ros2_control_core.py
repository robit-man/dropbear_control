from __future__ import annotations

import dataclasses
import sys
import unittest

from myactuator_lib import dropbear_hardware_api as hardware
from myactuator_lib import ros2_control_core as core
from myactuator_lib.simulation_runtime import SimulationRuntimeCatalog


CONFIG = "a1" * 32
GRAPH_SHA = "b2" * 32
GRAPH_ID = "graphdecision-" + "c3" * 10
SOURCE = "d4" * 32
GRAPH = "e5" * 32
CATALOG = SimulationRuntimeCatalog.load().generation_sha256
NOW = 1_000_000


class Clock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> int:
        return self.value


def joint(
    name: str = "left-knee",
    actuator: str = "actuator-left-knee",
    commands: tuple[core.CommandInterface, ...] = tuple(core.CommandInterface),
) -> core.JointInterfaceDescriptor:
    return core.JointInterfaceDescriptor(
        name,
        actuator,
        commands,
        tuple(core.StateInterface),
        -1.5,
        1.5,
        2.0,
        10.0,
        5.0,
    )


def descriptor(
    joints: tuple[core.JointInterfaceDescriptor, ...] = (joint(),),
) -> core.SystemInterfaceDescriptor:
    return core.SystemInterfaceDescriptor(
        "dropbear-control-fixture",
        CONFIG,
        GRAPH_ID,
        GRAPH_SHA,
        SOURCE,
        GRAPH,
        CATALOG,
        joints,
    )


def admission(
    ready: frozenset[str] = frozenset({"actuator-left-knee"}),
) -> hardware.AdmissionSnapshot:
    return hardware.AdmissionSnapshot.synthetic_fixture(
        canonical_configuration_digest=CONFIG,
        accepted_graph_decision_id=GRAPH_ID,
        accepted_graph_sha256=GRAPH_SHA,
        source_registry_generation_sha256=SOURCE,
        graph_registry_generation_sha256=GRAPH,
        ready_actuator_ids=ready,
    )


def lease() -> hardware.CommandLease:
    return hardware.CommandLease(
        "lease-controller",
        "controller-fixture",
        7,
        NOW - 100,
        NOW + 100_000,
    )


def present(
    value: float,
    source: hardware.SignalSource = hardware.SignalSource.SYNTHETIC_PLANT,
    validity: hardware.SignalValidity = hardware.SignalValidity.VALID,
) -> hardware.StateSignal:
    return hardware.StateSignal(
        True,
        value,
        source,
        10,
        validity,
        ("fixture:reviewed-signal",),
    )


def absent(
    validity: hardware.SignalValidity = hardware.SignalValidity.MISSING,
) -> hardware.StateSignal:
    return hardware.StateSignal(
        False,
        None,
        hardware.SignalSource.UNAVAILABLE,
        0,
        validity,
        (),
    )


def sample(
    actuator_id: str = "actuator-left-knee",
    joint_session: str = "ros-session-one",
    backend_id: str = "ros-core-fixture",
    **changes,
) -> hardware.JointStateSample:
    values = dict(
        canonical_actuator_id=actuator_id,
        canonical_configuration_digest=CONFIG,
        accepted_graph_decision_id=GRAPH_ID,
        session_id=joint_session,
        sampled_monotonic_ns=NOW - 10,
        received_monotonic_ns=NOW,
        position_rad=present(0.1),
        velocity_rad_s=present(0.2, hardware.SignalSource.REVIEWED_FUSION),
        qaxis_current_a=present(0.3, hardware.SignalSource.NATIVE_DRIVE),
        output_effort_nm=absent(),
        fault_code="NONE",
        backend_id=backend_id,
    )
    values.update(changes)
    return hardware.JointStateSample(**values)


class Fixture:
    def __init__(
        self,
        *,
        system_descriptor: core.SystemInterfaceDescriptor | None = None,
        ready: frozenset[str] = frozenset({"actuator-left-knee"}),
    ) -> None:
        self.clock = Clock()
        self.generations = [CATALOG, SOURCE, GRAPH]
        self.backend = hardware.FakeHardwareBackend(
            backend_id="ros-core-fixture",
        )
        self.hardware_session = hardware.DropbearHardwareSession(
            backend=self.backend,
            admission=admission(ready),
            monotonic_ns=self.clock,
            authority_generation=lambda: (self.generations[1], self.generations[2]),
        )
        self.core = core.Ros2ControlCore(
            descriptor=system_descriptor or descriptor(),
            session=self.hardware_session,
            monotonic_ns=self.clock,
            generation_provider=lambda: tuple(self.generations),
        )

    def configure(self) -> core.OperationResult:
        return self.core.configure(
            configuration_generation=3,
            session_id="ros-session-one",
            session_owner="controller-fixture",
        )

    def activate(self) -> core.OperationResult:
        result = self.configure()
        if not result.succeeded:
            return result
        return self.core.activate(lease())

    def batch(
        self,
        commands: tuple[core.JointCommandValue, ...],
        **changes,
    ) -> core.CommandBatch:
        values = dict(
            simulator_catalog_generation_sha256=CATALOG,
            source_registry_generation_sha256=SOURCE,
            graph_registry_generation_sha256=GRAPH,
            configuration_generation=3,
            sequence=1,
            issued_monotonic_ns=NOW,
            deadline_monotonic_ns=NOW + 1_000,
            commands=commands,
        )
        values.update(changes)
        return core.CommandBatch(**values)


class Ros2ControlCoreTests(unittest.TestCase):
    def test_import_is_ros_independent_and_surface_has_no_native_escape(self) -> None:
        self.assertNotIn("rclpy", sys.modules)
        self.assertNotIn("hardware_interface", sys.modules)
        fields = set(core.JointCommandValue.__dataclass_fields__) | set(
            core.SystemInterfaceDescriptor.__dataclass_fields__
        )
        for forbidden in (
            "can_id",
            "motor_id",
            "opcode",
            "native_bytes",
            "raw_command",
            "serial_port",
        ):
            self.assertNotIn(forbidden, fields)
        with self.assertRaises(core.RosControlAdmissionDenied):
            core.SystemInterfaceDescriptor.load_tracked_denial()

    def test_descriptor_rejects_duplicates_unknown_actuators_and_untyped_interfaces(self) -> None:
        with self.assertRaises(core.RosControlError):
            descriptor((joint(), joint()))
        with self.assertRaises(core.RosControlError):
            descriptor(
                (
                    joint(),
                    joint("left-knee-two", "actuator-left-knee"),
                )
            )
        with self.assertRaises(core.RosControlError):
            joint(actuator="actuator-left-unknown")
        with self.assertRaises(core.RosControlError):
            dataclasses.replace(joint(), command_interfaces=("position",))

    def test_lifecycle_maps_configure_activate_deactivate_cleanup_shutdown(self) -> None:
        fixture = Fixture()
        self.assertEqual(core.ReturnDisposition.INVALID, fixture.core.activate(lease()).disposition)
        self.assertTrue(fixture.configure().succeeded)
        self.assertEqual(core.ControlLifecycle.INACTIVE, fixture.core.state)
        self.assertTrue(fixture.core.activate(lease()).succeeded)
        self.assertEqual(core.ControlLifecycle.ACTIVE, fixture.core.state)
        self.assertTrue(fixture.core.deactivate().succeeded)
        self.assertTrue(fixture.core.cleanup().succeeded)
        self.assertTrue(fixture.core.shutdown().succeeded)
        self.assertEqual(core.ControlLifecycle.FINALIZED, fixture.core.state)
        self.assertEqual(core.ReturnDisposition.INVALID, fixture.configure().disposition)

    def test_all_admitted_command_interfaces_map_to_typed_intents(self) -> None:
        fixture = Fixture()
        self.assertTrue(fixture.activate().succeeded)
        batch = fixture.batch(
            (
                core.JointCommandValue("left-knee", core.CommandInterface.POSITION, 0.25),
                core.JointCommandValue("left-knee", core.CommandInterface.VELOCITY, 0.5),
                core.JointCommandValue("left-knee", core.CommandInterface.EFFORT, 1.25),
            )
        )
        self.assertTrue(fixture.core.write(batch).succeeded)
        self.assertEqual(
            [
                hardware.CommandMode.JOINT_POSITION,
                hardware.CommandMode.JOINT_VELOCITY,
                hardware.CommandMode.OUTPUT_TORQUE,
            ],
            [intent.mode for intent in fixture.backend.commands],
        )
        self.assertTrue(
            all(
                intent.canonical_actuator_id == "actuator-left-knee"
                and intent.session_id == "ros-session-one"
                and intent.lease_id == "lease-controller"
                for intent in fixture.backend.commands
            )
        )

    def test_unadmitted_interface_and_limit_violations_are_invalid_without_write(self) -> None:
        position_only = descriptor(
            (joint(commands=(core.CommandInterface.POSITION,)),)
        )
        fixture = Fixture(system_descriptor=position_only)
        self.assertTrue(fixture.activate().succeeded)
        cases = (
            core.JointCommandValue("left-knee", core.CommandInterface.VELOCITY, 0.1),
            core.JointCommandValue("left-knee", core.CommandInterface.POSITION, 2.0),
            core.JointCommandValue("missing-joint", core.CommandInterface.POSITION, 0.0),
        )
        for command in cases:
            with self.subTest(command=command):
                result = fixture.core.write(fixture.batch((command,)))
                self.assertEqual(core.ReturnDisposition.INVALID, result.disposition)
        self.assertEqual([], fixture.backend.commands)

    def test_read_preserves_missing_stale_fault_and_provenance_without_zero_fill(self) -> None:
        fixture = Fixture()
        self.assertTrue(fixture.activate().succeeded)
        fixture.backend.states["actuator-left-knee"] = sample(
            position_rad=present(
                0.1,
                hardware.SignalSource.EXTERNAL_JOINT_SENSOR,
                hardware.SignalValidity.STALE,
            ),
            output_effort_nm=absent(hardware.SignalValidity.FAULTED),
        )
        result = fixture.core.read()
        self.assertEqual(core.ReturnDisposition.SUCCESS, result.disposition)
        interfaces = dict(result.states[0].interfaces)
        self.assertEqual(hardware.SignalValidity.STALE, interfaces[core.StateInterface.POSITION].validity)
        self.assertEqual(
            hardware.SignalSource.EXTERNAL_JOINT_SENSOR,
            interfaces[core.StateInterface.POSITION].source,
        )
        self.assertIsNone(interfaces[core.StateInterface.EFFORT].value)
        self.assertEqual(hardware.SignalValidity.FAULTED, interfaces[core.StateInterface.EFFORT].validity)
        self.assertEqual(0.3, interfaces[core.StateInterface.QAXIS_CURRENT].value)

    def test_read_never_writes_and_write_requires_active_session(self) -> None:
        fixture = Fixture()
        self.assertEqual(core.ReturnDisposition.NOT_READY, fixture.core.read().disposition)
        self.assertTrue(fixture.activate().succeeded)
        fixture.backend.states["actuator-left-knee"] = sample()
        self.assertTrue(fixture.core.read().disposition is core.ReturnDisposition.SUCCESS)
        self.assertEqual([], fixture.backend.commands)
        fixture.core.deactivate()
        result = fixture.core.write(
            fixture.batch(
                (core.JointCommandValue("left-knee", core.CommandInterface.POSITION, 0.0),)
            )
        )
        self.assertEqual(core.ReturnDisposition.NOT_READY, result.disposition)

    def test_batch_generation_sequence_and_deadline_dispositions_are_distinct(self) -> None:
        fixture = Fixture()
        self.assertTrue(fixture.activate().succeeded)
        command = (
            core.JointCommandValue("left-knee", core.CommandInterface.POSITION, 0.0),
        )
        stale = fixture.batch(command, simulator_catalog_generation_sha256="0" * 64)
        self.assertEqual(core.ReturnDisposition.STALE, fixture.core.write(stale).disposition)
        timeout = fixture.batch(
            command,
            issued_monotonic_ns=NOW - 10,
            deadline_monotonic_ns=NOW,
        )
        self.assertEqual(core.ReturnDisposition.TIMEOUT, fixture.core.write(timeout).disposition)
        self.assertTrue(fixture.core.write(fixture.batch(command)).succeeded)
        replay = fixture.batch(command)
        self.assertEqual(core.ReturnDisposition.STALE, fixture.core.write(replay).disposition)

    def test_live_catalog_source_or_graph_change_revokes_handles(self) -> None:
        for index in range(3):
            with self.subTest(index=index):
                fixture = Fixture()
                self.assertTrue(fixture.activate().succeeded)
                fixture.generations[index] = "f6" * 32
                result = fixture.core.read()
                self.assertEqual(core.ReturnDisposition.STALE, result.disposition)
                self.assertEqual(core.ControlLifecycle.FAULTED, fixture.core.state)
                self.assertEqual((), result.states)
                self.assertGreaterEqual(fixture.backend.cancellation_count, 1)

    def test_backend_state_identity_fault_propagates_without_partial_state(self) -> None:
        fixture = Fixture()
        self.assertTrue(fixture.activate().succeeded)
        fixture.backend.states["actuator-left-knee"] = sample(
            backend_id="different-backend"
        )
        result = fixture.core.read()
        self.assertEqual(core.ReturnDisposition.FAULT, result.disposition)
        self.assertEqual((), result.states)
        self.assertEqual(core.ControlLifecycle.FAULTED, fixture.core.state)

    def test_not_ready_graph_or_lease_is_not_reported_as_success(self) -> None:
        missing = Fixture(ready=frozenset())
        self.assertTrue(missing.configure().succeeded)
        result = missing.core.activate(lease())
        self.assertEqual(core.ReturnDisposition.STALE, result.disposition)
        self.assertEqual(core.ControlLifecycle.FAULTED, missing.core.state)

        expired = Fixture()
        self.assertTrue(expired.configure().succeeded)
        old = dataclasses.replace(lease(), expires_monotonic_ns=NOW)
        result = expired.core.activate(old)
        self.assertEqual(core.ReturnDisposition.NOT_READY, result.disposition)
        self.assertEqual(core.ControlLifecycle.FAULTED, expired.core.state)

    def test_descriptor_order_is_preserved_across_handles_and_reads(self) -> None:
        two = descriptor(
            (
                joint("right-knee", "actuator-right-knee"),
                joint("left-knee", "actuator-left-knee"),
            )
        )
        fixture = Fixture(
            system_descriptor=two,
            ready=frozenset({"actuator-right-knee", "actuator-left-knee"}),
        )
        self.assertTrue(fixture.activate().succeeded)
        fixture.backend.states["actuator-right-knee"] = sample(
            "actuator-right-knee"
        )
        fixture.backend.states["actuator-left-knee"] = sample()
        result = fixture.core.read()
        self.assertEqual(
            ["right-knee", "left-knee"],
            [state.joint_name for state in result.states],
        )


if __name__ == "__main__":
    unittest.main()
