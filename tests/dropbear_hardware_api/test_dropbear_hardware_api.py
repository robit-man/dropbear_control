from __future__ import annotations

import dataclasses
import math
import unittest

from myactuator_lib import dropbear_hardware_api as api


CONFIG = "a1" * 32
GRAPH_SHA = "b2" * 32
GRAPH_ID = "graphdecision-" + "c3" * 10
SOURCE_GENERATION = "d4" * 32
GRAPH_GENERATION = "e5" * 32
NOW = 1_000_000


class Clock:
    def __init__(self, value: int = NOW):
        self.value = value

    def __call__(self) -> int:
        return self.value


def admission(
    ready: frozenset[str] = frozenset(api.CANONICAL_ACTUATOR_IDS),
) -> api.AdmissionSnapshot:
    return api.AdmissionSnapshot.synthetic_fixture(
        canonical_configuration_digest=CONFIG,
        accepted_graph_decision_id=GRAPH_ID,
        accepted_graph_sha256=GRAPH_SHA,
        source_registry_generation_sha256=SOURCE_GENERATION,
        graph_registry_generation_sha256=GRAPH_GENERATION,
        ready_actuator_ids=ready,
    )


def context(
    *,
    generation: int = 1,
    session_id: str = "session-one",
) -> api.SessionContext:
    return api.SessionContext(
        canonical_configuration_digest=CONFIG,
        accepted_graph_decision_id=GRAPH_ID,
        accepted_graph_sha256=GRAPH_SHA,
        source_registry_generation_sha256=SOURCE_GENERATION,
        graph_registry_generation_sha256=GRAPH_GENERATION,
        configuration_generation=generation,
        session_id=session_id,
        session_owner="controller-fixture",
    )


def lease(**changes) -> api.CommandLease:
    values = {
        "lease_id": "lease-one",
        "lease_owner": "controller-fixture",
        "lease_sequence": 7,
        "issued_monotonic_ns": NOW - 100,
        "expires_monotonic_ns": NOW + 10_000,
    }
    values.update(changes)
    return api.CommandLease(**values)


def intent(mode: api.CommandMode = api.CommandMode.JOINT_POSITION, **changes):
    values = {
        "canonical_actuator_id": "actuator-left-knee",
        "canonical_configuration_digest": CONFIG,
        "accepted_graph_decision_id": GRAPH_ID,
        "session_id": "session-one",
        "lease_id": "lease-one",
        "lease_sequence": 7,
        "issued_monotonic_ns": NOW - 10,
        "deadline_monotonic_ns": NOW + 100,
        "mode": mode,
        "target_position_rad": 0.25,
        "maximum_velocity_rad_s": 1.5,
        "maximum_current_a": 2.0,
    }
    if mode is api.CommandMode.DISABLE:
        values.update(
            target_position_rad=None,
            maximum_velocity_rad_s=None,
            maximum_current_a=None,
        )
    elif mode is api.CommandMode.JOINT_VELOCITY:
        values.update(
            target_position_rad=None,
            target_velocity_rad_s=0.5,
            maximum_velocity_rad_s=None,
        )
    elif mode is api.CommandMode.OUTPUT_TORQUE:
        values.update(
            target_position_rad=None,
            target_output_torque_nm=1.25,
        )
    values.update(changes)
    return api.JointCommandIntent(**values)


def present(value: float, source=api.SignalSource.SYNTHETIC_PLANT):
    return api.StateSignal(
        present=True,
        value=value,
        source=source,
        source_age_ns=10,
        validity=api.SignalValidity.VALID,
        provenance_refs=("tests/dropbear_hardware_api/synthetic-state",),
    )


def absent(validity=api.SignalValidity.MISSING):
    return api.StateSignal(
        present=False,
        value=None,
        source=api.SignalSource.UNAVAILABLE,
        source_age_ns=0,
        validity=validity,
        provenance_refs=(),
    )


