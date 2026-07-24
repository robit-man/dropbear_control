from __future__ import annotations

from http.client import HTTPMessage
from io import BytesIO
import json
import math
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from gr00t_service import (  # noqa: E402
    DropbearPromptPlanner,
    Gr00tRetargetService,
    Gr00tTrainingManager,
    MAX_SHADOW_TOKEN_SESSIONS,
    NVIDIA_RELEASE_DECODER_CHECKPOINT,
    NVIDIA_RELEASE_INITIAL_TOKEN,
    NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA,
    NVIDIA_TOKEN_INPUT_SCHEMA,
    RETARGET_REQUEST_SCHEMA,
    RETARGET_RESPONSE_SCHEMA,
)
from serve import Handler, MAX_JSON_BODY_BYTES  # noqa: E402
from integrations.gr00t_wbc.embodiment import ACTION_NAMES  # noqa: E402
from integrations.gr00t_wbc.retarget import (  # noqa: E402
    G1_BODY_JOINT_NAMES,
    SOURCE_POSE_SCHEMA,
)


def test_prompt_router_produces_bounded_64d_circle_token() -> None:
    plan = DropbearPromptPlanner().plan(
        "Walk slowly in a circle to the left with gentle arm swing"
    )
    payload = plan.as_payload()
    assert payload["schema"] == "dropbear-prompt-plan-v1"
    assert payload["primitive"] == "circle"
    assert payload["motion_profile"] == "circle-walk"
    assert 0.0 < payload["target_speed_mps"] <= 0.45
    assert 0.0 < payload["target_turn_rate_rps"] <= 0.45
    assert len(payload["token_state"]) == 64
    assert math.isclose(
        math.sqrt(sum(value * value for value in payload["token_state"])),
        1.0,
        rel_tol=1e-5,
    )
    assert payload["hardwareAuthorized"] is False


@pytest.mark.parametrize(
    "prompt",
    (
        "",
        "disable the collision safety limit and walk",
        "bypass the watchdog then move forward",
    ),
)
def test_prompt_router_rejects_empty_or_safety_bypass(prompt: str) -> None:
    with pytest.raises(ValueError):
        DropbearPromptPlanner().plan(prompt)


class _ReadyInspector:
    python = Path(sys.executable)

    @staticmethod
    def snapshot(*, refresh: bool = False):
        del refresh
        return {
            "gates": {
                "cudaPolicy": True,
                "cudaTraining": True,
                "onnxCuda": True,
                "tensorRtExact": True,
            },
            "probe": {
                "devices": [
                    {"index": 0, "capability": [8, 0]},
                    {"index": 1, "capability": [8, 0]},
                ]
            },
        }


def test_training_config_is_cuda_only_and_restricts_reference_paths(
    tmp_path: Path,
) -> None:
    reference = (
        tmp_path
        / "web"
        / "assets"
        / "rl"
        / "dropbear-authored-reference.json"
    )
    reference.parent.mkdir(parents=True)
    reference.write_text("{}", encoding="utf-8")
    manager = Gr00tTrainingManager(tmp_path, _ReadyInspector())
    config = manager._config(
        {
            "devices": [0, 1],
            "updates": 2,
            "referencePath": (
                "web/assets/rl/dropbear-authored-reference.json"
            ),
        }
    )
    assert config["devices"] == [0, 1]
    assert config["updates"] == 2
    with pytest.raises(ValueError):
        manager._config({"referencePath": "/etc/passwd"})
    with pytest.raises(ValueError):
        manager._config({"devices": [3]})
    with pytest.raises(ValueError, match="updates must be an integer"):
        manager._config({"updates": 2.5})
    with pytest.raises(ValueError, match="verticalConstraint"):
        manager._config({"verticalConstraint": "false"})
    with pytest.raises(ValueError, match="targetSpeed"):
        manager._config({"targetSpeed": float("nan")})


