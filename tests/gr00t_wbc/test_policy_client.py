from __future__ import annotations

import io
from pathlib import Path
import threading
from typing import Any

import numpy as np
import pytest

from integrations.gr00t_wbc.policy_client import (
    ACTION_HORIZON_FRAMES,
    G1SonicPolicyClient,
    G1SonicProtocolError,
    G1SonicServerError,
    HAND_JOINT_DIMENSION,
    MOTION_TOKEN_COMPONENT_ABS_LIMIT,
    MOTION_TOKEN_DIMENSION,
    SafePolicyWireSerializer,
    policy_client_contract,
    validate_unitree_g1_sonic_response,
)

msgpack = pytest.importorskip("msgpack")
msgpack_numpy = pytest.importorskip("msgpack_numpy")
zmq = pytest.importorskip("zmq")


ROOT = Path(__file__).resolve().parents[2]


def _valid_wire_action(*, prefixed: bool = False) -> dict[str, np.ndarray]:
    prefix = "action." if prefixed else ""
    return {
        f"{prefix}motion_token": np.zeros(
            (1, ACTION_HORIZON_FRAMES, MOTION_TOKEN_DIMENSION),
            dtype=np.float32,
        ),
        f"{prefix}left_hand_joints": np.zeros(
            (1, ACTION_HORIZON_FRAMES, HAND_JOINT_DIMENSION),
            dtype=np.float32,
        ),
        f"{prefix}right_hand_joints": np.zeros(
            (1, ACTION_HORIZON_FRAMES, HAND_JOINT_DIMENSION),
            dtype=np.float32,
        ),
    }


def test_static_contract_does_not_claim_a_server_or_checkpoint() -> None:
    contract = policy_client_contract()
    assert contract["embodiment"] == "UNITREE_G1_SONIC"
    assert contract["serverReachability"] == "unknown-until-ping"
    assert contract["serverIncluded"] is False
    assert contract["modelCheckpointIncluded"] is False
    assert contract["remoteAllowedByDefault"] is False
    assert contract["tlsProvidedByProtocol"] is False
    assert contract["actionShapes"]["motion_token"] == [1, 40, 64]
    assert contract["actionShapes"]["left_hand_joints"] == [1, 40, 7]


def test_safe_serializer_round_trips_numeric_numpy_without_pickle() -> None:
    original = {
        "float": np.arange(12, dtype=np.float32).reshape(3, 4),
        "integer": np.asarray([1, 2, 3], dtype=np.int64),
    }
    decoded = SafePolicyWireSerializer.from_bytes(
        SafePolicyWireSerializer.to_bytes(original)
    )
    np.testing.assert_array_equal(decoded["float"], original["float"])
    np.testing.assert_array_equal(decoded["integer"], original["integer"])
    assert decoded["float"].dtype == np.float32
    assert decoded["integer"].dtype == np.int64


def test_safe_serializer_is_cross_compatible_with_msgpack_numpy() -> None:
    original = {"motion_token": np.arange(64, dtype=np.float32)}

    decoded_by_upstream_codec = msgpack_numpy.unpackb(
        SafePolicyWireSerializer.to_bytes(original),
        raw=False,
    )
    np.testing.assert_array_equal(
        decoded_by_upstream_codec["motion_token"],
        original["motion_token"],
    )

    decoded_by_safe_codec = SafePolicyWireSerializer.from_bytes(
        msgpack_numpy.packb(original)
    )
    np.testing.assert_array_equal(
        decoded_by_safe_codec["motion_token"],
        original["motion_token"],
    )


def test_safe_serializer_rejects_object_array_encode() -> None:
    payload = {"unsafe": np.asarray([{"call": "pickle"}], dtype=object)}
    with pytest.raises(G1SonicProtocolError, match="object-bearing"):
        SafePolicyWireSerializer.to_bytes(payload)


def test_safe_serializer_rejects_forged_msgpack_numpy_pickle_envelope() -> None:
    forged = msgpack.packb(
        {
            b"nd": True,
            b"type": b"|O",
            b"kind": b"O",
            b"shape": [1],
            b"data": b"not-a-pickle",
        }
    )
    with pytest.raises(G1SonicProtocolError, match="pickle is disabled"):
        SafePolicyWireSerializer.from_bytes(forged)


def test_safe_serializer_rejects_legacy_object_npy_payload() -> None:
    buffer = io.BytesIO()
    np.save(
        buffer,
        np.asarray([{"unsafe": True}], dtype=object),
        allow_pickle=True,
    )
    forged = msgpack.packb(
        {
            "__ndarray_class__": True,
            "as_npy": buffer.getvalue(),
        }
    )
    with pytest.raises(G1SonicProtocolError, match="pickle-bearing"):
        SafePolicyWireSerializer.from_bytes(forged)


