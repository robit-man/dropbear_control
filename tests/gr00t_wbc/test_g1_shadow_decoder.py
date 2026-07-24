from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from integrations.gr00t_wbc.g1_shadow_decoder import (
    ACTION_DIMENSION,
    CADENCE_TOLERANCE_NS,
    CONTROL_PERIOD_NS,
    G1_ACTION_SCALES_RAD,
    G1_DEFAULT_ANGLES_RAD,
    G1_JOINT_LIMITS_RAD,
    G1ShadowCadenceError,
    G1ShadowContractError,
    G1ShadowDecoder,
    G1ShadowDecoderUnavailable,
    ISAAC_INDEX_TO_MUJOCO_INDEX,
    MAX_SHADOW_JOINT_SPEED_RAD_S,
    MODEL_SHA256,
    MUJOCO_INDEX_TO_ISAAC_INDEX,
    OBSERVATION_DIMENSION,
    OBSERVATION_SLICES,
    TOKEN_DIMENSION,
    shadow_decoder_contract,
)
from integrations.gr00t_wbc.retarget import G1_BODY_JOINT_NAMES


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _Meta:
    name: str
    shape: list[int]
    type: str = "tensor(float)"


class _FakeSession:
    def __init__(
        self,
        *,
        action: np.ndarray | None = None,
        providers: tuple[str, ...] = ("CUDAExecutionProvider",),
        input_shape: tuple[int, ...] = (1, OBSERVATION_DIMENSION),
        output_shape: tuple[int, ...] = (1, ACTION_DIMENSION),
    ) -> None:
        self.action = (
            np.zeros((1, ACTION_DIMENSION), dtype=np.float32)
            if action is None
            else action
        )
        self.providers = providers
        self.input_shape = input_shape
        self.output_shape = output_shape
        self.observations: list[np.ndarray] = []
        self.calls = 0

    def get_providers(self) -> list[str]:
        return list(self.providers)

    def get_inputs(self) -> list[_Meta]:
        return [_Meta("obs_dict", list(self.input_shape))]

    def get_outputs(self) -> list[_Meta]:
        return [_Meta("action", list(self.output_shape))]

    def run(
        self,
        output_names: list[str],
        feeds: dict[str, np.ndarray],
    ) -> list[np.ndarray]:
        assert output_names == ["action"]
        self.observations.append(feeds["obs_dict"].copy())
        self.calls += 1
        if self.calls == 1:
            # Initialization warm-up must validate independently of the
            # action configured for streamed frames.
            return [np.zeros((1, ACTION_DIMENSION), dtype=np.float32)]
        return [self.action.copy()]


def _decoder(
    *,
    action: np.ndarray | None = None,
    providers: tuple[str, ...] = ("CUDAExecutionProvider",),
    input_shape: tuple[int, ...] = (1, OBSERVATION_DIMENSION),
    output_shape: tuple[int, ...] = (1, ACTION_DIMENSION),
) -> tuple[G1ShadowDecoder, _FakeSession]:
    session = _FakeSession(
        action=action,
        providers=providers,
        input_shape=input_shape,
        output_shape=output_shape,
    )
    decoder = G1ShadowDecoder(ROOT, session_factory=lambda _: session)
    return decoder, session


def test_static_contract_is_exact_and_order_maps_are_inverses():
    contract = shadow_decoder_contract()
    assert contract["previewTeacherOnly"] is True
    assert contract["hardwareAuthorized"] is False
    assert contract["modelSha256"] == MODEL_SHA256
    assert contract["inputShape"] == [1, 994]
    assert contract["outputShape"] == [1, 29]
    assert contract["tokenDimension"] == 64
    assert contract["controlRateHz"] == 50
    assert contract["historyFrames"] == 10
    assert contract["jointOrder"] == list(G1_BODY_JOINT_NAMES)
    assert len(G1_DEFAULT_ANGLES_RAD) == ACTION_DIMENSION
    assert len(G1_ACTION_SCALES_RAD) == ACTION_DIMENSION
    assert len(G1_JOINT_LIMITS_RAD) == ACTION_DIMENSION

    for mujoco_index, isaac_index in enumerate(MUJOCO_INDEX_TO_ISAAC_INDEX):
        assert ISAAC_INDEX_TO_MUJOCO_INDEX[isaac_index] == mujoco_index