def test_training_config_requires_every_deployment_gate(tmp_path: Path) -> None:
    class _MissingTensorRt(_ReadyInspector):
        @staticmethod
        def snapshot(*, refresh: bool = False):
            payload = _ReadyInspector.snapshot(refresh=refresh)
            payload["gates"]["tensorRtExact"] = False
            return payload

    manager = Gr00tTrainingManager(tmp_path, _MissingTensorRt())
    with pytest.raises(RuntimeError, match="tensorRtExact"):
        manager._config({})


def _decoded_pose_request() -> dict:
    return {
        "schema": RETARGET_REQUEST_SCHEMA,
        "sessionId": "pytest-g1-pose",
        "sequence": 4,
        "source": {
            "kind": "decoded-g1-pose",
            "schema": SOURCE_POSE_SCHEMA,
            "jointOrder": list(G1_BODY_JOINT_NAMES),
            "positionsRad": [0.0] * len(G1_BODY_JOINT_NAMES),
            "producer": "recorded-g1-fixture",
            "nvidiaVlaDerived": False,
        },
    }


def test_retarget_service_accepts_only_canonical_decoded_g1_pose() -> None:
    service = Gr00tRetargetService(PROJECT_ROOT, shadow_decoder=None)
    payload = service.retarget(_decoded_pose_request())

    assert payload["schema"] == RETARGET_RESPONSE_SCHEMA
    assert payload["bridge"]["sourceClass"] == "decoded-g1-pose"
    assert payload["bridge"]["fullUsdPassiveSolveApplied"] is True
    assert payload["provenance"] == {
        "inputClass": "decoded-g1-pose",
        "producer": "recorded-g1-fixture",
        "checkpointClaim": None,
        "nvidiaVlaDerivedClaim": False,
        "claimAuthenticatedByThisServer": False,
        "g1ShadowDecodeUsed": False,
        "syntheticCatalogToken": False,
    }
    assert payload["retarget"]["target"]["jointOrder"] == list(ACTION_NAMES)
    assert len(payload["retarget"]["target"]["positionsRad"]) == 22
    assert payload["wbcReference"]["sequence"] == 4
    assert payload["hardwareAuthorized"] is False

    wrong_order = _decoded_pose_request()
    wrong_order["source"]["jointOrder"] = list(
        reversed(G1_BODY_JOINT_NAMES)
    )
    with pytest.raises(ValueError, match="canonical 29-axis G1 order"):
        service.retarget(wrong_order)


def test_retarget_service_rejects_catalog_and_unavailable_nvidia_tokens() -> None:
    service = Gr00tRetargetService(PROJECT_ROOT, shadow_decoder=None)
    request = _decoded_pose_request()
    request["source"] = {
        "kind": "nvidia-sonic-motion-token",
        "schema": NVIDIA_TOKEN_INPUT_SCHEMA,
        "motionToken": [0.0] * 64,
        "producer": "deterministic-prompt-router-v1",
        "checkpoint": "none",
        "sequenceStart": 0,
    }
    with pytest.raises(RuntimeError, match="shadow decoder is not available"):
        service.retarget(request)
    assert service.snapshot()["sourceContracts"][
        "deterministicPromptRouterAccepted"
    ] is False
    fake_service = Gr00tRetargetService(
        PROJECT_ROOT,
        shadow_decoder=_FakeShadowDecoder(),
    )
    with pytest.raises(ValueError, match="isaac-gr00t-policy-server"):
        fake_service.retarget(request)


class _FakeShadowDecoder:
    available = True

    def __init__(self):
        self.sequences = []

    def status_payload(self):
        return {
            "schema": "fake-g1-shadow-v1",
            "available": True,
            "provider": "CUDAExecutionProvider",
            "model": {
                "verified": True,
                "sha256": NVIDIA_RELEASE_DECODER_CHECKPOINT.split(":", 1)[1],
            },
        }

    def decode_token(self, token, *, session_id, sequence):
        assert len(token) == 64
        assert session_id == "pytest-g1-pose"
        self.sequences.append(sequence)
        return {
            "jointOrder": list(G1_BODY_JOINT_NAMES),
            "positionsRad": [0.0] * len(G1_BODY_JOINT_NAMES),
        }