def state(**changes):
    values = {
        "canonical_actuator_id": "actuator-left-knee",
        "canonical_configuration_digest": CONFIG,
        "accepted_graph_decision_id": GRAPH_ID,
        "session_id": "session-one",
        "sampled_monotonic_ns": NOW - 10,
        "received_monotonic_ns": NOW,
        "position_rad": present(0.1),
        "velocity_rad_s": present(0.2),
        "qaxis_current_a": present(0.3),
        "output_effort_nm": absent(),
        "fault_code": "NONE",
        "backend_id": "synthetic-hardware-api-fixture",
    }
    values.update(changes)
    return api.JointStateSample(**values)


def active_session(
    *,
    backend=None,
    snapshot=None,
    clock=None,
    authority_generation=None,
):
    backend = backend or api.FakeHardwareBackend()
    clock = clock or Clock()
    session = api.DropbearHardwareSession(
        backend=backend,
        admission=snapshot or admission(),
        monotonic_ns=clock,
        authority_generation=authority_generation,
    )
    session.configure(context())
    session.activate()
    return session, backend, clock


class DropbearHardwareApiTests(unittest.TestCase):
    def test_tracked_project_admission_is_exactly_denied(self):
        snapshot = api.AdmissionSnapshot.load_tracked()
        self.assertFalse(snapshot.graph_admitted)
        self.assertEqual(frozenset(), snapshot.ready_actuator_ids)
        self.assertFalse(snapshot.offline_test_only)
        self.assertFalse(snapshot.physical_motion_authority)
        self.assertTrue(snapshot.blockers)
        backend = api.FakeHardwareBackend()
        session = api.DropbearHardwareSession(
            backend=backend,
            admission=snapshot,
            monotonic_ns=Clock(),
        )
        with self.assertRaises(api.AdmissionDenied):
            session.configure(
                dataclasses.replace(
                    context(),
                    canonical_configuration_digest=(
                        snapshot.canonical_configuration_digest
                    ),
                    accepted_graph_decision_id=(
                        snapshot.candidate_graph_decision_id
                    ),
                )
            )
        self.assertIsNone(backend.context)
        self.assertEqual(api.LifecycleState.UNCONFIGURED, session.state)

    def test_fail_only_physical_backend_has_no_success_operation(self):
        backend = api.FailOnlyPhysicalBackend()
        session = api.DropbearHardwareSession(
            backend=backend,
            admission=admission(),
            monotonic_ns=Clock(),
        )
        with self.assertRaises(api.PhysicalAdapterUnavailable):
            session.configure(context())
        self.assertEqual(api.LifecycleState.UNCONFIGURED, session.state)
        operations = (
            lambda: backend.configure(context()),
            backend.activate,
            lambda: backend.submit(intent()),
            lambda: backend.read_state("actuator-left-knee"),
            backend.cancel_pending,
            backend.deactivate,
            backend.cleanup,
        )
        for operation in operations:
            with self.assertRaises(api.PhysicalAdapterUnavailable):
                operation()

    def test_fake_lifecycle_deactivate_cleanup_fault_and_reconfigure(self):
        session, backend, _ = active_session()
        self.assertEqual(api.LifecycleState.ACTIVE, session.state)
        session.deactivate()
        self.assertEqual(api.LifecycleState.INACTIVE, session.state)
        session.cleanup()
        self.assertEqual(api.LifecycleState.UNCONFIGURED, session.state)
        self.assertEqual(2, backend.cancellation_count)
        session.configure(context(generation=2, session_id="session-two"))
        session.activate()
        session.fault("injected-test-fault")
        self.assertEqual(api.LifecycleState.FAULTED, session.state)
        self.assertEqual("injected-test-fault", session.fault_reason)
        session.cleanup()
        self.assertEqual(api.LifecycleState.UNCONFIGURED, session.state)
        self.assertEqual(4, backend.cancellation_count)
        session.finalize()
        self.assertEqual(api.LifecycleState.FINALIZED, session.state)

    def test_handles_require_active_exact_ready_actuator_and_current_lease(self):
        backend = api.FakeHardwareBackend()
        session = api.DropbearHardwareSession(
            backend=backend,
            admission=admission(frozenset({"actuator-left-knee"})),
            monotonic_ns=Clock(),
        )
        session.configure(context())
        with self.assertRaises(api.HardwareApiError):
            session.open_handle("actuator-left-knee", lease())
        session.activate()
        handle = session.open_handle("actuator-left-knee", lease())
        self.assertEqual("actuator-left-knee", handle.canonical_actuator_id)
        self.assertEqual(
            SOURCE_GENERATION,
            handle.source_registry_generation_sha256,
        )
        self.assertEqual(
            GRAPH_GENERATION,
            handle.graph_registry_generation_sha256,
        )
        for actuator_id in ("left-knee", "actuator-left", "ACTUATOR-LEFT-KNEE", ""):
            with self.assertRaises(api.HardwareApiError):
                session.open_handle(actuator_id, lease())
        with self.assertRaises(api.AdmissionDenied):
            session.open_handle("actuator-left-hip-roll", lease())
        with self.assertRaises(api.HardwareApiError):
            session.open_handle(
                "actuator-left-knee",
                lease(expires_monotonic_ns=NOW),
            )

    def test_all_typed_command_modes_submit_without_native_escape(self):
        session, backend, _ = active_session()
        handle = session.open_handle("actuator-left-knee", lease())
        for mode in api.CommandMode:
            handle.submit(intent(mode))
        self.assertEqual(list(api.CommandMode), [row.mode for row in backend.commands])
        fields = set(api.JointCommandIntent.__dataclass_fields__)
        for forbidden in (
            "native_id",
            "node_id",
            "can_id",
            "vendor_bytes",
            "raw_command",
            "effort_nm",
            "enable_requested",
        ):
            self.assertNotIn(forbidden, fields)

    def test_command_identity_and_time_are_bound_to_handle_session_and_lease(self):
        base = intent()
        mutations = [
            dict(canonical_actuator_id="actuator-right-knee"),
            dict(canonical_configuration_digest="00" * 32),
            dict(accepted_graph_decision_id="graphdecision-" + "00" * 10),
            dict(session_id="session-other"),
            dict(lease_id="lease-other"),
            dict(lease_sequence=8),
            dict(issued_monotonic_ns=NOW + 1),
            dict(deadline_monotonic_ns=NOW + 20_000),
        ]
        for changes in mutations:
            session, backend, _ = active_session()
            handle = session.open_handle("actuator-left-knee", lease())
            with self.assertRaises(api.HardwareApiError, msg=changes):
                handle.submit(dataclasses.replace(base, **changes))
            self.assertEqual([], backend.commands)

    def test_source_or_graph_registry_generation_change_revokes_open_handle(self):
        current = [SOURCE_GENERATION, GRAPH_GENERATION]
        provider = lambda: (current[0], current[1])
        session, backend, _ = active_session(authority_generation=provider)
        handle = session.open_handle("actuator-left-knee", lease())
        current[1] = "f6" * 32
        with self.assertRaises(api.AdmissionDenied):
            handle.submit(intent())
        self.assertEqual(api.LifecycleState.FAULTED, session.state)
        self.assertEqual("authority_generation_changed", session.fault_reason)
        self.assertEqual(1, backend.cancellation_count)
        self.assertEqual([], backend.commands)

        current[:] = [SOURCE_GENERATION, GRAPH_GENERATION]
        session, backend, _ = active_session(authority_generation=provider)
        handle = session.open_handle("actuator-left-knee", lease())
        current[0] = "a7" * 32
        with self.assertRaises(api.AdmissionDenied):
            handle.read_state()
        self.assertEqual(api.LifecycleState.FAULTED, session.state)
        self.assertEqual(1, backend.cancellation_count)

    def test_command_modes_have_closed_target_and_bound_semantics(self):
        invalid = (
            lambda: intent(target_velocity_rad_s=1.0),
            lambda: intent(target_position_rad=None),
            lambda: intent(target_position_rad=math.nan),
            lambda: intent(maximum_current_a=0.0),
            lambda: intent(maximum_velocity_rad_s=None),
            lambda: intent(api.CommandMode.DISABLE, maximum_current_a=1.0),
            lambda: intent(
                api.CommandMode.JOINT_VELOCITY,
                maximum_velocity_rad_s=1.0,
            ),
            lambda: intent(
                api.CommandMode.JOINT_VELOCITY,
                target_output_torque_nm=1.0,
            ),
            lambda: intent(
                api.CommandMode.OUTPUT_TORQUE,
                target_output_torque_nm=math.inf,
            ),
            lambda: intent(deadline_monotonic_ns=NOW - 20),
        )
        for constructor in invalid:
            with self.assertRaises(api.HardwareApiError):
                constructor()

    def test_replay_backend_is_readable_but_never_command_capable(self):
        backend = api.FakeHardwareBackend(
            backend_id="replay-fixture",
            backend_kind=api.BackendKind.REPLAY,
            command_capable=False,
        )
        session, _, _ = active_session(backend=backend)
        handle = session.open_handle("actuator-left-knee", lease())
        replay_state = state(
            backend_id="replay-fixture",
            position_rad=present(0.1, api.SignalSource.REPLAY),
        )
        backend.states["actuator-left-knee"] = replay_state
        self.assertEqual(replay_state, handle.read_state())
        with self.assertRaises(api.HardwareApiError):
            handle.submit(intent())
        self.assertEqual([], backend.commands)
        self.assertEqual(api.LifecycleState.ACTIVE, session.state)

    def test_state_keeps_position_velocity_current_effort_provenance_distinct(self):
        session, backend, _ = active_session()
        handle = session.open_handle("actuator-left-knee", lease())
        sample = state(
            position_rad=present(1.0, api.SignalSource.EXTERNAL_JOINT_SENSOR),
            velocity_rad_s=present(2.0, api.SignalSource.REVIEWED_FUSION),
            qaxis_current_a=present(3.0, api.SignalSource.NATIVE_DRIVE),
            output_effort_nm=absent(),
        )
        backend.states["actuator-left-knee"] = sample
        observed = handle.read_state()
        self.assertEqual(api.SignalSource.EXTERNAL_JOINT_SENSOR, observed.position_rad.source)
        self.assertEqual(api.SignalSource.REVIEWED_FUSION, observed.velocity_rad_s.source)
        self.assertEqual(api.SignalSource.NATIVE_DRIVE, observed.qaxis_current_a.source)
        self.assertFalse(observed.output_effort_nm.present)
        self.assertFalse(observed.physical_motion_authority)

    def test_state_identity_mismatch_faults_and_cancels_session(self):
        mutations = (
            dict(canonical_actuator_id="actuator-right-knee"),
            dict(canonical_configuration_digest="00" * 32),
            dict(accepted_graph_decision_id="graphdecision-" + "00" * 10),
            dict(session_id="session-other"),
            dict(backend_id="backend-other"),
        )
        for changes in mutations:
            session, backend, _ = active_session()
            backend.states["actuator-left-knee"] = state(**changes)
            handle = session.open_handle("actuator-left-knee", lease())
            with self.assertRaises(api.HardwareApiError, msg=changes):
                handle.read_state()
            self.assertEqual(api.LifecycleState.FAULTED, session.state)
            self.assertEqual(1, backend.cancellation_count)

    def test_signal_presence_source_validity_and_provenance_are_closed(self):
        invalid = (
            lambda: api.StateSignal(
                True,
                None,
                api.SignalSource.NATIVE_DRIVE,
                0,
                api.SignalValidity.VALID,
                ("evidence",),
            ),
            lambda: api.StateSignal(
                True,
                1.0,
                api.SignalSource.UNAVAILABLE,
                0,
                api.SignalValidity.VALID,
                ("evidence",),
            ),
            lambda: api.StateSignal(
                True,
                1.0,
                api.SignalSource.NATIVE_DRIVE,
                0,
                api.SignalValidity.MISSING,
                ("evidence",),
            ),
            lambda: api.StateSignal(
                True,
                1.0,
                api.SignalSource.NATIVE_DRIVE,
                0,
                api.SignalValidity.VALID,
                (),
            ),
            lambda: api.StateSignal(
                False,
                1.0,
                api.SignalSource.UNAVAILABLE,
                0,
                api.SignalValidity.MISSING,
                (),
            ),
        )
        for constructor in invalid:
            with self.assertRaises(api.HardwareApiError):
                constructor()

    def test_backend_identity_prevents_kind_or_physical_confusion(self):
        invalid = (
            dict(
                backend_id="backend-test",
                backend_kind=api.BackendKind.SYNTHETIC_PLANT,
                concrete_adapter=False,
                command_capable=True,
                physical_io=True,
            ),
            dict(
                backend_id="backend-test",
                backend_kind=api.BackendKind.REPLAY,
                concrete_adapter=False,
                command_capable=True,
                physical_io=False,
            ),
            dict(
                backend_id="backend-test",
                backend_kind=api.BackendKind.SYNTHETIC_PLANT,
                concrete_adapter=True,
                command_capable=True,
                physical_io=False,
            ),
        )
        for values in invalid:
            with self.assertRaises(api.HardwareApiError):
                api.BackendIdentity(**values)

    def test_illegal_lifecycle_transitions_deny_without_backend_calls(self):
        backend = api.FakeHardwareBackend()
        session = api.DropbearHardwareSession(
            backend=backend,
            admission=admission(),
            monotonic_ns=Clock(),
        )
        for operation in (
            session.activate,
            session.deactivate,
            session.cleanup,
            lambda: session.fault("bad-transition"),
        ):
            with self.assertRaises(api.HardwareApiError):
                operation()
        session.configure(context())
        with self.assertRaises(api.HardwareApiError):
            session.configure(context(session_id="session-two"))
        session.activate()
        with self.assertRaises(api.HardwareApiError):
            session.activate()
        with self.assertRaises(api.HardwareApiError):
            session.cleanup()

    def test_backend_failures_fault_cancel_cleanup_and_reconnect(self):
        backend = api.FakeHardwareBackend()
        session, _, _ = active_session(backend=backend)
        handle = session.open_handle("actuator-left-knee", lease())
        backend.fail_operation = "submit"
        with self.assertRaises(api.HardwareApiError):
            handle.submit(intent())
        self.assertEqual(api.LifecycleState.FAULTED, session.state)
        self.assertEqual(1, backend.cancellation_count)
        backend.fail_operation = None
        session.cleanup()
        session.configure(context(generation=2, session_id="session-two"))
        session.activate()
        self.assertEqual(api.LifecycleState.ACTIVE, session.state)
        session.deactivate()
        session.cleanup()
        with self.assertRaises(api.HardwareApiError):
            session.configure(context(generation=3, session_id="session-one"))

    def test_stale_handle_cannot_cross_configuration_generation(self):
        session, _, _ = active_session()
        old = session.open_handle("actuator-left-knee", lease())
        session.deactivate()
        session.cleanup()
        session.configure(context(generation=2, session_id="session-two"))
        session.activate()
        with self.assertRaises(api.HardwareApiError):
            old.submit(intent())

    def test_offline_fixture_cannot_configure_even_concrete_physical_backend(self):
        class PhysicalBackend(api.FakeHardwareBackend):
            def __init__(self):
                self._identity = api.BackendIdentity(
                    backend_id="physical-test-adapter",
                    backend_kind=api.BackendKind.PHYSICAL_ADAPTER,
                    concrete_adapter=True,
                    command_capable=True,
                    physical_io=True,
                )
                self.context = None
                self.active = False
                self.commands = []
                self.states = {}
                self.cancellation_count = 0
                self.fail_operation = None

        backend = PhysicalBackend()
        session = api.DropbearHardwareSession(
            backend=backend,
            admission=admission(),
            monotonic_ns=Clock(),
        )
        with self.assertRaises(api.AdmissionDenied):
            session.configure(context())
        self.assertIsNone(backend.context)

    def test_exact_canonical_actuator_domain_is_twelve_and_closed(self):
        self.assertEqual(12, len(api.CANONICAL_ACTUATOR_IDS))
        self.assertEqual(12, len(set(api.CANONICAL_ACTUATOR_IDS)))
        self.assertEqual(
            {
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
            },
            set(api.CANONICAL_ACTUATOR_IDS),
        )


if __name__ == "__main__":
    unittest.main()
