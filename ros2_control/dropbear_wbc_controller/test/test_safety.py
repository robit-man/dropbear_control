import math

import pytest

from dropbear_wbc_controller.contract import (
    CANONICAL_JOINT_ORDER,
    JOINT_COUNT,
    JOINT_LIMITS,
    STAND_POSE,
    ActivationRequest,
    ContractError,
    JointReferenceFrame,
    MotionTokenFrame,
    RobotStateFrame,
)
from dropbear_wbc_controller.safety import (
    ControllerMode,
    SafetyConfig,
    WbcSafetyController,
)


NS = 1_000_000_000
DT_NS = 20_000_000


def state(now_ns, sequence=1, positions=STAND_POSE, velocities=None, **kwargs):
    return RobotStateFrame(
        source_id="sim",
        sequence=sequence,
        observed_steady_time_ns=now_ns,
        positions=positions,
        velocities=velocities or (0.0,) * JOINT_COUNT,
        **kwargs,
    )


def activation(now_ns, sequence=1, session_id="run"):
    return ActivationRequest(
        session_id=session_id,
        sequence=sequence,
        issued_steady_time_ns=now_ns,
        guarded_confirmation=ActivationRequest.CONFIRMATION,
    )


def reference(now_ns, sequence=1, positions=STAND_POSE, velocities=()):
    return JointReferenceFrame(
        session_id="run",
        sequence=sequence,
        generated_steady_time_ns=now_ns,
        positions=positions,
        velocities=velocities,
    )


def controller(**kwargs):
    defaults = dict(
        command_timeout_sec=0.10,
        state_timeout_sec=2.0,
        stand_blend_sec=0.04,
        watchdog_blend_sec=0.10,
    )
    defaults.update(kwargs)
    return WbcSafetyController(SafetyConfig(**defaults))


def activate_with_state(guard, now_ns=NS, positions=STAND_POSE):
    guard.observe_state(
        state(now_ns, positions=positions), receipt_steady_time_ns=now_ns
    )
    guard.activate(activation(now_ns), now_ns=now_ns)


def finish_blend(guard, now_ns=NS):
    guard.submit_reference(reference(now_ns), receipt_steady_time_ns=now_ns)
    guard.tick(now_ns + DT_NS)
    return guard.tick(now_ns + 2 * DT_NS)


def test_fixed_50_hz_contract():
    with pytest.raises(ContractError, match="fixed at 50 Hz"):
        SafetyConfig(control_hz=100.0)


def test_guarded_activation_requires_fresh_stationary_state():
    guard = controller()
    with pytest.raises(ContractError, match="fresh robot state"):
        guard.activate(activation(NS), now_ns=NS)

    moving = (0.0,) * 4 + (0.2,) + (0.0,) * (JOINT_COUNT - 5)
    guard.observe_state(
        state(NS, velocities=moving), receipt_steady_time_ns=NS
    )
    with pytest.raises(ContractError, match="stationary"):
        guard.activate(activation(NS), now_ns=NS)


def test_activation_rejects_out_of_envelope_measured_knee():
    guard = controller()
    positions = list(STAND_POSE)
    positions[4] = -0.001
    guard.observe_state(
        state(NS, positions=tuple(positions)), receipt_steady_time_ns=NS
    )
    with pytest.raises(ContractError, match="left_knee"):
        guard.activate(activation(NS), now_ns=NS)


def test_activation_blends_to_stand_before_decoded_reference():
    guard = controller(stand_blend_sec=0.10)
    positions = list(STAND_POSE)
    positions[5] = 0.30
    activate_with_state(guard, positions=tuple(positions))
    guard.submit_reference(reference(NS), receipt_steady_time_ns=NS)
    first = guard.tick(NS + DT_NS)
    assert first.mode == ControllerMode.STAND_BLEND.value
    assert first.command_enabled
    assert 0.0 < first.positions[5] < 0.30


def test_reference_position_velocity_and_slew_are_clamped():
    guard = controller()
    activate_with_state(guard)
    finish_blend(guard)
    target = tuple(20.0 if index % 2 else -20.0 for index in range(JOINT_COUNT))
    velocity = (100.0,) * JOINT_COUNT
    clamped = guard.submit_reference(
        reference(NS + 40_000_000, 2, target, velocity),
        receipt_steady_time_ns=NS + 40_000_000,
    )
    assert set(clamped) == set(CANONICAL_JOINT_ORDER)
    output = guard.tick(NS + 60_000_000)
    assert output.command_enabled
    assert set(output.clamped_joints) == set(CANONICAL_JOINT_ORDER)
    for name, position, speed in zip(
        CANONICAL_JOINT_ORDER, output.positions, output.velocities
    ):
        limit = JOINT_LIMITS[name]
        assert limit.lower_rad <= position <= limit.upper_rad
        assert abs(speed) <= limit.max_velocity_rad_s + 1e-12
    assert 0.0 <= output.positions[4] <= math.pi
    assert 0.0 <= output.positions[7] <= math.pi