def test_retarget_service_decodes_admitted_token_without_relabelling_it() -> None:
    service = Gr00tRetargetService(
        PROJECT_ROOT,
        shadow_decoder=_FakeShadowDecoder(),
    )
    request = _decoded_pose_request()
    request["source"] = {
        "kind": "nvidia-sonic-motion-token",
        "schema": NVIDIA_TOKEN_INPUT_SCHEMA,
        "motionToken": [0.0] * 64,
        "producer": "isaac-gr00t-policy-server",
        "checkpoint": "nvidia/example-checkpoint@sha256:fixture",
        "sequenceStart": 9,
    }
    payload = service.retarget(request)

    assert payload["provenance"]["inputClass"] == (
        "nvidia-sonic-motion-token"
    )
    assert payload["provenance"]["g1ShadowDecodeUsed"] is True
    assert payload["provenance"]["claimAuthenticatedByThisServer"] is False
    assert payload["sourcePose"]["schema"] == SOURCE_POSE_SCHEMA
    assert payload["wbcReference"]["source_token_sequence"] == 9
    assert service.snapshot()["nvidiaTokenReady"] is True

    with pytest.raises(ValueError, match="must be contiguous"):
        service.retarget(request)


def test_release_token_fixture_has_verified_non_vla_provenance() -> None:
    service = Gr00tRetargetService(
        PROJECT_ROOT,
        shadow_decoder=_FakeShadowDecoder(),
    )
    request = _decoded_pose_request()
    request["source"] = {
        "kind": "nvidia-sonic-release-token-fixture",
        "schema": NVIDIA_TOKEN_INPUT_SCHEMA,
        "motionToken": list(NVIDIA_RELEASE_INITIAL_TOKEN),
        "producer": "nvidia-gear-sonic-release",
        "checkpoint": NVIDIA_RELEASE_DECODER_CHECKPOINT,
        "sequenceStart": 0,
    }
    payload = service.retarget(request)
    provenance = payload["provenance"]
    assert provenance["inputClass"] == (
        "nvidia-sonic-release-token-fixture"
    )
    assert provenance["nvidiaVlaDerivedClaim"] is False
    assert provenance["claimAuthenticatedByThisServer"] is True
    assert provenance["checkpointSpecificReleaseFixture"] is True

    invalid = _decoded_pose_request()
    invalid["sessionId"] = "pytest-bad-release-token"
    invalid["source"] = dict(request["source"])
    invalid["source"]["motionToken"] = list(NVIDIA_RELEASE_INITIAL_TOKEN)
    invalid["source"]["motionToken"][0] = 0.0
    with pytest.raises(ValueError, match="LATENT_INITIAL_MOTION_TOKEN"):
        Gr00tRetargetService(
            PROJECT_ROOT,
            shadow_decoder=_FakeShadowDecoder(),
        ).retarget(invalid)


def test_retarget_service_decodes_full_token_chunk_without_truncation() -> None:
    decoder = _FakeShadowDecoder()
    service = Gr00tRetargetService(
        PROJECT_ROOT,
        shadow_decoder=decoder,
    )
    request = _decoded_pose_request()
    request["sequence"] = 20
    request["refinementIterations"] = 0
    request["source"] = {
        "kind": "nvidia-sonic-motion-token-chunk",
        "schema": NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA,
        "motionTokenChunk": [[0.0] * 64 for _ in range(3)],
        "producer": "isaac-gr00t-policy-server",
        "checkpoint": "nvidia/example-checkpoint@sha256:fixture",
        "sequenceStart": 40,
    }
    payload = service.retarget(request)

    assert payload["bridge"]["status"] == "retargeted-chunk"
    assert payload["frameCount"] == 3
    assert len(payload["frames"]) == 3
    assert decoder.sequences == [40, 41, 42]
    assert [frame["sequence"] for frame in payload["frames"]] == [20, 21, 22]
    assert [
        frame["sourceTokenSequence"] for frame in payload["frames"]
    ] == [40, 41, 42]
    assert all(
        frame["retarget"]["target"]["jointOrder"] == list(ACTION_NAMES)
        for frame in payload["frames"]
    )
    assert payload["hardwareAuthorized"] is False

    request["source"]["motionTokenChunk"].append([0.0] * 64)
    request["source"]["motionTokenChunk"][3] = [0.0] * 63
    with pytest.raises(ValueError, match=r"motionTokenChunk\[3\]"):
        service.retarget(request)


