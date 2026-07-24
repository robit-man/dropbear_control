"""Loopback-only GR00T/SONIC integration status and prompt planning.

The browser service deliberately distinguishes three deployment gates:

* ``cuda_policy``: the local Dropbear token-conditioned controller can train
  and execute on CUDA.
* ``authoritative_sim``: Isaac Lab/PhysX is installed and the complete
  Dropbear closed-loop asset has passed its external validation suite.
* ``hardware``: an independently reviewed ROS 2/HIL safety admission exists.

Only the first gate can be satisfied by this development server.  The other
two remain fail-closed even when a CUDA smoke test succeeds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import deque
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Any
import uuid


TOKEN_DIMENSION = 64
MAX_PROMPT_LENGTH = 256
MAX_SHADOW_TOKEN_SESSIONS = 128
G1_POSE_DIMENSION = 29
RETARGET_REQUEST_SCHEMA = "dropbear-gr00t-retarget-request-v1"
RETARGET_RESPONSE_SCHEMA = "dropbear-gr00t-retarget-response-v1"
NVIDIA_TOKEN_INPUT_SCHEMA = "nvidia-gr00t-sonic-motion-token-64d-v1"
NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA = (
    "nvidia-gr00t-sonic-motion-token-chunk-40x64-v1"
)
NVIDIA_RELEASE_DECODER_CHECKPOINT = (
    "sha256:"
    "c7241a123eaa36b5d64bad19540efde93cac1ad443bd4572fd12ca99898118ed"
)
NVIDIA_RELEASE_INITIAL_TOKEN = (
    -0.0625, 0.0, -0.0625, -0.125, -0.1875, -0.0625, 0.1875,
    0.25, 0.1875, -0.125, 0.0625, -0.0625, -0.25, -0.25,
    -0.3125, -0.0625, 0.0, -0.0625, -0.125, -0.1875, 0.0,
    -0.25, 0.0, -0.25, -0.0625, 0.0625, 0.125, -0.125,
    0.25, 0.1875, 0.25, -0.125, 0.125, 0.1875, -0.0625,
    0.0, -0.1875, -0.1875, 0.25, 0.0, 0.0, -0.125,
    0.0625, 0.0, -0.0625, -0.0625, 0.1875, -0.0625, 0.0,
    0.0625, 0.125, 0.0625, 0.125, 0.0625, 0.125, 0.0,
    0.125, 0.1875, 0.0, 0.0, 0.0625, 0.0625, 0.1875, 0.0625,
)
_AUTO_SHADOW_DECODER = object()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _require_finite_json(value: Any, *, label: str = "payload") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, item in value.items():
            _require_finite_json(item, label=f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_finite_json(item, label=f"{label}[{index}]")


def _strict_json_loads(raw: str) -> Any:
    value = json.loads(raw, parse_constant=_reject_json_constant)
    _require_finite_json(value)
    return value


@dataclass(frozen=True)
class PromptPlan:
    """A bounded high-level reference plan, never a hardware command."""

    prompt: str
    primitive: str
    motion_profile: str
    target_speed_mps: float
    target_turn_rate_rps: float
    duration_seconds: float
    stride_scale: float
    knee_scale: float
    arm_swing_scale: float
    token_state: tuple[float, ...]
    confidence: float
    notes: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "schema": "dropbear-prompt-plan-v1",
                "referenceRateHz": 50,
                "tokenDimension": TOKEN_DIMENSION,
                "tokenSource": "deterministic-prompt-router-v1",
                "hardwareAuthorized": False,
            }
        )
        return payload


class DropbearPromptPlanner:
    """Convert a small, inspectable language surface into motion references.

    This is the safe bootstrap layer described in the GR00T integration plan.
    It provides deterministic catalog-routing metadata while a learned
    Isaac-GR00T VLA is not installed.  The generated token is not compatible
    with the state-token-trained local CUDA checkpoint and is never submitted
    to that policy.
    """

    _unsafe = re.compile(
        r"\b(disable|bypass|ignore|remove)\b.{0,30}\b"
        r"(limit|watchdog|estop|e-stop|safety|collision)\b",
        re.IGNORECASE,
    )

    def plan(self, raw_prompt: Any) -> PromptPlan:
        if not isinstance(raw_prompt, str):
            raise ValueError("prompt must be a string")
        prompt = " ".join(raw_prompt.strip().split())
        if not prompt:
            raise ValueError("prompt is required")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(
                f"prompt must be at most {MAX_PROMPT_LENGTH} characters"
            )
        if self._unsafe.search(prompt):
            raise ValueError("prompt requests a safety-control bypass")

        text = prompt.casefold()
        primitive = "stand"
        profile = "gentle-forward"
        speed = 0.0
        turn = 0.0
        duration = 6.0
        stride = 0.0
        knee = 0.15
        arm = 0.15
        confidence = 0.72
        notes: list[str] = [
            "development reference only",
            "closed-loop knee and elbow projection remains active",
        ]

        if any(word in text for word in ("walk", "step", "move", "go")):
            primitive = "walk"
            speed = 0.26
            stride = 0.62
            knee = 0.42
            arm = 0.55
            confidence = 0.92
        if any(word in text for word in ("circle", "orbit")):
            primitive = "circle"
            profile = "circle-walk"
            speed = 0.22
            turn = 0.28
            stride = 0.56
            knee = 0.38
            arm = 0.50
            confidence = 0.95
        elif "turn" in text or "rotate" in text:
            primitive = "turn"
            speed = 0.08
            turn = 0.28
            stride = 0.30
            knee = 0.30
            arm = 0.30
            confidence = 0.88
        elif any(word in text for word in ("crouch", "squat", "kneel")):
            primitive = "crouch"
            speed = 0.0
            stride = 0.0
            knee = 0.65
            arm = 0.20
            duration = 4.0
            confidence = 0.90
        elif "wave" in text:
            primitive = "wave"
            speed = 0.0
            stride = 0.0
            knee = 0.18
            arm = 0.85
            duration = 5.0
            confidence = 0.84

        if any(word in text for word in ("backward", "backwards", "reverse")):
            speed = -max(abs(speed), 0.16)
            notes.append("reverse locomotion requested")
        if "right" in text:
            turn = -max(abs(turn), 0.24)
        elif "left" in text:
            turn = max(abs(turn), 0.24)
        if any(word in text for word in ("slow", "slowly", "gentle", "gently")):
            speed *= 0.65
            turn *= 0.70
            stride *= 0.78
            knee *= 0.82
            notes.append("gentle speed envelope applied")
        if any(word in text for word in ("fast", "quick", "quickly")):
            speed *= 1.25
            turn *= 1.15
            stride *= 1.10
            notes.append("request capped by development envelope")

        speed = max(-0.35, min(0.45, speed))
        turn = max(-0.45, min(0.45, turn))
        stride = max(0.0, min(0.85, stride))
        knee = max(0.0, min(0.75, knee))
        arm = max(0.0, min(0.90, arm))
        token = self._token(
            prompt,
            primitive=primitive,
            speed=speed,
            turn=turn,
            stride=stride,
            knee=knee,
            arm=arm,
        )
        return PromptPlan(
            prompt=prompt,
            primitive=primitive,
            motion_profile=profile,
            target_speed_mps=speed,
            target_turn_rate_rps=turn,
            duration_seconds=duration,
            stride_scale=stride,
            knee_scale=knee,
            arm_swing_scale=arm,
            token_state=token,
            confidence=confidence,
            notes=tuple(notes),
        )

    @staticmethod
    def _token(
        prompt: str,
        *,
        primitive: str,
        speed: float,
        turn: float,
        stride: float,
        knee: float,
        arm: float,
    ) -> tuple[float, ...]:
        primitives = ("stand", "walk", "circle", "turn", "crouch", "wave")
        token = [0.0] * TOKEN_DIMENSION
        if primitive in primitives:
            token[primitives.index(primitive)] = 1.0
        token[8:14] = [speed, turn, stride, knee, arm, 1.0]
        digest = hashlib.sha256(prompt.casefold().encode("utf-8")).digest()
        for index in range(14, TOKEN_DIMENSION):
            token[index] = (digest[(index - 14) % len(digest)] / 127.5) - 1.0
        norm = math.sqrt(sum(value * value for value in token)) or 1.0
        return tuple(round(value / norm, 7) for value in token)


class Gr00tRetargetService:
    """Strict G1-pose/token bridge into the 22-axis Dropbear contract.

    Decoded G1 poses are accepted directly for fixture, recorded-rollout, and
    integration testing. A 64D token is accepted only when a local G1 SONIC
    shadow decoder is present and ready. The deterministic prompt planner
    above is deliberately excluded from this service because its catalog token
    is not an NVIDIA GR00T/SONIC latent.
    """

    _session_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    _decoded_source_keys = frozenset(
        {
            "kind",
            "schema",
            "jointOrder",
            "positionsRad",
            "producer",
            "nvidiaVlaDerived",
            "checkpoint",
        }
    )
    _token_source_keys = frozenset(
        {
            "kind",
            "schema",
            "motionToken",
            "producer",
            "checkpoint",
            "sequenceStart",
        }
    )
    _token_chunk_source_keys = frozenset(
        {
            "kind",
            "schema",
            "motionTokenChunk",
            "producer",
            "checkpoint",
            "sequenceStart",
        }
    )

    def __init__(
        self,
        project_root: Path,
        shadow_decoder: Any = _AUTO_SHADOW_DECODER,
    ) -> None:
        self.project_root = project_root.resolve()
        self._lock = threading.RLock()
        self._shadow_setting = shadow_decoder
        self._shadow_decoder: Any | None = (
            None if shadow_decoder is _AUTO_SHADOW_DECODER else shadow_decoder
        )
        self._shadow_error: str | None = None
        self._active_token_session: str | None = None
        self._last_token_sequences: dict[str, int] = {}
        self._retargeter: Any | None = None
        self._retarget_contract: dict[str, Any] | None = None
        self._source_verification: dict[str, Any] | None = None
        self._retarget_error: str | None = None
        try:
            project_import_root = str(self.project_root)
            if project_import_root not in sys.path:
                sys.path.insert(0, project_import_root)
            from integrations.gr00t_wbc.retarget import retargeting_contract
            from integrations.gr00t_wbc.usd_retarget import (
                G1UsdDropbearRetargeter,
            )

            self._retargeter = G1UsdDropbearRetargeter(self.project_root)
            self._retarget_contract = retargeting_contract()
            self._source_verification = (
                self._retargeter.source_verification_payload()
            )
        except (ImportError, OSError, TypeError, ValueError) as error:
            self._retarget_error = str(error)

    @staticmethod
    def _bounded_string(value: Any, *, label: str, maximum: int = 160) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string")
        result = value.strip()
        if not result or len(result) > maximum:
            raise ValueError(f"{label} must contain 1..{maximum} characters")
        return result

    @staticmethod
    def _non_negative_integer(value: Any, *, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value

    @staticmethod
    def _exact_keys(
        payload: dict[str, Any],
        *,
        allowed: frozenset[str],
        required: frozenset[str],
        label: str,
    ) -> None:
        missing = sorted(required - set(payload))
        extra = sorted(set(payload) - allowed)
        if missing or extra:
            raise ValueError(
                f"{label} fields mismatch; missing={missing}, extra={extra}"
            )

    @staticmethod
    def _finite_vector(
        value: Any,
        *,
        length: int,
        label: str,
    ) -> list[float]:
        if not isinstance(value, list) or len(value) != length:
            raise ValueError(f"{label} must contain exactly {length} values")
        if any(
            isinstance(item, bool) or not isinstance(item, (int, float))
            for item in value
        ):
            raise ValueError(f"{label} must contain only JSON numbers")
        result = [float(item) for item in value]
        if not all(math.isfinite(item) for item in result):
            raise ValueError(f"{label} must contain only finite values")
        return result

    def _load_shadow_decoder(self) -> Any | None:
        if self._shadow_setting is not _AUTO_SHADOW_DECODER:
            return self._shadow_decoder
        if self._shadow_decoder is not None:
            return self._shadow_decoder
        # A decoder module can be added while the dashboard remains live, so
        # retry after a previous import miss instead of caching it forever.
        importlib.invalidate_caches()
        try:
            # Importing torch first preloads the matching CUDA/cuDNN runtime
            # libraries used by this workspace's ONNX Runtime CUDA provider.
            importlib.import_module("torch")
            try:
                module = importlib.import_module(
                    "integrations.gr00t_wbc.g1_shadow_decoder"
                )
            except ImportError:
                module = importlib.import_module(
                    "integrations.gr00t_wbc.g1_shadow"
                )
            factory = getattr(module, "create_g1_shadow_decoder", None)
            if callable(factory):
                decoder = factory(self.project_root)
            else:
                decoder_type = getattr(module, "G1ShadowDecoder", None)
                if decoder_type is None:
                    decoder_type = getattr(
                        module,
                        "G1SonicShadowDecoder",
                        None,
                    )
                if decoder_type is None:
                    raise RuntimeError(
                        "g1_shadow exports no supported decoder factory"
                    )
                decoder = decoder_type(self.project_root)
            self._shadow_decoder = decoder
            self._shadow_error = None
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as error:
            self._shadow_error = str(error)
            self._shadow_decoder = None
        return self._shadow_decoder

    @staticmethod
    def _shadow_status(decoder: Any | None, error: str | None) -> dict[str, Any]:
        status: dict[str, Any] = {}
        if decoder is not None:
            for name in ("status_payload", "snapshot", "status"):
                callback = getattr(decoder, name, None)
                if callable(callback):
                    try:
                        candidate = callback()
                    except (OSError, RuntimeError, TypeError, ValueError) as exc:
                        status = {"error": str(exc)}
                    else:
                        if isinstance(candidate, dict):
                            status = dict(candidate)
                    break
            raw_available = getattr(decoder, "available", None)
            if callable(raw_available):
                try:
                    raw_available = raw_available()
                except (OSError, RuntimeError, TypeError, ValueError):
                    raw_available = False
            if raw_available is None:
                raw_available = status.get(
                    "available",
                    status.get("ready", False),
                )
            available = raw_available is True
        else:
            available = False
        return {
            "available": available,
            "implementation": (
                type(decoder).__name__ if decoder is not None else None
            ),
            "error": error or status.get("error"),
            "details": {
                key: value
                for key, value in status.items()
                if key not in {"available", "ready", "error"}
            },
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            decoder = self._load_shadow_decoder()
            shadow = self._shadow_status(decoder, self._shadow_error)
            decoded_ready = self._retargeter is not None
            return {
                "schema": "dropbear-gr00t-retarget-bridge-status-v1",
                "decodedG1PoseReady": decoded_ready,
                "nvidiaTokenReady": decoded_ready and shadow["available"],
                "shadowDecoder": shadow,
                "sourceContracts": {
                    "decodedG1Pose": "unitree-g1-body-position-v1",
                    "nvidiaMotionToken": NVIDIA_TOKEN_INPUT_SCHEMA,
                    "nvidiaMotionTokenChunk": (
                        NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA
                    ),
                    "nvidiaReleaseTokenFixture": {
                        "kind": "nvidia-sonic-release-token-fixture",
                        "producer": "nvidia-gear-sonic-release",
                        "checkpoint": NVIDIA_RELEASE_DECODER_CHECKPOINT,
                        "nvidiaVlaDerived": False,
                    },
                    "maximumTokenChunkFrames": 40,
                    "deterministicPromptRouterAccepted": False,
                },
                "target": {
                    "actionCount": 22,
                    "usdMotorTargets": True,
                    "usdTaskSpaceKinematics": decoded_ready,
                    "fullUsdPassiveSolve": decoded_ready,
                    "contactDynamics": False,
                    "contactDynamicsAuthority": "Isaac/PhysX",
                    "hardwareAuthorized": False,
                },
                "retargetContract": self._retarget_contract,
                "sourceVerification": self._source_verification,
                "error": self._retarget_error,
            }

    @staticmethod
    def _extract_decoded_pose(
        decoded: Any,
        expected_order: tuple[str, ...],
    ) -> list[float]:
        joint_order: Any = None
        values: Any = decoded
        if isinstance(decoded, dict):
            joint_order = decoded.get(
                "jointOrder",
                decoded.get("joint_order"),
            )
            for key in (
                "positionsRad",
                "jointPositionsRad",
                "joint_positions_rad",
                "g1_joint_positions_rad",
                "q",
            ):
                if key in decoded:
                    values = decoded[key]
                    break
        elif not isinstance(decoded, (list, tuple)):
            joint_order = getattr(
                decoded,
                "joint_order",
                getattr(decoded, "jointOrder", None),
            )
            for name in (
                "positions_rad",
                "joint_positions_rad",
                "g1_joint_positions_rad",
                "q",
            ):
                if hasattr(decoded, name):
                    values = getattr(decoded, name)
                    break
        if hasattr(values, "tolist"):
            values = values.tolist()
        if joint_order is not None and tuple(joint_order) != expected_order:
            raise RuntimeError(
                "G1 shadow decoder returned an incompatible joint order"
            )
        if (
            not isinstance(values, (list, tuple))
            or len(values) != G1_POSE_DIMENSION
        ):
            raise RuntimeError(
                "G1 shadow decoder must return exactly 29 canonical body positions"
            )
        result = [float(value) for value in values]
        if not all(math.isfinite(value) for value in result):
            raise RuntimeError("G1 shadow decoder returned non-finite positions")
        return result

    @staticmethod
    def _invoke_shadow(
        decoder: Any,
        token: list[float],
        *,
        session_id: str,
        token_sequence: int,
    ) -> Any:
        callback = getattr(decoder, "decode_token", None)
        if not callable(callback):
            callback = getattr(decoder, "decode", None)
        if not callable(callback):
            raise RuntimeError("G1 shadow decoder has no decode_token method")
        parameters = inspect.signature(callback).parameters
        kwargs: dict[str, Any] = {}
        if "session_id" in parameters:
            kwargs["session_id"] = session_id
        if "sequence" in parameters:
            kwargs["sequence"] = token_sequence
        elif "source_sequence" in parameters:
            kwargs["source_sequence"] = token_sequence
        elif "token_sequence" in parameters:
            kwargs["token_sequence"] = token_sequence
        return callback(token, **kwargs)

    def _decode_token(
        self,
        source: dict[str, Any],
        *,
        motion_token: Any,
        token_sequence: Any,
        session_id: str,
        expected_order: tuple[str, ...],
    ) -> tuple[list[float], dict[str, Any], int]:
        decoder = self._load_shadow_decoder()
        status = self._shadow_status(decoder, self._shadow_error)
        if decoder is None or not status["available"]:
            raise RuntimeError(
                "64D NVIDIA token input is blocked: the pinned G1 shadow "
                "decoder is not available"
            )
        producer = self._bounded_string(
            source["producer"],
            label="source.producer",
        )
        checkpoint = self._bounded_string(
            source["checkpoint"],
            label="source.checkpoint",
        )
        release_fixture = (
            source["kind"] == "nvidia-sonic-release-token-fixture"
        )
        expected_producer = (
            "nvidia-gear-sonic-release"
            if release_fixture
            else "isaac-gr00t-policy-server"
        )
        if producer != expected_producer:
            raise ValueError(
                f"source.producer must be {expected_producer} for "
                f"{source['kind']}"
            )
        if (
            release_fixture
            and checkpoint != NVIDIA_RELEASE_DECODER_CHECKPOINT
        ):
            raise ValueError(
                "the release token fixture requires the pinned released "
                "decoder checkpoint digest"
            )
        if release_fixture:
            model = status.get("details", {}).get("model", {})
            expected_digest = NVIDIA_RELEASE_DECODER_CHECKPOINT.split(
                ":",
                1,
            )[1]
            if (
                not isinstance(model, dict)
                or model.get("verified") is not True
                or model.get("sha256") != expected_digest
            ):
                raise RuntimeError(
                    "release fixture requires the locally verified pinned "
                    "NVIDIA decoder"
                )
        token_sequence = self._non_negative_integer(
            token_sequence,
            label="source.sequenceStart/token frame",
        )
        token = self._finite_vector(
            motion_token,
            length=TOKEN_DIMENSION,
            label="source.motionToken",
        )
        if release_fixture and any(
            not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-8)
            for actual, expected in zip(
                token,
                NVIDIA_RELEASE_INITIAL_TOKEN,
            )
        ):
            raise ValueError(
                "release token fixture differs from pinned "
                "LATENT_INITIAL_MOTION_TOKEN"
            )
        previous = self._last_token_sequences.get(session_id)
        if previous is not None and token_sequence != previous + 1:
            raise ValueError(
                "token sequence must be contiguous within a token session; "
                f"expected {previous + 1}, got {token_sequence}"
            )
        if self._active_token_session != session_id:
            if session_id in self._last_token_sequences:
                raise RuntimeError(
                    "a reset shadow stream cannot resume an earlier session; "
                    "start a new sessionId"
                )
            if len(self._last_token_sequences) >= MAX_SHADOW_TOKEN_SESSIONS:
                raise RuntimeError(
                    "shadow token-session capacity is exhausted; restart the "
                    "loopback dashboard before opening another stream"
                )
            if self._active_token_session is not None:
                reset = getattr(decoder, "reset", None)
                if not callable(reset):
                    raise RuntimeError(
                        "G1 shadow decoder cannot switch sessions without reset"
                    )
                parameters = inspect.signature(reset).parameters
                reset(**({"session_id": session_id} if "session_id" in parameters else {}))
            self._active_token_session = session_id
        decoded = self._invoke_shadow(
            decoder,
            token,
            session_id=session_id,
            token_sequence=token_sequence,
        )
        positions = self._extract_decoded_pose(decoded, expected_order)
        self._last_token_sequences[session_id] = token_sequence
        provenance = {
            "inputClass": (
                "nvidia-sonic-release-token-fixture"
                if release_fixture
                else "nvidia-sonic-motion-token"
            ),
            "producer": producer,
            "checkpointClaim": checkpoint,
            "nvidiaVlaDerivedClaim": not release_fixture,
            "claimAuthenticatedByThisServer": release_fixture,
            "g1ShadowDecodeUsed": True,
            "shadowDecoder": status,
            "syntheticCatalogToken": False,
            "checkpointSpecificReleaseFixture": release_fixture,
        }
        return positions, provenance, token_sequence

    @staticmethod
    def _retarget_diagnostics(result: Any) -> dict[str, Any]:
        base_pose = getattr(result, "pose", result)
        return {
            "actionCount": len(result.joint_positions_rad),
            "saturationCount": len(base_pose.saturations),
            "maximumReducedClosureResidualM": (
                base_pose.closure.maximum_residual_m
            ),
            "allInValidatedReducedDomain": (
                base_pose.closure.all_in_validated_domain
            ),
            "refinementIterationsRequested": (
                result.diagnostics.iterations_requested
            ),
            "refinementIterationsAccepted": (
                result.diagnostics.iterations_accepted
            ),
            "seedTaskError": result.diagnostics.seed_task_error,
            "finalTaskError": result.diagnostics.final_task_error,
            "maximumUsdClosureResidualM": (
                result.diagnostics.maximum_closure_residual_m
            ),
            "worstUsdClosureConstraint": (
                result.diagnostics.worst_closure_constraint
            ),
            "bodyTargetCount": len(result.diagnostics.body_targets),
        }

    @classmethod
    def _frame_payload(
        cls,
        result: Any,
        positions: list[float],
        *,
        session_id: str,
        sequence: int,
        source_token_sequence: int | None,
        source_pose_schema: str,
        expected_order: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "sourceTokenSequence": source_token_sequence,
            "sourcePose": {
                "schema": source_pose_schema,
                "jointOrder": list(expected_order),
                "positionsRad": list(map(float, positions)),
            },
            "retarget": result.as_payload(),
            "wbcReference": result.wbc_reference_payload(
                session_id=session_id,
                sequence=sequence,
                source_token_sequence=source_token_sequence,
            ),
            "diagnostics": cls._retarget_diagnostics(result),
        }

    def retarget(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate one request and return exact Dropbear motor targets."""

        with self._lock:
            return self._retarget_locked(payload)

    def _retarget_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a request while token-decoder session state is locked."""

        if self._retargeter is None:
            raise RuntimeError(
                "G1-to-Dropbear retargeter is unavailable"
                + (f": {self._retarget_error}" if self._retarget_error else "")
            )
        self._exact_keys(
            payload,
            allowed=frozenset(
                {
                    "schema",
                    "sessionId",
                    "sequence",
                    "source",
                    "refinementIterations",
                }
            ),
            required=frozenset({"schema", "sessionId", "sequence", "source"}),
            label="request",
        )
        if payload["schema"] != RETARGET_REQUEST_SCHEMA:
            raise ValueError(
                f"schema must be {RETARGET_REQUEST_SCHEMA}"
            )
        session_id = self._bounded_string(
            payload["sessionId"],
            label="sessionId",
            maximum=64,
        )
        if not self._session_pattern.fullmatch(session_id):
            raise ValueError("sessionId contains unsupported characters")
        sequence = self._non_negative_integer(
            payload["sequence"],
            label="sequence",
        )
        refinement_iterations = payload.get("refinementIterations")
        if refinement_iterations is not None and (
            isinstance(refinement_iterations, bool)
            or not isinstance(refinement_iterations, int)
            or not 0 <= refinement_iterations <= 2
        ):
            raise ValueError("refinementIterations must be an integer in 0..2")
        source = payload["source"]
        if not isinstance(source, dict):
            raise ValueError("source must be an object")

        from integrations.gr00t_wbc.retarget import (
            G1_BODY_JOINT_NAMES,
            SOURCE_POSE_SCHEMA,
        )

        expected_order = tuple(G1_BODY_JOINT_NAMES)
        kind = source.get("kind")
        source_token_sequence: int | None = None
        decoded_chunk: list[list[float]] | None = None
        token_sequences: list[int] | None = None
        if kind == "decoded-g1-pose":
            self._exact_keys(
                source,
                allowed=self._decoded_source_keys,
                required=frozenset(
                    {
                        "kind",
                        "schema",
                        "jointOrder",
                        "positionsRad",
                        "producer",
                        "nvidiaVlaDerived",
                    }
                ),
                label="source",
            )
            if source["schema"] != SOURCE_POSE_SCHEMA:
                raise ValueError(f"source.schema must be {SOURCE_POSE_SCHEMA}")
            if (
                not isinstance(source["jointOrder"], list)
                or tuple(source["jointOrder"]) != expected_order
            ):
                raise ValueError(
                    "source.jointOrder must exactly match the canonical "
                    "29-axis G1 order"
                )
            if not isinstance(source["nvidiaVlaDerived"], bool):
                raise ValueError("source.nvidiaVlaDerived must be boolean")
            producer = self._bounded_string(
                source["producer"],
                label="source.producer",
            )
            checkpoint = source.get("checkpoint")
            if source["nvidiaVlaDerived"]:
                checkpoint = self._bounded_string(
                    checkpoint,
                    label="source.checkpoint",
                )
            elif checkpoint is not None:
                raise ValueError(
                    "source.checkpoint is allowed only when "
                    "nvidiaVlaDerived is true"
                )
            positions = self._finite_vector(
                source["positionsRad"],
                length=G1_POSE_DIMENSION,
                label="source.positionsRad",
            )
            provenance = {
                "inputClass": "decoded-g1-pose",
                "producer": producer,
                "checkpointClaim": checkpoint,
                "nvidiaVlaDerivedClaim": source["nvidiaVlaDerived"],
                "claimAuthenticatedByThisServer": False,
                "g1ShadowDecodeUsed": False,
                "syntheticCatalogToken": False,
            }
        elif kind in {
            "nvidia-sonic-motion-token",
            "nvidia-sonic-release-token-fixture",
        }:
            self._exact_keys(
                source,
                allowed=self._token_source_keys,
                required=self._token_source_keys,
                label="source",
            )
            if source["schema"] != NVIDIA_TOKEN_INPUT_SCHEMA:
                raise ValueError(
                    f"source.schema must be {NVIDIA_TOKEN_INPUT_SCHEMA}"
                )
            positions, provenance, source_token_sequence = self._decode_token(
                source,
                motion_token=source["motionToken"],
                token_sequence=source["sequenceStart"],
                session_id=session_id,
                expected_order=expected_order,
            )
        elif kind == "nvidia-sonic-motion-token-chunk":
            self._exact_keys(
                source,
                allowed=self._token_chunk_source_keys,
                required=self._token_chunk_source_keys,
                label="source",
            )
            if source["schema"] != NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA:
                raise ValueError(
                    "source.schema must be "
                    f"{NVIDIA_TOKEN_CHUNK_INPUT_SCHEMA}"
                )
            raw_chunk = source["motionTokenChunk"]
            if (
                not isinstance(raw_chunk, list)
                or not 1 <= len(raw_chunk) <= 40
            ):
                raise ValueError(
                    "source.motionTokenChunk must contain 1..40 token frames"
                )
            # Validate the complete chunk before advancing the stateful
            # decoder so a malformed later frame cannot partially consume it.
            token_chunk = [
                self._finite_vector(
                    frame,
                    length=TOKEN_DIMENSION,
                    label=f"source.motionTokenChunk[{index}]",
                )
                for index, frame in enumerate(raw_chunk)
            ]
            sequence_start = self._non_negative_integer(
                source["sequenceStart"],
                label="source.sequenceStart",
            )
            decoded_chunk = []
            token_sequences = []
            provenance = {}
            for index, token in enumerate(token_chunk):
                token_sequence = sequence_start + index
                positions, frame_provenance, _ = self._decode_token(
                    source,
                    motion_token=token,
                    token_sequence=token_sequence,
                    session_id=session_id,
                    expected_order=expected_order,
                )
                decoded_chunk.append(positions)
                token_sequences.append(token_sequence)
                provenance = frame_provenance
            provenance = {
                **provenance,
                "inputClass": "nvidia-sonic-motion-token-chunk",
                "tokenFrameCount": len(decoded_chunk),
            }
        else:
            raise ValueError(
                "source.kind must be decoded-g1-pose, "
                "nvidia-sonic-motion-token, "
                "nvidia-sonic-motion-token-chunk, or "
                "nvidia-sonic-release-token-fixture"
            )

        if refinement_iterations is None:
            # q[29] and one-token previews get one bounded body-space update.
            # A full 40-frame horizon defaults to graph/closure evaluation
            # without 880 additional finite-difference solves; clients may
            # explicitly request 1..2 refinement iterations per frame.
            refinement_iterations = 0 if decoded_chunk is not None else 1
        if decoded_chunk is not None:
            assert token_sequences is not None
            results = self._retargeter.retarget_chunk(
                decoded_chunk,
                refinement_iterations=refinement_iterations,
                maximum_frames=40,
            )
            frames = [
                self._frame_payload(
                    result,
                    frame_positions,
                    session_id=session_id,
                    sequence=sequence + index,
                    source_token_sequence=token_sequences[index],
                    source_pose_schema=SOURCE_POSE_SCHEMA,
                    expected_order=expected_order,
                )
                for index, (result, frame_positions) in enumerate(
                    zip(results, decoded_chunk)
                )
            ]
            return {
                "schema": RETARGET_RESPONSE_SCHEMA,
                "sessionId": session_id,
                "sequenceStart": sequence,
                "frameCount": len(frames),
                "targetJointOrder": frames[0]["retarget"]["target"][
                    "jointOrder"
                ],
                "bridge": {
                    "status": "retargeted-chunk",
                    "sourceClass": provenance["inputClass"],
                    "stages": [
                        "1..40 × 64D NVIDIA-token claim",
                        "contiguous sequential G1 SONIC shadow decode",
                        "retained USD task-space/passive-loop solve",
                        "22 Dropbear USD motor targets per frame",
                    ],
                    "fullUsdTaskSpaceKinematicsApplied": True,
                    "fullUsdPassiveSolveApplied": True,
                    "contactDynamicsApplied": False,
                    "contactDynamicsAuthority": "Isaac/PhysX",
                },
                "provenance": provenance,
                "frames": frames,
                "hardwareAuthorized": False,
            }

        result = self._retargeter.retarget_g1_pose(
            positions,
            refinement_iterations=refinement_iterations,
        )
        frame = self._frame_payload(
            result,
            positions,
            session_id=session_id,
            sequence=sequence,
            source_token_sequence=source_token_sequence,
            source_pose_schema=SOURCE_POSE_SCHEMA,
            expected_order=expected_order,
        )
        token_stage = (
            "verified checkpoint-specific NVIDIA release token fixture"
            if provenance.get("checkpointSpecificReleaseFixture")
            else "64D NVIDIA VLA-token claim"
        )
        return {
            "schema": RETARGET_RESPONSE_SCHEMA,
            "sessionId": session_id,
            "sequence": sequence,
            "bridge": {
                "status": "retargeted",
                "sourceClass": provenance["inputClass"],
                "stages": (
                    [
                        token_stage,
                        "G1 SONIC shadow decode",
                        "semantic reduced-closure seed",
                        "retained USD task-space/passive-loop refinement",
                        "22 Dropbear USD motor targets",
                    ]
                    if provenance["g1ShadowDecodeUsed"]
                    else [
                        "canonical decoded G1 pose",
                        "semantic reduced-closure seed",
                        "retained USD task-space/passive-loop refinement",
                        "22 Dropbear USD motor targets",
                    ]
                ),
                "fullUsdTaskSpaceKinematicsApplied": True,
                "fullUsdPassiveSolveApplied": True,
                "contactDynamicsApplied": False,
                "contactDynamicsAuthority": "Isaac/PhysX",
            },
            "provenance": provenance,
            **frame,
            "hardwareAuthorized": False,
        }


class Gr00tRuntimeInspector:
    """Cache a structured readiness report for the dashboard."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.python = self.project_root / ".gr00t-venv" / "bin" / "python"
        self.cuda_visible_devices = os.environ.get(
            "DROPBEAR_CUDA_VISIBLE_DEVICES",
            os.environ.get("CUDA_VISIBLE_DEVICES"),
        )
        self._lock = threading.RLock()
        self._cached_at = 0.0
        self._cached: dict[str, Any] | None = None

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ModuleNotFoundError):
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def child_environment(self) -> dict[str, str]:
        """Return the identical CUDA visibility used by probe and trainer."""

        environment = dict(os.environ)
        if self.cuda_visible_devices is not None:
            environment["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        environment["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        return environment

    def _verified_smoke(self, probe: dict[str, Any]) -> dict[str, Any]:
        """Return the newest locally reproducible CUDA deployment evidence."""

        artifacts_root = self.project_root / "artifacts" / "rl"
        reports = sorted(
            [
                *(
                    artifacts_root / "sonic-smoke"
                ).glob("*/smoke-report.json"),
                *(
                    artifacts_root / "sonic"
                ).glob("*/deployment-report.json"),
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ) if artifacts_root.is_dir() else []
        if not reports:
            return {
                "verified": False,
                "reason": "run tools/verify_gr00t_cuda.sh",
                "reportUrl": None,
            }
        report_path = reports[0]
        try:
            report = _strict_json_loads(
                report_path.read_text(encoding="utf-8")
            )
            onnx = report["onnx"]
            validation = onnx["validation"]
            tensorrt = report["tensorrt"]
            runtime = report["runtime"]
            artifact_root = (
                self.project_root / "artifacts" / "rl"
            ).resolve()

            def checked_artifact(raw_path: Any, expected_hash: Any) -> Path:
                path = (self.project_root / str(raw_path)).resolve()
                if (
                    not path.is_relative_to(artifact_root)
                    or not path.is_file()
                    or self._sha256(path) != str(expected_hash)
                ):
                    raise ValueError(f"artifact verification failed: {path.name}")
                return path

            def checked_json(path: Path) -> dict[str, Any]:
                payload = _strict_json_loads(
                    path.read_text(encoding="utf-8")
                )
                if not isinstance(payload, dict):
                    raise ValueError(f"{path.name} must contain an object")
                return payload

            checkpoint_path = checked_artifact(
                onnx["checkpoint"],
                onnx["checkpoint_sha256"],
            )
            onnx_path = checked_artifact(
                onnx["onnx"],
                onnx["onnx_sha256"],
            )
            engine_path = checked_artifact(
                tensorrt["engine"],
                tensorrt["engine_sha256"],
            )
            sidecar = checked_json(
                onnx_path.with_suffix(onnx_path.suffix + ".json")
            )
            session = checked_json(
                checkpoint_path.parent / "session.json"
            )
            contract = onnx.get("contract", {})
            reference = session.get("reference", {})
            expected_action = probe.get("actionContract")
            expected_contract = {
                "observation_dim": 90,
                "motion_token_dim": 64,
                "action_dim": 22,
                "joint_order": (
                    expected_action.get("joint_order")
                    if isinstance(expected_action, dict)
                    else None
                ),
                "output": "normalized motor residual in [-1, 1]",
                "frequency_hz": 50.0,
                "action_semantics": expected_action,
                "motion_token_semantics": {
                    "source": (
                        reference.get("token_source")
                        if isinstance(reference, dict)
                        else None
                    ),
                    "prompt_router_compatible": False,
                },
            }
            device_names = {
                str(item.get("name"))
                for item in probe.get("devices", [])
                if isinstance(item, dict)
            }
            report_devices = set(
                report.get("device", {}).get("device_names", [])
            )
            verified = bool(
                report.get("schema")
                in {
                    "dropbear-sonic-cuda-smoke-v1",
                    "dropbear-sonic-residual-deployment-v1",
                }
                and report.get("status") == "passed"
                and isinstance(expected_action, dict)
                and contract == expected_contract
                and session.get("schema")
                == "dropbear-sonic-training-session-v1"
                and session.get("status") == "complete"
                and session.get("contract") == contract
                and session.get("artifacts", {}).get(
                    "checkpoint_sha256"
                )
                == onnx["checkpoint_sha256"]
                and sidecar == onnx
                and validation.get("validated") is True
                and "CUDAExecutionProvider"
                in validation.get("providers", [])
                and float(validation.get("max_abs_error", math.inf)) < 1e-4
                and runtime.get("torch", {}).get("validated") is True
                and runtime.get("onnxruntime", {}).get("validated") is True
                and tensorrt.get("status") == "passed"
                and str(tensorrt.get("version", "")).startswith("10.13")
                and float(tensorrt.get("max_abs_error", math.inf))
                <= float(tensorrt.get("tolerance", 0.0))
                and bool(device_names.intersection(report_devices))
            )
            return {
                "verified": verified,
                "reason": (
                    "CUDA train/export/runtime/TensorRT smoke passed"
                    if verified
                    else "smoke report is incompatible with this host"
                ),
                "sessionId": (
                    report.get("session_id") or report_path.parent.name
                ),
                "reportUrl": (
                    "/"
                    + str(report_path.relative_to(self.project_root))
                ),
                "enginePath": str(
                    engine_path.relative_to(self.project_root)
                ),
                "checkpointPath": str(onnx["checkpoint"]),
                "onnxPath": str(onnx["onnx"]),
                "device": report.get("device"),
                "training": report.get("training"),
                "onnx": validation,
                "tensorRt": tensorrt,
            }
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            return {
                "verified": False,
                "reason": str(error),
                "reportUrl": (
                    "/"
                    + str(report_path.relative_to(self.project_root))
                ),
            }

    def _python_probe(self) -> dict[str, Any]:
        if not self.python.is_file():
            return {
                "available": False,
                "error": "run tools/setup_gr00t_runtime.sh",
            }
        probe = """
import json
result = {}
try:
 import torch
 result["torchVersion"] = torch.__version__
 result["cudaAvailable"] = bool(torch.cuda.is_available())
 result["cudaRuntime"] = torch.version.cuda
 result["deviceCount"] = torch.cuda.device_count()
 result["devices"] = [
   {"index": i, "name": torch.cuda.get_device_name(i),
    "capability": list(torch.cuda.get_device_capability(i))}
   for i in range(torch.cuda.device_count())
 ]
except Exception as exc:
 result["torchError"] = repr(exc)
for name in ("onnx", "onnxruntime", "zmq", "tensorrt"):
 try:
  module = __import__(name)
  result[name] = getattr(module, "__version__", "available")
  if name == "onnxruntime":
   result["onnxProviders"] = module.get_available_providers()
 except Exception as exc:
  result[name + "Error"] = repr(exc)
try:
 from rl.sonic_action import action_contract
 result["actionContract"] = action_contract()
except Exception as exc:
 result["actionContractError"] = repr(exc)
print(json.dumps(result))
"""
        try:
            environment = self.child_environment()
            environment["PATH"] = (
                "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
            )
            result = subprocess.run(
                [str(self.python), "-c", probe],
                cwd=self.project_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
                env=environment,
            )
            if result.returncode:
                return {
                    "available": False,
                    "error": (result.stderr or result.stdout)[-1200:],
                }
            payload = _strict_json_loads(result.stdout)
            if not isinstance(payload, dict):
                raise ValueError("CUDA probe did not return an object")
            return {
                "available": True,
                "cudaVisibleDevices": self.cuda_visible_devices,
                **payload,
            }
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return {"available": False, "error": str(error)}

    def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if (
                not refresh
                and self._cached is not None
                and now - self._cached_at < 5.0
            ):
                return dict(self._cached)
            probe = self._python_probe()
            providers = probe.get("onnxProviders") or []
            tensor_rt = str(probe.get("tensorrt") or "")
            lock_path = (
                self.project_root
                / "integrations"
                / "gr00t_wbc"
                / "UPSTREAM_LOCK.json"
            )
            upstream: dict[str, Any] = {}
            try:
                upstream = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                upstream = {}
            cuda_ready = bool(probe.get("cudaAvailable"))
            onnx_ready = "CUDAExecutionProvider" in providers
            tensor_rt_ready = tensor_rt.startswith("10.13")
            smoke = self._verified_smoke(probe)
            isaac_installed = self._module_available("isaaclab") and (
                self._module_available("isaacsim")
                or self._module_available("omni.isaac.core")
            )
            assets = {
                "usd": (
                    self.project_root / "artifacts" / "usd" / "dropbear.usd"
                ).is_file(),
                "browserManifest": (
                    self.project_root
                    / "web"
                    / "assets"
                    / "robot"
                    / "dropbear-physics-manifest.json"
                ).is_file(),
                "embodiment": (
                    self.project_root
                    / "integrations"
                    / "gr00t_wbc"
                    / "config"
                    / "dropbear_embodiment.json"
                ).is_file(),
            }
            payload = {
                "schema": "dropbear-gr00t-runtime-v1",
                "checkedAtUnix": time.time(),
                "python": str(self.python.relative_to(self.project_root))
                if self.python.is_file()
                else None,
                "probe": probe,
                "upstream": upstream,
                "assets": assets,
                "gates": {
                    "cudaTraining": cuda_ready,
                    "cudaPolicy": cuda_ready and onnx_ready,
                    "onnxCuda": onnx_ready,
                    "tensorRtExact": tensor_rt_ready,
                    "cudaDeploymentVerified": bool(
                        smoke.get("verified")
                    ),
                    "isaacPhysxInstalled": isaac_installed,
                    # Import presence never establishes an authoritative
                    # Dropbear gravity/contact/closure validation result.
                    "authoritativeIsaacPhysx": False,
                    "hardwareDeployment": False,
                },
                "deploymentMode": (
                    "cuda-tensorrt-residual-engine-build-verified"
                    if (
                        cuda_ready
                        and tensor_rt_ready
                        and smoke.get("verified")
                    )
                    else "not-ready"
                ),
                "verification": smoke,
                "safety": {
                    "hardwareCommandsEnabled": False,
                    "reason": (
                        "software-in-the-loop only; HIL admission is absent"
                    ),
                },
            }
            self._cached = payload
            self._cached_at = now
            return dict(payload)


class Gr00tTrainingManager:
    """Launch one CUDA-only token-policy training session at a time."""

    def __init__(self, project_root: Path, inspector: Gr00tRuntimeInspector):
        self.project_root = project_root.resolve()
        self.inspector = inspector
        self.output_root = (
            self.project_root / "artifacts" / "rl" / "sonic"
        )
        self.lock = threading.RLock()
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=300)
        self.state: dict[str, Any] = self._idle_state()
        self.state_path = self.output_root / ".service-state.json"
        self._restore_state()

    @staticmethod
    def _idle_state() -> dict[str, Any]:
        return {
            "state": "idle",
            "sessionId": None,
            "startedAt": None,
            "finishedAt": None,
            "pid": None,
            "config": None,
            "progress": None,
            "manifestUrl": None,
            "checkpointPath": None,
            "deployment": None,
            "error": None,
        }

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        _require_finite_json(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = _strict_json_loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _deployment_report_passed(self, path: Path) -> bool:
        report = self._read_json(path)
        onnx = report.get("onnx", {})
        validation = onnx.get("validation", {}) if isinstance(onnx, dict) else {}
        tensorrt = report.get("tensorrt", {})
        if (
            report.get("schema")
            != "dropbear-sonic-residual-deployment-v1"
            or report.get("status") != "passed"
            or not isinstance(onnx, dict)
            or not isinstance(validation, dict)
            or validation.get("validated") is not True
            or "CUDAExecutionProvider"
            not in validation.get("providers", [])
            or not isinstance(tensorrt, dict)
            or tensorrt.get("status") != "passed"
            or not str(tensorrt.get("version", "")).startswith("10.13")
        ):
            return False
        try:
            maximum_error = float(tensorrt["max_abs_error"])
            tolerance = float(tensorrt["tolerance"])
            if (
                not math.isfinite(maximum_error)
                or not math.isfinite(tolerance)
                or tolerance <= 0.0
                or maximum_error > tolerance
            ):
                return False
            artifact_root = (
                self.project_root / "artifacts" / "rl"
            ).resolve()

            def verify_file(raw_path: Any, raw_hash: Any) -> Path:
                candidate = (
                    self.project_root / str(raw_path)
                ).resolve()
                if (
                    not candidate.is_relative_to(artifact_root)
                    or not candidate.is_file()
                    or self.inspector._sha256(candidate) != str(raw_hash)
                ):
                    raise ValueError
                return candidate

            checkpoint = verify_file(
                onnx["checkpoint"],
                onnx["checkpoint_sha256"],
            )
            onnx_path = verify_file(
                onnx["onnx"],
                onnx["onnx_sha256"],
            )
            verify_file(
                tensorrt["engine"],
                tensorrt["engine_sha256"],
            )
            session = self._read_json(
                checkpoint.parent / "session.json"
            )
            sidecar = self._read_json(
                onnx_path.with_suffix(onnx_path.suffix + ".json")
            )
            return bool(
                session.get("schema")
                == "dropbear-sonic-training-session-v1"
                and session.get("status") == "complete"
                and session.get("contract") == onnx.get("contract")
                and session.get("artifacts", {}).get(
                    "checkpoint_sha256"
                )
                == onnx["checkpoint_sha256"]
                and sidecar == onnx
            )
        except (KeyError, OSError, TypeError, ValueError):
            return False

    def _persist_state(self) -> None:
        record = {
            "schema": "dropbear-sonic-service-record-v1",
            "state": dict(self.state),
            "events": list(self.events),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json_atomic(self.state_path, record)
        session_id = self.state.get("sessionId")
        if session_id:
            self._write_json_atomic(
                self.output_root / str(session_id) / "service-state.json",
                record,
            )

    @staticmethod
    def _pid_matches(pid: int, session_id: str) -> bool:
        try:
            command = (
                Path(f"/proc/{pid}/cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", errors="replace")
            )
        except OSError:
            return False
        return "rl.sonic_train" in command and session_id in command

    @classmethod
    def _terminate_orphan(cls, pid: int, session_id: str) -> bool:
        if pid <= 1 or not cls._pid_matches(pid, session_id):
            return False
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not Path(f"/proc/{pid}").exists():
                return True
            time.sleep(0.05)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not Path(f"/proc/{pid}").exists():
                return True
            time.sleep(0.05)
        return not Path(f"/proc/{pid}").exists()

    def _restore_state(self) -> None:
        record = self._read_json(self.state_path)
        if not record and self.output_root.is_dir():
            candidates = sorted(
                self.output_root.glob("*/service-state.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                record = self._read_json(candidates[0])
        saved = record.get("state") if isinstance(record, dict) else None
        if not isinstance(saved, dict):
            return
        self.state = {**self._idle_state(), **saved}
        raw_events = record.get("events", [])
        if isinstance(raw_events, list):
            self.events.extend(
                item for item in raw_events if isinstance(item, dict)
            )
        state_name = self.state.get("state")
        session_id = str(self.state.get("sessionId") or "")
        if state_name in {"running", "stopping"}:
            raw_pid = self.state.get("pid")
            terminated = (
                self._terminate_orphan(raw_pid, session_id)
                if type(raw_pid) is int and session_id
                else False
            )
            self.state["state"] = "interrupted"
            self.state["pid"] = None
            self.state["finishedAt"] = datetime.now(timezone.utc).isoformat()
            self.state["error"] = (
                "dashboard restarted during a CUDA session; "
                + (
                    "the matching orphan process group was terminated"
                    if terminated
                    else "no matching child process remained"
                )
            )
            self.events.append(
                {
                    "event": "interrupted",
                    "message": self.state["error"],
                }
            )
            self._persist_state()
        elif state_name == "complete" and session_id:
            report = (
                self.output_root / session_id / "deployment-report.json"
            )
            if not self._deployment_report_passed(report):
                self.state["state"] = "error"
                self.state["error"] = (
                    "persisted session has no passed CUDA/TensorRT "
                    "deployment report"
                )
                self._persist_state()

    def _finalize_manifest(
        self,
        session_id: str,
        *,
        status: str,
        verification: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        path = self.output_root / session_id / "session.json"
        manifest = self._read_json(path)
        if not manifest:
            return
        manifest["status"] = status
        manifest["service_finished_at"] = datetime.now(timezone.utc).isoformat()
        if verification:
            manifest["deployment_verification"] = {
                "verified": bool(verification.get("verified")),
                "session_id": verification.get("sessionId"),
                "report_url": verification.get("reportUrl"),
            }
        if error:
            manifest["error"] = error
        self._write_json_atomic(path, manifest)

    @staticmethod
    def _integer(
        payload: dict[str, Any],
        key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        raw = payload.get(key, default)
        if type(raw) is not int:
            raise ValueError(f"{key} must be an integer")
        value = raw
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be in [{minimum}, {maximum}]")
        return value

    @staticmethod
    def _number(
        payload: dict[str, Any],
        key: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        raw = payload.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{key} must be a number")
        value = float(raw)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be in [{minimum}, {maximum}]")
        return value

    def _config(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self.inspector.snapshot(refresh=True)
        gates = runtime.get("gates", {})
        required_gates = ("cudaTraining", "onnxCuda", "tensorRtExact")
        missing_gates = [
            name for name in required_gates if not gates.get(name)
        ]
        if missing_gates:
            raise RuntimeError(
                "required CUDA deployment prerequisites are not ready: "
                + ", ".join(missing_gates)
                + "; inspect /api/gr00t/status"
            )
        device_ids = payload.get("devices", [0])
        if not isinstance(device_ids, list) or not device_ids:
            raise ValueError("devices must contain at least one CUDA index")
        devices: list[int] = []
        compatible = {
            int(item["index"])
            for item in runtime.get("probe", {}).get("devices", [])
            if int(item.get("capability", [0])[0]) >= 7
        }
        for raw in device_ids:
            if type(raw) is not int:
                raise ValueError("each devices entry must be an integer")
            value = raw
            if value not in compatible:
                raise ValueError(
                    "devices must select a detected CUDA GPU with "
                    "compute capability 7.0 or newer"
                )
            if value not in devices:
                devices.append(value)
        profile = payload.get("motionProfile", "gentle-forward")
        if not isinstance(profile, str):
            raise ValueError("motionProfile must be a string")
        if profile not in {"gentle-forward", "circle-walk", "custom"}:
            raise ValueError("motionProfile is not supported")
        precision = payload.get("precision", "bfloat16")
        if not isinstance(precision, str):
            raise ValueError("precision must be a string")
        if precision not in {"bfloat16", "float16", "float32"}:
            raise ValueError("precision is not supported")
        raw_reference = payload.get("referencePath")
        reference_path: Path | None = None
        if raw_reference not in (None, ""):
            if not isinstance(raw_reference, str):
                raise ValueError("referencePath must be a string")
            reference_path = (
                self.project_root / raw_reference
            ).resolve()
            allowed_roots = (
                (self.project_root / "web" / "assets" / "rl").resolve(),
                (self.project_root / "artifacts" / "rl").resolve(),
            )
            if (
                not reference_path.is_file()
                or reference_path.suffix != ".json"
                or not any(
                    reference_path.is_relative_to(root)
                    for root in allowed_roots
                )
            ):
                raise ValueError(
                    "referencePath must be a JSON motion under web/assets/rl "
                    "or artifacts/rl"
                )
        hidden_dim = self._integer(
            payload, "hiddenDim", 256, 128, 1024
        )
        if hidden_dim not in {128, 256, 512, 1024}:
            raise ValueError(
                "hiddenDim must be one of 128, 256, 512, or 1024"
            )
        vertical_constraint = payload.get("verticalConstraint", False)
        if type(vertical_constraint) is not bool:
            raise ValueError("verticalConstraint must be a boolean")
        return {
            "updates": self._integer(payload, "updates", 4, 1, 10_000),
            "rolloutSteps": self._integer(
                payload, "rolloutSteps", 64, 8, 2048
            ),
            "environments": self._integer(
                payload, "environments", 128, 1, 4096
            ),
            "ppoEpochs": self._integer(payload, "ppoEpochs", 2, 1, 20),
            "batchSize": self._integer(
                payload, "batchSize", 2048, 32, 131_072
            ),
            "hiddenDim": hidden_dim,
            "referenceFrames": self._integer(
                payload, "referenceFrames", 400, 2, 1_000_000
            ),
            "targetSpeed": self._number(
                payload, "targetSpeed", 0.26, -0.5, 1.2
            ),
            "targetTurnRate": self._number(
                payload, "targetTurnRate", 0.0, -1.2, 1.2
            ),
            "referenceTrackingWeight": self._number(
                payload, "referenceTrackingWeight", 1.0, 0.0, 20.0
            ),
            "learningRate": self._number(
                payload, "learningRate", 3e-4, 1e-7, 0.1
            ),
            "motionProfile": profile,
            "precision": precision,
            "devices": devices,
            "referencePath": (
                str(reference_path.relative_to(self.project_root))
                if reference_path is not None
                else None
            ),
            "verticalConstraint": vertical_constraint,
        }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config(payload)
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("a GR00T/SONIC session is already running")
            session_id = (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + uuid.uuid4().hex[:8]
            )
            session_dir = self.output_root / session_id
            session_dir.mkdir(parents=True, exist_ok=False)
            command = [
                str(self.inspector.python),
                "-m",
                "rl.sonic_train",
                "--output-dir",
                str(self.output_root),
                "--session-id",
                session_id,
                "--device",
                "cuda",
                "--devices",
                ",".join(str(value) for value in config["devices"]),
                "--amp" if config["precision"] != "float32" else "--no-amp",
                "--amp-dtype",
                config["precision"]
                if config["precision"] != "float32"
                else "bfloat16",
                "--updates",
                str(config["updates"]),
                "--rollout-steps",
                str(config["rolloutSteps"]),
                "--environments",
                str(config["environments"]),
                "--ppo-epochs",
                str(config["ppoEpochs"]),
                "--batch-size",
                str(config["batchSize"]),
                "--hidden-dim",
                str(config["hiddenDim"]),
                "--learning-rate",
                str(config["learningRate"]),
                "--reference-frames",
                str(config["referenceFrames"]),
                "--reference-tracking-weight",
                str(config["referenceTrackingWeight"]),
                "--target-speed",
                str(config["targetSpeed"]),
                "--target-turn-rate",
                str(config["targetTurnRate"]),
                "--motion-profile",
                config["motionProfile"],
                (
                    "--vertical-constraint"
                    if config["verticalConstraint"]
                    else "--no-vertical-constraint"
                ),
                "--jsonl",
                "--deploy",
                "--require-tensorrt",
            ]
            if config["referencePath"]:
                device_index = command.index("--device")
                command[device_index:device_index] = [
                    "--reference-path",
                    config["referencePath"],
                ]
            environment = self.inspector.child_environment()
            environment["PYTHONUNBUFFERED"] = "1"
            self.events.clear()
            self.process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=environment,
            )
            self.state = {
                **self._idle_state(),
                "state": "running",
                "sessionId": session_id,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "pid": self.process.pid,
                "config": config,
                "manifestUrl": (
                    f"/artifacts/rl/sonic/{session_id}/session.json"
                ),
                "checkpointPath": str(
                    (
                        session_dir / "sonic_policy.pt"
                    ).relative_to(self.project_root)
                ),
            }
            self._persist_state()
            self.reader = threading.Thread(
                target=self._read_output,
                args=(self.process, session_id),
                daemon=True,
            )
            self.reader.start()
            return self.snapshot()

    def _read_output(
        self,
        process: subprocess.Popen[str],
        session_id: str,
    ) -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = _strict_json_loads(line)
                if not isinstance(event, dict):
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                event = {"event": "log", "message": line[-1200:]}
            with self.lock:
                if self.state.get("sessionId") != session_id:
                    continue
                self.events.append(event)
                if event.get("event") == "progress":
                    self.state["progress"] = event
                if event.get("event") == "deployment":
                    self.state["deployment"] = event
                self._persist_state()
        return_code = process.wait()
        verification: dict[str, Any] = {}
        if return_code == 0:
            runtime = self.inspector.snapshot(refresh=True)
            candidate = runtime.get("verification", {})
            if isinstance(candidate, dict):
                verification = candidate
        deployment_verified = bool(
            verification.get("verified") is True
            and verification.get("sessionId") == session_id
        )
        with self.lock:
            if self.state.get("sessionId") != session_id:
                return
            if self.state["state"] == "stopping":
                self.state["state"] = "stopped"
            elif return_code == 0 and deployment_verified:
                self.state["state"] = "complete"
                self.state["deploymentVerification"] = verification
            else:
                self.state["state"] = "error"
                self.state["error"] = (
                    f"SONIC trainer exited with status {return_code}"
                    if return_code != 0
                    else (
                        "trainer exited without hash-verified ONNX CUDA and "
                        "TensorRT deployment evidence for this session"
                    )
                )
            self.state["finishedAt"] = datetime.now(timezone.utc).isoformat()
            self.state["pid"] = None
            final_status = self.state["state"]
            self._finalize_manifest(
                session_id,
                status=final_status,
                verification=verification or None,
                error=self.state.get("error"),
            )
            self._persist_state()
            if self.process is process:
                self.process = None

    def stop(self) -> dict[str, Any]:
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return self.snapshot()
            self.state["state"] = "stopping"
            self._persist_state()
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                with self.lock:
                    self.state["state"] = "error"
                    self.state["error"] = (
                        "CUDA trainer process group did not terminate"
                    )
                    self.state["finishedAt"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    self._persist_state()
        reader = self.reader
        if (
            reader is not None
            and reader is not threading.current_thread()
            and reader.is_alive()
        ):
            reader.join(timeout=2)
        with self.lock:
            if (
                self.state.get("state") == "stopping"
                and process.poll() is not None
            ):
                self.state["state"] = "stopped"
                self.state["finishedAt"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                self.state["pid"] = None
                self._persist_state()
        return self.snapshot()

    def shutdown(self) -> None:
        """Stop a trainer/deployer before the dashboard process exits."""

        self.stop()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            payload = dict(self.state)
            payload["schema"] = "dropbear-sonic-service-state-v1"
            payload["events"] = list(self.events)
            return payload

    def list_sessions(self) -> dict[str, Any]:
        sessions: list[dict[str, Any]] = []
        if self.output_root.is_dir():
            for directory in self.output_root.iterdir():
                manifest_path = directory / "session.json"
                if not directory.is_dir():
                    continue
                manifest = self._read_json(manifest_path)
                service_record = self._read_json(
                    directory / "service-state.json"
                )
                service_state = service_record.get("state", {})
                if not isinstance(service_state, dict):
                    service_state = {}
                deployment_path = directory / "deployment-report.json"
                if service_state.get("state"):
                    session_state = str(service_state["state"])
                elif (
                    manifest
                    and self._deployment_report_passed(deployment_path)
                ):
                    session_state = "complete"
                elif manifest:
                    session_state = "deployment-missing"
                else:
                    session_state = "interrupted"
                sessions.append(
                    {
                        "sessionId": directory.name,
                        "state": session_state,
                        "createdAt": (
                            service_state.get("startedAt")
                            or manifest.get("created_at")
                        ),
                        "finishedAt": service_state.get("finishedAt"),
                        "device": manifest.get("device"),
                        "metrics": manifest.get("metrics"),
                        "config": (
                            service_state.get("config")
                            or manifest.get("config")
                        ),
                        "reference": manifest.get("reference"),
                        "error": service_state.get("error"),
                        "deployment": (
                            f"/artifacts/rl/sonic/{directory.name}/"
                            "deployment-report.json"
                            if deployment_path.is_file()
                            else None
                        ),
                        "manifestUrl": (
                            f"/artifacts/rl/sonic/{directory.name}/session.json"
                            if manifest_path.is_file()
                            else None
                        ),
                    }
                )
        sessions.sort(
            key=lambda item: str(item.get("createdAt") or item["sessionId"]),
            reverse=True,
        )
        return {
            "schema": "dropbear-sonic-session-index-v1",
            "count": len(sessions),
            "sessions": sessions,
        }