def test_verified_cuda_session_exposes_fail_closed_status_contract():
    decoder, session = _decoder()
    assert decoder.available
    assert session.calls == 1
    status = decoder.status_payload()
    assert status["available"] is True
    assert status["mode"] == "preview-teacher-only"
    assert status["hardwareAuthorized"] is False
    assert status["dropbearDynamicsAuthority"] is False
    assert status["model"]["verified"] is True
    assert status["model"]["input"]["shape"] == [1, 994]
    assert status["model"]["output"]["shape"] == [1, 29]
    assert status["runtime"]["cudaRequired"] is True
    assert status["runtime"]["cpuFallbackAllowed"] is False
    assert status["runtime"]["providers"][0] == "CUDAExecutionProvider"
    assert status["observation"]["historyOrder"] == ("oldest-to-newest-zero-padded")


def test_cpu_provider_and_wrong_model_shape_are_unavailable():
    cpu_decoder, _ = _decoder(providers=("CPUExecutionProvider",))
    assert not cpu_decoder.available
    assert (
        "CUDAExecutionProvider" in (cpu_decoder.status_payload()["availabilityReason"])
    )
    with pytest.raises(G1ShadowDecoderUnavailable):
        cpu_decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=0)

    wrong_decoder, _ = _decoder(input_shape=(1, 993))
    assert not wrong_decoder.available
    assert "float32[1,994]" in (wrong_decoder.status_payload()["availabilityReason"])


def test_first_observation_has_exact_994_field_layout_and_zero_padding():
    decoder, session = _decoder()
    token = np.linspace(-1.0, 1.0, TOKEN_DIMENSION, dtype=np.float32)
    q = decoder.decode_token(token, sequence=100)
    assert q == pytest.approx(G1_DEFAULT_ANGLES_RAD)

    observation = session.observations[1][0]
    assert observation.shape == (OBSERVATION_DIMENSION,)
    assert observation[slice(*OBSERVATION_SLICES["token_state"])] == pytest.approx(
        token
    )
    assert observation[
        slice(*OBSERVATION_SLICES["base_angular_velocity_history"])
    ] == pytest.approx(np.zeros(30))
    assert observation[
        slice(*OBSERVATION_SLICES["body_joint_position_history"])
    ] == pytest.approx(np.zeros(290))
    assert observation[
        slice(*OBSERVATION_SLICES["body_joint_velocity_history"])
    ] == pytest.approx(np.zeros(290))
    assert observation[
        slice(*OBSERVATION_SLICES["last_action_history"])
    ] == pytest.approx(np.zeros(290))

    gravity = observation[
        slice(*OBSERVATION_SLICES["projected_gravity_history"])
    ].reshape(10, 3)
    assert gravity[:-1] == pytest.approx(np.zeros((9, 3)))
    assert gravity[-1] == pytest.approx((0.0, 0.0, -1.0))


def test_action_reorder_scale_and_next_history_match_upstream_contract():
    action = np.zeros((1, ACTION_DIMENSION), dtype=np.float32)
    # Isaac index 1 is canonical MuJoCo right_hip_pitch index 6.
    action[0, 1] = 1.0
    decoder, session = _decoder(action=action)
    token = np.zeros(TOKEN_DIMENSION, dtype=np.float32)

    first_q = decoder.decode_token(
        token,
        sequence=20,
        steady_time_ns=1_000_000_000,
    )
    expected_delta = G1_ACTION_SCALES_RAD[6]
    assert first_q[6] == pytest.approx(G1_DEFAULT_ANGLES_RAD[6] + expected_delta)
    assert first_q[:6] == pytest.approx(G1_DEFAULT_ANGLES_RAD[:6])

    decoder.decode_token(
        token,
        sequence=21,
        steady_time_ns=1_000_000_000 + CONTROL_PERIOD_NS,
    )
    second_observation = session.observations[2][0]
    q_history = second_observation[
        slice(*OBSERVATION_SLICES["body_joint_position_history"])
    ].reshape(10, ACTION_DIMENSION)
    dq_history = second_observation[
        slice(*OBSERVATION_SLICES["body_joint_velocity_history"])
    ].reshape(10, ACTION_DIMENSION)
    action_history = second_observation[
        slice(*OBSERVATION_SLICES["last_action_history"])
    ].reshape(10, ACTION_DIMENSION)
    assert q_history[-1, 1] == pytest.approx(expected_delta)
    assert dq_history[-1, 1] == pytest.approx(
        expected_delta / (CONTROL_PERIOD_NS / 1e9)
    )
    assert action_history[-1, 1] == pytest.approx(1.0)