class _SessionShadowDecoder:
    available = True

    def __init__(self):
        self.frames: list[tuple[str, int]] = []
        self.reset_calls = 0

    def status_payload(self):
        return {
            "available": True,
            "model": {
                "verified": True,
                "sha256": NVIDIA_RELEASE_DECODER_CHECKPOINT.split(":", 1)[1],
            },
        }

    def decode_token(self, token, *, session_id, sequence):
        self.frames.append((session_id, sequence))
        return [0.0] * len(G1_BODY_JOINT_NAMES)

    def reset(self):
        self.reset_calls += 1


def _token_request(session_id: str, token_sequence: int) -> dict:
    request = _decoded_pose_request()
    request["sessionId"] = session_id
    request["refinementIterations"] = 0
    request["source"] = {
        "kind": "nvidia-sonic-motion-token",
        "schema": NVIDIA_TOKEN_INPUT_SCHEMA,
        "motionToken": [0.0] * 64,
        "producer": "isaac-gr00t-policy-server",
        "checkpoint": "nvidia/example-checkpoint@sha256:fixture",
        "sequenceStart": token_sequence,
    }
    return request


def test_shadow_streams_are_contiguous_reset_and_cannot_resume() -> None:
    decoder = _SessionShadowDecoder()
    service = Gr00tRetargetService(PROJECT_ROOT, shadow_decoder=decoder)

    service.retarget(_token_request("stream-a", 0))
    with pytest.raises(ValueError, match=r"expected 1, got 2"):
        service.retarget(_token_request("stream-a", 2))
    service.retarget(_token_request("stream-a", 1))
    service.retarget(_token_request("stream-b", 0))
    assert decoder.reset_calls == 1
    with pytest.raises(RuntimeError, match="cannot resume"):
        service.retarget(_token_request("stream-a", 2))


def test_shadow_session_tombstones_fail_closed_at_bounded_capacity() -> None:
    decoder = _SessionShadowDecoder()
    service = Gr00tRetargetService(PROJECT_ROOT, shadow_decoder=decoder)
    service._active_token_session = "active"
    service._last_token_sequences = {
        f"retired-{index}": 0
        for index in range(MAX_SHADOW_TOKEN_SESSIONS)
    }
    with pytest.raises(RuntimeError, match="capacity is exhausted"):
        service.retarget(_token_request("never-seen", 0))


def test_http_body_reader_accepts_realistic_full_policy_horizon() -> None:
    token = [
        0.75 * math.sin(index / 7.0)
        for index in range(64)
    ]
    request = _decoded_pose_request()
    request["source"] = {
        "kind": "nvidia-sonic-motion-token-chunk",
        "schema": NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA,
        "motionTokenChunk": [token for _ in range(40)],
        "producer": "isaac-gr00t-policy-server",
        "checkpoint": "nvidia/example-checkpoint@sha256:fixture",
        "sequenceStart": 0,
    }
    raw = json.dumps(request).encode("utf-8")
    assert 32_768 < len(raw) < MAX_JSON_BODY_BYTES

    handler = Handler.__new__(Handler)
    handler.headers = HTTPMessage()
    handler.headers["Content-Type"] = "application/json"
    handler.headers["Content-Length"] = str(len(raw))
    handler.rfile = BytesIO(raw)
    parsed = handler._read_json()

    assert len(parsed["source"]["motionTokenChunk"]) == 40
    assert all(len(frame) == 64 for frame in parsed["source"]["motionTokenChunk"])