def test_response_validator_normalizes_prefix_and_returns_read_only_copies() -> None:
    raw_action = _valid_wire_action(prefixed=True)
    raw_action["action.task_progress"] = np.asarray([0.5], dtype=np.float32)
    action, info = validate_unitree_g1_sonic_response(
        [raw_action, {"server_latency_ms": 12.0}]
    )

    assert tuple(action) == (
        "motion_token",
        "left_hand_joints",
        "right_hand_joints",
    )
    assert info == {"server_latency_ms": 12.0}
    assert action["motion_token"].shape == (1, 40, 64)
    assert action["left_hand_joints"].shape == (1, 40, 7)
    assert action["motion_token"].dtype == np.float32
    assert not action["motion_token"].flags.writeable
    assert action["motion_token"] is not raw_action["action.motion_token"]


@pytest.mark.parametrize(
    ("mutation", "match"),
    (
        (
            lambda action: action.__setitem__(
                "motion_token",
                np.zeros((40, 64), dtype=np.float32),
            ),
            "shape",
        ),
        (
            lambda action: action.__setitem__(
                "left_hand_joints",
                np.zeros((1, 40, 7), dtype=np.float64),
            ),
            "dtype",
        ),
        (
            lambda action: action.__setitem__(
                "right_hand_joints",
                np.full((1, 40, 7), np.nan, dtype=np.float32),
            ),
            "non-finite",
        ),
        (
            lambda action: action.__setitem__(
                "motion_token",
                np.full(
                    (1, 40, 64),
                    MOTION_TOKEN_COMPONENT_ABS_LIMIT + 0.01,
                    dtype=np.float32,
                ),
            ),
            "absolute component limit",
        ),
        (
            lambda action: action.pop("right_hand_joints"),
            "missing",
        ),
        (
            lambda action: action.__setitem__(
                "unexpected",
                np.zeros((1,), dtype=np.float32),
            ),
            "unexpected",
        ),
    ),
)
def test_response_validator_rejects_contract_violations(
    mutation: Any,
    match: str,
) -> None:
    action = _valid_wire_action()
    mutation(action)
    with pytest.raises(G1SonicProtocolError, match=match):
        validate_unitree_g1_sonic_response([action, {}])


def test_non_loopback_is_rejected_unless_explicitly_allowed() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        G1SonicPolicyClient("policy.example.test")

    client = G1SonicPolicyClient(
        "192.0.2.10",
        timeout_ms=10,
        allow_remote=True,
    )
    try:
        assert client.endpoint == "tcp://192.0.2.10:5550"
    finally:
        client.close()


def test_official_get_action_wire_request_and_response_on_loopback() -> None:
    context = zmq.Context()
    server = context.socket(zmq.REP)
    server.setsockopt(zmq.LINGER, 0)
    port = server.bind_to_random_port("tcp://127.0.0.1")
    captured: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def serve_once() -> None:
        try:
            request = SafePolicyWireSerializer.from_bytes(server.recv())
            captured.append(request)
            response = [
                _valid_wire_action(prefixed=True),
                {"policy": "mock-only"},
            ]
            server.send(SafePolicyWireSerializer.to_bytes(response))
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    client = G1SonicPolicyClient(
        "127.0.0.1",
        port,
        timeout_ms=2_000,
        api_token="test-token",
    )
    try:
        observation = {
            "video.ego_view": np.zeros(
                (1, 1, 2, 2, 3),
                dtype=np.uint8,
            )
        }
        action, info = client.get_action(
            observation,
            options={"execution_horizon": 40},
        )
    finally:
        client.close()
        thread.join(timeout=2)
        server.close(linger=0)
        context.term()

    assert not thread.is_alive()
    assert errors == []
    assert action["motion_token"].shape == (1, 40, 64)
    assert info == {"policy": "mock-only"}
    assert captured[0]["endpoint"] == "get_action"
    assert captured[0]["api_token"] == "test-token"
    assert captured[0]["data"]["options"] == {"execution_horizon": 40}
    assert captured[0]["data"]["observation"]["video.ego_view"].shape == (
        1,
        1,
        2,
        2,
        3,
    )


def test_server_error_response_fails_closed() -> None:
    context = zmq.Context()
    server = context.socket(zmq.REP)
    server.setsockopt(zmq.LINGER, 0)
    port = server.bind_to_random_port("tcp://127.0.0.1")

    def serve_once() -> None:
        server.recv()
        server.send(
            SafePolicyWireSerializer.to_bytes({"error": "wrong embodiment checkpoint"})
        )

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    client = G1SonicPolicyClient("localhost", port, timeout_ms=2_000)
    try:
        with pytest.raises(G1SonicServerError, match="wrong embodiment checkpoint"):
            client.get_action({})
    finally:
        client.close()
        thread.join(timeout=2)
        server.close(linger=0)
        context.term()
