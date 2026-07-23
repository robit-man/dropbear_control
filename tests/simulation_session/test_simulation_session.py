from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from myactuator_lib import actuator_plant
from myactuator_lib import plant_runtime_adapter_v2
from myactuator_lib import simulation_runtime
from myactuator_lib.simulation_runtime import (
    SimulationRuntimeCatalog,
    SimulationSelection,
    SimulationUseCase,
)
from myactuator_lib.simulation_session import (
    EngineState,
    FaultDisposition,
    FaultKind,
    ProtocolEmulatorEngine,
    RecordedReplayEngine,
    ResetRequest,
    ScheduledFault,
    SignalValidity,
    SimulationCommand,
    SimulationCommandMode,
    SimulationLifecycle,
    SimulationRevoked,
    SimulationSession,
    SimulationSessionError,
    SourcedPlantV2Engine,
    SyntheticPlantEngine,
)


ROOT = Path(__file__).resolve().parents[2]
PARAMETERS = ROOT / "tests/plant_core/synthetic_parameter_set.json"


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


class SimulationSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = SimulationRuntimeCatalog.load()
        cls.model = cls.catalog._value["models"][0]
        cls.parameter_set = actuator_plant.SyntheticParameterSet.load(PARAMETERS)
        from tests.plant_runtime_adapter_v2 import (
            test_plant_runtime_adapter_v2 as adapter_v2_tests,
        )

        cls.v2_fixture = adapter_v2_tests.Fixture()
        _, contracts = adapter_v2_tests.generator.build_from_inputs(
            **cls.v2_fixture.inputs()
        )
        cls.v2_executable = plant_runtime_adapter_v2.load_contract(
            next(iter(contracts.values()))
        )
        v2_value = copy.deepcopy(cls.catalog._value)
        v2_value["backends"].append(
            {
                "backend_id": cls.v2_executable.backend_id,
                "kind": "actuator_plant",
                "evidence_class": "sil-plant-sourced",
                "substitution_scope": "single-actuator-mechanics",
                "runtime_loadable": True,
                "command_capable": True,
                "deterministic_virtual_time": True,
                "models_protocol_state": False,
                "models_actuator_dynamics": True,
                "models_rigid_body": False,
                "exact_model_applicability_verified": True,
                "physically_validated": False,
                "physical_io": False,
                "parameter_set_id": cls.v2_executable.plant_id,
                "runtime_contract_id": cls.v2_executable.contract_id,
                "allowed_use_cases": ["exact_model_plant_sil"],
                "blockers": [],
            }
        )
        first = v2_value["models"][0]
        first["plant"].update(
            status="sourced",
            plant_ids=[cls.v2_executable.plant_id],
        )
        first["fidelity"].update(
            exact_model_geometry_ready=True,
            exact_model_plant_ready=True,
            exact_model_simulation_ready=True,
        )
        first["admitted_exact_model_backend_ids"] = [
            cls.v2_executable.backend_id
        ]
        v2_value["summary"].update(
            backend_descriptor_count=6,
            runtime_loadable_backend_count=5,
            exact_model_geometry_ready_count=1,
            exact_model_plant_ready_count=1,
            exact_model_simulation_ready_count=1,
        )
        v2_value["integrity"]["record_sha256"] = simulation_runtime._digest(
            v2_value
        )
        cls.v2_catalog = SimulationRuntimeCatalog(
            v2_value,
            json.loads(
                simulation_runtime.DEFAULT_SCHEMA.read_text(
                    encoding="utf-8"
                )
            ),
        )

    def selection(
        self,
        backend_id: str,
        backend_kind: str,
        use_case: SimulationUseCase,
    ) -> SimulationSelection:
        return SimulationSelection(
            self.catalog.generation_sha256,
            self.model["model_key"],
            self.model["series"],
            self.model["model"],
            self.model["configuration_ids"][0],
            backend_id,
            backend_kind,
            use_case,
            False,
            False,
            False,
        )

    def synthetic(
        self,
        *,
        generation_provider=None,
    ) -> SimulationSession:
        return SimulationSession(
            catalog=self.catalog,
            selection=self.selection(
                "synthetic-electromechanical-fixed-step-v1",
                "synthetic_actuator_plant",
                SimulationUseCase.SYNTHETIC_PLANT_SIL,
            ),
            engine=SyntheticPlantEngine(self.parameter_set),
            generation_provider=generation_provider,
        )

    def protocol(self) -> SimulationSession:
        return SimulationSession(
            catalog=self.catalog,
            selection=self.selection(
                "rmd-v44-protocol-emulator",
                "protocol_emulator",
                SimulationUseCase.PROTOCOL_STATE_SIL,
            ),
            engine=ProtocolEmulatorEngine(),
        )

    def sourced_v2(self) -> SimulationSession:
        model = self.v2_catalog._value["models"][0]
        selection = SimulationSelection(
            self.v2_catalog.generation_sha256,
            model["model_key"],
            model["series"],
            model["model"],
            model["configuration_ids"][0],
            self.v2_executable.backend_id,
            "actuator_plant",
            SimulationUseCase.EXACT_MODEL_PLANT_SIL,
            True,
            False,
            False,
        )
        return SimulationSession(
            catalog=self.v2_catalog,
            selection=selection,
            engine=SourcedPlantV2Engine(self.v2_executable),
        )

    @staticmethod
    def replay_states(count: int = 5) -> tuple[EngineState, ...]:
        return tuple(
            EngineState(
                "sim-actuator-1",
                tick,
                tick * 0.01,
                0.1,
                0.2,
                298.15,
                SignalValidity.VALID,
                "recorded-replay",
                "no-fault",
                ("trace:canonical-fixture",),
            )
            for tick in range(count)
        )

    def replay(self, count: int = 5) -> SimulationSession:
        return SimulationSession(
            catalog=self.catalog,
            selection=self.selection(
                "canonical-recorded-state-replay-v1",
                "recorded_replay",
                SimulationUseCase.RECORDED_REPLAY,
            ),
            engine=RecordedReplayEngine(self.replay_states(count)),
        )

    def command(
        self,
        session: SimulationSession,
        *,
        sequence: int = 1,
        mode: SimulationCommandMode = SimulationCommandMode.QAXIS_CURRENT,
        target: float | None = 1.0,
        unit: str | None = "A",
        bound: float | None = 2.0,
        issued_tick: int | None = None,
        deadline_tick: int | None = None,
        reset_generation: int | None = None,
    ) -> SimulationCommand:
        issued = session.tick if issued_tick is None else issued_tick
        return SimulationCommand(
            self.catalog.generation_sha256,
            session.reset_generation if reset_generation is None else reset_generation,
            sequence,
            "sim-actuator-1",
            issued,
            issued + 2 if deadline_tick is None else deadline_tick,
            mode,
            target,
            unit,
            bound,
        )

    def test_lifecycle_is_closed_and_finalize_is_terminal(self) -> None:
        session = self.synthetic()
        with self.assertRaises(SimulationSessionError):
            session.activate()
        session.configure(ResetRequest(7))
        self.assertEqual(SimulationLifecycle.INACTIVE, session.state)
        with self.assertRaises(SimulationSessionError):
            session.configure(ResetRequest(7))
        session.activate()
        with self.assertRaises(SimulationSessionError):
            session.reset(ResetRequest(8))
        session.deactivate()
        session.cleanup()
        session.finalize()
        self.assertEqual(SimulationLifecycle.FINALIZED, session.state)
        with self.assertRaises(SimulationSessionError):
            session.configure(ResetRequest(9))

    def test_read_and_wall_clock_do_not_advance_virtual_time(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(0))
        session.activate()
        first = session.read()
        second = session.read()
        self.assertEqual(0, session.tick)
        self.assertEqual(first.engine_state, second.engine_state)
        session.advance(3)
        self.assertEqual(3, session.tick)
        self.assertEqual(3, session.read().tick)

    def test_command_identity_sequence_deadline_units_and_reset_generation(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(0))
        session.activate()
        session.submit(self.command(session))
        for mutation, message in (
            ({"sequence": 1}, "sequence"),
            ({"issued_tick": 1, "deadline_tick": 3, "sequence": 2}, "issue tick"),
            ({"reset_generation": 2, "sequence": 2}, "reset generation"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                SimulationSessionError, message
            ):
                session.submit(self.command(session, **mutation))
        with self.assertRaisesRegex(SimulationSessionError, "unit"):
            replace(self.command(session, sequence=2), target_unit="Nm")
        with self.assertRaisesRegex(SimulationSessionError, "bound"):
            replace(
                self.command(session, sequence=2),
                maximum_absolute_target_si=0.5,
            )

    def test_synthetic_adapter_reports_equations_without_model_fidelity(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(11))
        session.activate()
        session.submit(self.command(session))
        session.advance(10)
        state = session.read()
        self.assertEqual("synthetic-plant", state.engine_state.source)
        self.assertIn(
            "solver:semi-implicit-euler-fixed-step-v1",
            state.engine_state.provenance_refs,
        )
        self.assertFalse(state.exact_model_fidelity)
        self.assertFalse(state.physically_validated)
        self.assertFalse(state.physical_io)

    def test_sourced_v2_preserves_deadline_feedback_and_snapshot_state(
        self,
    ) -> None:
        session = self.sourced_v2()
        session.configure(ResetRequest(9182))
        initial = session._engine.read_state()
        self.assertEqual(SignalValidity.MISSING, initial.validity)
        self.assertEqual("sourced-plant-v2", initial.source)
        session.activate()
        session.submit(
            SimulationCommand(
                self.v2_catalog.generation_sha256,
                session.reset_generation,
                1,
                "sim-actuator-1",
                0,
                1,
                SimulationCommandMode.QAXIS_CURRENT,
                1.0,
                "A",
                2.0,
            )
        )
        session.advance(2)
        self.assertEqual(
            0.0,
            session._engine._plant.state.qaxis_current_a,
        )
        diagnostics = session._engine._plant.last_step.diagnostics
        self.assertEqual(diagnostics.active_command_sequence, 0)
        self.assertEqual(diagnostics.expired_command_count, 1)

        session.submit(
            SimulationCommand(
                self.v2_catalog.generation_sha256,
                session.reset_generation,
                2,
                "sim-actuator-1",
                2,
                12,
                SimulationCommandMode.QAXIS_CURRENT,
                1.0,
                "A",
                2.0,
            )
        )
        session.advance(6)
        observed = session.read()
        self.assertIn(
            observed.engine_state.validity,
            {SignalValidity.VALID, SignalValidity.STALE},
        )
        self.assertEqual(
            observed.engine_state.source,
            "sourced-plant-v2",
        )
        self.assertTrue(observed.exact_model_fidelity)
        self.assertFalse(observed.physically_validated)
        self.assertFalse(observed.physical_io)
        self.assertTrue(
            any(
                ref.startswith("capture:")
                for ref in observed.engine_state.provenance_refs
            )
        )
        session.deactivate()
        checkpoint = session.snapshot()
        before = session._engine.snapshot()
        session.activate()
        session.advance(2)
        session.deactivate()
        session.restore(checkpoint)
        self.assertEqual(before, session._engine.snapshot())

    def test_protocol_adapter_records_commands_but_does_not_invent_feedback(self) -> None:
        session = self.protocol()
        session.configure(ResetRequest(0))
        session.activate()
        before = session.read().engine_state
        session.submit(self.command(session))
        session.advance()
        after = session.read().engine_state
        self.assertEqual(0.0, before.qaxis_current_a)
        self.assertEqual(0.0, after.qaxis_current_a)
        self.assertEqual("protocol-input", after.source)
        self.assertIn(
            "feedback:independent-input-not-dynamics",
            after.provenance_refs,
        )
        session.deactivate()
        snapshot = session.snapshot()
        self.assertEqual(
            100,
            snapshot.engine_state["node_state"]["last_iq_command_raw"],
        )

    def test_replay_is_read_only_dense_and_exhaustion_faults(self) -> None:
        with self.assertRaisesRegex(SimulationSessionError, "dense"):
            RecordedReplayEngine((self.replay_states()[0], self.replay_states()[2]))
        session = self.replay(2)
        session.configure(ResetRequest(0))
        session.activate()
        with self.assertRaisesRegex(SimulationSessionError, "read-only"):
            session.submit(
                self.command(
                    session,
                    mode=SimulationCommandMode.DISABLE,
                    target=None,
                    unit=None,
                    bound=None,
                )
            )
        session.advance()
        self.assertAlmostEqual(0.01, session.read().engine_state.position_rad)
        with self.assertRaisesRegex(SimulationSessionError, "exhausted"):
            session.advance()
        self.assertEqual(SimulationLifecycle.FAULTED, session.state)

    def test_snapshot_restore_binds_engine_catalog_configuration_and_digest(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(3))
        session.activate()
        session.submit(self.command(session))
        session.advance(5)
        session.deactivate()
        snapshot = session.snapshot()
        position = session._engine.read_state().position_rad
        session.activate()
        session.advance(4)
        session.deactivate()
        session.restore(snapshot)
        self.assertEqual(5, session.tick)
        self.assertEqual(position, session._engine.read_state().position_rad)
        corrupt = replace(snapshot, engine_state_sha256="0" * 64)
        with self.assertRaisesRegex(SimulationSessionError, "digest"):
            session.restore(corrupt)
        wrong_model = replace(snapshot, model_key="model-" + "0" * 20)
        body = asdict(wrong_model)
        body.pop("snapshot_sha256")
        wrong_model = replace(
            wrong_model,
            snapshot_sha256=hashlib.sha256(canonical(body)).hexdigest(),
        )
        with self.assertRaisesRegex(SimulationSessionError, "identity"):
            session.restore(wrong_model)

    def test_initial_state_digest_can_be_pinned(self) -> None:
        first = self.synthetic()
        first.configure(ResetRequest(99))
        snapshot = first.snapshot()
        second = self.synthetic()
        second.configure(
            ResetRequest(99, snapshot.initial_state_sha256)
        )
        denied = self.synthetic()
        with self.assertRaisesRegex(SimulationSessionError, "initial state"):
            denied.configure(ResetRequest(99, "0" * 64))
        self.assertEqual(SimulationLifecycle.FAULTED, denied.state)

    def test_transient_and_latched_scheduled_faults_are_deterministic(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(0))
        session.schedule_fault(
            ScheduledFault(
                "fault-state-transient",
                FaultKind.STATE_UNAVAILABLE,
                "sim-actuator-1",
                1,
                1,
                FaultDisposition.TRANSIENT,
            )
        )
        session.schedule_fault(
            ScheduledFault(
                "fault-command-latched",
                FaultKind.COMMAND_REJECTION,
                "sim-actuator-1",
                2,
                1,
                FaultDisposition.LATCHED,
            )
        )
        session.activate()
        session.advance()
        unavailable = session.read().engine_state
        self.assertEqual(SignalValidity.FAULTED, unavailable.validity)
        session.advance()
        self.assertEqual(SignalValidity.VALID, session.read().engine_state.validity)
        with self.assertRaisesRegex(SimulationSessionError, "command rejection"):
            session.submit(self.command(session, issued_tick=2, sequence=1))
        session.advance()
        with self.assertRaisesRegex(SimulationSessionError, "command rejection"):
            session.submit(self.command(session, issued_tick=3, sequence=1))

    def test_scheduled_backend_fault_cancels_and_latches_session(self) -> None:
        session = self.synthetic()
        session.configure(ResetRequest(0))
        session.schedule_fault(
            ScheduledFault(
                "fault-engine-latched",
                FaultKind.BACKEND_FAULT,
                "sim-actuator-1",
                1,
                1,
                FaultDisposition.LATCHED,
            )
        )
        session.activate()
        session.advance()
        self.assertEqual(SimulationLifecycle.FAULTED, session.state)
        self.assertEqual(
            "scheduled_backend_fault:fault-engine-latched",
            session.fault_reason,
        )
        with self.assertRaises(SimulationSessionError):
            session.read()

    def test_live_catalog_source_or_graph_revocation_faults_before_use(self) -> None:
        generations = list(
            (
                self.catalog.generation_sha256,
                self.catalog.source_registry_generation_sha256,
                self.catalog.graph_registry_generation_sha256,
            )
        )
        session = self.synthetic(generation_provider=lambda: tuple(generations))
        session.configure(ResetRequest(0))
        session.activate()
        generations[1] = "0" * 64
        with self.assertRaises(SimulationRevoked):
            session.read()
        self.assertEqual(SimulationLifecycle.FAULTED, session.state)
        self.assertEqual("authority_generation_changed", session.fault_reason)

    def test_engine_substitution_and_evidence_promotion_are_denied(self) -> None:
        selection = self.selection(
            "synthetic-electromechanical-fixed-step-v1",
            "synthetic_actuator_plant",
            SimulationUseCase.SYNTHETIC_PLANT_SIL,
        )

        class PromotedEngine(SyntheticPlantEngine):
            @property
            def identity(self):
                return replace(
                    super().identity,
                    evidence_class="sil-protocol",
                    exact_model_fidelity=True,
                )

        with self.assertRaises(SimulationSessionError):
            SimulationSession(
                catalog=self.catalog,
                selection=selection,
                engine=PromotedEngine(self.parameter_set),
            )
        with self.assertRaises(SimulationSessionError):
            SimulationSession(
                catalog=self.catalog,
                selection=selection,
                engine=ProtocolEmulatorEngine(),
            )

    def test_trace_is_dense_chained_and_reproducible(self) -> None:
        def run() -> SimulationSession:
            session = self.synthetic()
            session.configure(ResetRequest(5))
            session.activate()
            session.submit(self.command(session))
            session.advance(4)
            session.read()
            session.deactivate()
            return session

        first = run()
        second = run()
        self.assertEqual(first.trace_sha256, second.trace_sha256)
        self.assertEqual(first.trace(), second.trace())
        previous = "0" * 64
        for index, event in enumerate(first.trace(), 1):
            self.assertEqual(index, event.sequence)
            self.assertEqual(previous, event.previous_sha256)
            body = {
                "sequence": event.sequence,
                "tick": event.tick,
                "kind": event.kind,
                "payload": event.payload,
                "previous_sha256": event.previous_sha256,
            }
            self.assertEqual(
                hashlib.sha256(canonical(body)).hexdigest(),
                event.record_sha256,
            )
            previous = event.record_sha256
        self.assertEqual(previous, first.trace_sha256)

    def test_cross_backend_lifecycle_time_and_state_vector(self) -> None:
        for name, factory, maximum_ticks in (
            ("synthetic", self.synthetic, 2),
            ("protocol", self.protocol, 2),
            ("replay", self.replay, 2),
        ):
            with self.subTest(name=name):
                session = factory()
                session.configure(ResetRequest(0))
                session.activate()
                session.advance(maximum_ticks)
                state = session.read()
                self.assertEqual(maximum_ticks, state.tick)
                self.assertFalse(state.physical_io)
                self.assertFalse(state.exact_model_fidelity)
                session.deactivate()
                snapshot = session.snapshot()
                self.assertEqual(maximum_ticks, snapshot.tick)
                session.cleanup()


if __name__ == "__main__":
    unittest.main()