def test_shadow_position_is_mechanically_and_velocity_bounded():
    action = np.zeros((1, ACTION_DIMENSION), dtype=np.float32)
    action[0, 0] = 20.0
    decoder, _ = _decoder(action=action)
    q = decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=0)

    maximum_delta = MAX_SHADOW_JOINT_SPEED_RAD_S / 50.0
    assert q[0] == pytest.approx(G1_DEFAULT_ANGLES_RAD[0] + maximum_delta)
    assert G1_JOINT_LIMITS_RAD[0][0] <= q[0] <= G1_JOINT_LIMITS_RAD[0][1]
    status = decoder.status_payload()
    assert status["shadowState"]["lastVelocityClampCount"] >= 1
    assert status["shadowState"]["physicsAuthoritative"] is False


def test_sequence_and_optional_timestamp_cadence_reject_without_mutation():
    decoder, _ = _decoder()
    token = [0.0] * TOKEN_DIMENSION
    decoder.decode_token(token, sequence=7)
    with pytest.raises(G1ShadowCadenceError, match="expected contiguous"):
        decoder.decode_token(token, sequence=7)
    with pytest.raises(G1ShadowCadenceError, match="expected contiguous"):
        decoder.decode_token(token, sequence=9)
    status = decoder.status_payload()
    assert status["streamState"]["framesDecoded"] == 1
    assert status["streamState"]["lastSequence"] == 7
    decoder.decode_token(token, sequence=8)

    timed, _ = _decoder()
    timed.decode_token(token, sequence=0, steady_time_ns=500_000_000)
    with pytest.raises(G1ShadowCadenceError, match="50 Hz"):
        timed.decode_token(
            token,
            sequence=1,
            steady_time_ns=(500_000_000 + CONTROL_PERIOD_NS + CADENCE_TOLERANCE_NS + 1),
        )
    timed.decode_token(
        token,
        sequence=1,
        steady_time_ns=500_000_000 + CONTROL_PERIOD_NS,
    )


@pytest.mark.parametrize(
    ("token", "message"),
    [
        ([0.0] * 63, "shape"),
        ([0.0] * 63 + [float("nan")], "finite"),
        ([0.0] * 63 + [1.2501], "1.25"),
        ([False] * 64, "booleans"),
    ],
)
def test_invalid_tokens_fail_closed_without_disabling_valid_session(
    token: list[Any],
    message: str,
):
    decoder, _ = _decoder()
    with pytest.raises(G1ShadowContractError, match=message):
        decoder.decode_token(token, sequence=0)
    assert decoder.available
    assert decoder.status_payload()["streamState"]["framesDecoded"] == 0


@pytest.mark.parametrize(
    "bad_action",
    [
        np.zeros((29,), dtype=np.float32),
        np.full((1, 29), np.nan, dtype=np.float32),
        np.full((1, 29), 20.01, dtype=np.float32),
        np.zeros((1, 29), dtype=np.float64),
    ],
)
def test_bad_decoder_output_latches_runtime_unavailable(
    bad_action: np.ndarray,
):
    decoder, _ = _decoder(action=bad_action)
    with pytest.raises(G1ShadowContractError):
        decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=0)
    assert not decoder.available
    assert decoder.status_payload()["faultLatched"] is True
    with pytest.raises(G1ShadowDecoderUnavailable):
        decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=0)


def test_reset_starts_a_new_global_sequence_and_standing_history():
    decoder, session = _decoder()
    decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=40)
    decoder.reset()
    q = decoder.decode_token([0.0] * TOKEN_DIMENSION, sequence=0)
    assert q == pytest.approx(G1_DEFAULT_ANGLES_RAD)
    assert decoder.status_payload()["streamState"]["framesDecoded"] == 1

    reset_observation = session.observations[-1][0]
    q_history = reset_observation[
        slice(*OBSERVATION_SLICES["body_joint_position_history"])
    ]
    assert q_history == pytest.approx(np.zeros(290))