def test_reference_sequence_is_strictly_monotonic():
    guard = controller()
    activate_with_state(guard)
    guard.submit_reference(reference(NS, 7), receipt_steady_time_ns=NS)
    with pytest.raises(ContractError, match="strictly monotonic"):
        guard.submit_reference(reference(NS, 7), receipt_steady_time_ns=NS)


def test_state_sequence_is_strictly_monotonic():
    guard = controller()
    guard.observe_state(state(NS, 3), receipt_steady_time_ns=NS)
    with pytest.raises(ContractError, match="strictly monotonic"):
        guard.observe_state(state(NS + 1, 3), receipt_steady_time_ns=NS + 1)


def test_token_sequence_and_session_are_guarded_but_token_has_no_output_path():
    guard = controller()
    activate_with_state(guard)
    token = MotionTokenFrame(
        session_id="run",
        sequence=1,
        generated_steady_time_ns=NS,
        token=(0.0,) * 64,
        source="tensorrt",
    )
    guard.accept_token(token, receipt_steady_time_ns=NS)
    with pytest.raises(ContractError, match="strictly monotonic"):
        guard.accept_token(token, receipt_steady_time_ns=NS)
    command = guard.tick(NS + DT_NS)
    assert command.mode == ControllerMode.STAND_BLEND.value
    assert command.source_reference_sequence is None


def test_stale_reference_enters_disabled_watchdog_and_requires_reactivation():
    guard = controller()
    activate_with_state(guard)
    finish_blend(guard)
    output = guard.tick(NS + 160_000_000)
    assert output.mode == ControllerMode.WATCHDOG_STAND.value
    assert not output.command_enabled
    assert guard.active_session is None
    with pytest.raises(ContractError, match="stand_blend or active"):
        guard.submit_reference(
            reference(NS + 160_000_000, 2),
            receipt_steady_time_ns=NS + 160_000_000,
        )


def test_stale_state_fails_closed():
    guard = controller(state_timeout_sec=0.10)
    activate_with_state(guard)
    guard.submit_reference(reference(NS), receipt_steady_time_ns=NS)
    output = guard.tick(NS + 120_000_000)
    assert output.mode == ControllerMode.WATCHDOG_STAND.value
    assert not output.command_enabled
    assert "state watchdog" in output.reason


def test_estop_is_immediate_latched_and_reset_never_reactivates():
    guard = controller()
    activate_with_state(guard)
    guard.latch_estop("operator")
    output = guard.tick(NS + DT_NS)
    assert output.mode == ControllerMode.ESTOP.value
    assert not output.command_enabled
    assert guard.estop_latched

    guard.observe_state(state(NS + 30_000_000, 2), receipt_steady_time_ns=NS + 30_000_000)
    with pytest.raises(ContractError, match="confirmation"):
        guard.reset_estop(operator_confirmation="yes", now_ns=NS + 30_000_000)
    guard.reset_estop(
        operator_confirmation="DROPBEAR_WBC_RESET_ESTOP",
        now_ns=NS + 30_000_000,
    )
    assert guard.mode == ControllerMode.INACTIVE
    assert guard.active_session is None


def test_state_reported_estop_latches_guard():
    guard = controller()
    guard.observe_state(
        state(NS, estop=True), receipt_steady_time_ns=NS
    )
    assert guard.mode == ControllerMode.ESTOP
    assert guard.estop_latched


def test_old_or_future_reference_is_rejected():
    guard = controller()
    activate_with_state(guard)
    with pytest.raises(ContractError, match="stale"):
        guard.submit_reference(
            reference(NS - 200_000_000),
            receipt_steady_time_ns=NS,
        )
    with pytest.raises(ContractError, match="future"):
        guard.submit_reference(
            reference(NS + 30_000_000),
            receipt_steady_time_ns=NS,
        )


def test_non_monotonic_tick_is_rejected():
    guard = controller()
    guard.tick(NS)
    with pytest.raises(ContractError, match="strictly monotonic"):
        guard.tick(NS)
