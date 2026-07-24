"""Safe CUDA-first deployment runtime for Dropbear SONIC policy artifacts.

``auto`` backend selection uses ONNX Runtime only when its CUDA execution
provider is present.  Otherwise it deliberately falls back to the Torch CUDA
checkpoint instead of silently running production inference on the CPU.

The model output is a normalized 22-motor residual.  Every frame passes through
finite-value checks, absolute clamps, a per-frame slew limit, monotonically
increasing sequence checks, and a stale-frame watchdog.  This is a software
safety boundary, not a replacement for ROS 2/firmware hard limits and E-stop.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Dict, Mapping, Sequence

import numpy as np
import torch

from .sonic_core import (
    ACTION_DIM,
    MOTION_TOKEN_DIM,
    OBSERVATION_DIM,
    SESSION_SCHEMA,
    DevicePlan,
    load_checkpoint,
    sha256_file,
    validate_checkpoint_payload,
)


ONNX_EXPORT_SCHEMA = "dropbear-sonic-onnx-export-v1"
DEPLOYMENT_REPORT_SCHEMA = "dropbear-sonic-residual-deployment-v1"


@dataclass(frozen=True)
class RuntimeResult:
    motor_residual: tuple[float, ...]
    accepted: bool
    reason: str
    sequence: int
    backend: str


class SafetyEnvelope:
    """Stateful output clamp and stale-input watchdog."""

    def __init__(
        self,
        *,
        lower: float | Sequence[float] = -1.0,
        upper: float | Sequence[float] = 1.0,
        maximum_delta: float | Sequence[float] = 0.12,
        stale_after_seconds: float = 0.10,
        maximum_future_skew_seconds: float = 0.02,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.lower = self._vector(lower, "lower")
        self.upper = self._vector(upper, "upper")
        self.maximum_delta = self._vector(maximum_delta, "maximum_delta")
        if not torch.all(self.lower < self.upper):
            raise ValueError("every lower limit must be below its upper limit")
        if not torch.all(self.maximum_delta > 0):
            raise ValueError("maximum_delta must be positive")
        self.stale_after_seconds = float(stale_after_seconds)
        if not 0.001 <= self.stale_after_seconds <= 10.0:
            raise ValueError("stale_after_seconds must be in [0.001, 10]")
        self.maximum_future_skew_seconds = float(maximum_future_skew_seconds)
        if (
            not math.isfinite(self.maximum_future_skew_seconds)
            or not 0.0 <= self.maximum_future_skew_seconds <= 0.1
        ):
            raise ValueError(
                "maximum_future_skew_seconds must be finite and in [0, 0.1]"
            )
        self.clock = clock
        self.last_action = torch.zeros(ACTION_DIM, dtype=torch.float32)
        self.last_sequence = -1
        self.last_accepted_at: float | None = None
        self.estopped = False

    @staticmethod
    def _vector(value: float | Sequence[float], name: str) -> torch.Tensor:
        tensor = torch.as_tensor(value, dtype=torch.float32).flatten()
        if tensor.numel() == 1:
            tensor = tensor.repeat(ACTION_DIM)
        if tensor.numel() != ACTION_DIM or not torch.isfinite(tensor).all():
            raise ValueError(f"{name} must be finite scalar or {ACTION_DIM}-vector")
        return tensor

    def emergency_stop(self) -> None:
        self.estopped = True
        self.last_action.zero_()

    def clear_emergency_stop(self) -> None:
        self.estopped = False

    def _failsafe(self) -> torch.Tensor:
        # Zero is the authored reference residual. Slew toward it so a stale
        # policy cannot keep introducing a learned offset.
        delta = (-self.last_action).clamp(-self.maximum_delta, self.maximum_delta)
        self.last_action = self.last_action + delta
        return self.last_action.clone()

    def guard(
        self,
        raw_action: torch.Tensor | np.ndarray | Sequence[float],
        *,
        sequence: int,
        timestamp: float,
        now: float | None = None,
    ) -> tuple[torch.Tensor, bool, str]:
        current_time = self.clock() if now is None else float(now)
        sequence = int(sequence)
        if self.estopped:
            self.last_action.zero_()
            return self.last_action.clone(), False, "emergency-stop"
        if not math.isfinite(current_time):
            return self._failsafe(), False, "non-finite-clock"
        try:
            frame_time = float(timestamp)
        except (TypeError, ValueError):
            return self._failsafe(), False, "non-finite-timestamp"
        if not math.isfinite(frame_time):
            return self._failsafe(), False, "non-finite-timestamp"
        if sequence <= self.last_sequence:
            return self._failsafe(), False, "non-monotonic-sequence"
        if frame_time - current_time > self.maximum_future_skew_seconds:
            return self._failsafe(), False, "future-input-frame"
        if current_time - frame_time > self.stale_after_seconds:
            return self._failsafe(), False, "stale-input-frame"
        action = torch.as_tensor(raw_action, dtype=torch.float32).flatten()
        if action.numel() != ACTION_DIM:
            return self._failsafe(), False, "action-shape"
        if not torch.isfinite(action).all():
            return self._failsafe(), False, "non-finite-action"
        clamped = torch.maximum(torch.minimum(action, self.upper), self.lower)
        delta = (clamped - self.last_action).clamp(
            -self.maximum_delta,
            self.maximum_delta,
        )
        self.last_action = self.last_action + delta
        self.last_sequence = sequence
        self.last_accepted_at = current_time
        reason = "accepted"
        if not torch.equal(clamped, action):
            reason = "accepted-absolute-clamp"
        elif not torch.equal(self.last_action, clamped):
            reason = "accepted-slew-clamp"
        return self.last_action.clone(), True, reason

    def watchdog(self, *, now: float | None = None) -> tuple[torch.Tensor, bool, str]:
        current_time = self.clock() if now is None else float(now)
        if self.estopped:
            self.last_action.zero_()
            return self.last_action.clone(), False, "emergency-stop"
        if not math.isfinite(current_time):
            return self._failsafe(), False, "non-finite-clock"
        if (
            self.last_accepted_at is None
            or current_time - self.last_accepted_at > self.stale_after_seconds
        ):
            return self._failsafe(), False, "watchdog-timeout"
        return self.last_action.clone(), True, "watchdog-healthy"


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} {path} must contain a JSON object")
    return payload


def _recorded_path_matches(
    recorded: Any,
    actual: Path,
    *,
    manifest: Path,
) -> bool:
    if not isinstance(recorded, str) or not recorded:
        return False
    candidate = Path(recorded)
    actual_resolved = actual.resolve()
    if candidate.name != actual.name:
        return False
    if candidate.is_absolute():
        return candidate.resolve() == actual_resolved
    # Preserve exact paths when the bundle has not moved, while allowing a
    # hash-bound directory bundle to be relocated as one unit.
    return (
        (Path.cwd() / candidate).resolve() == actual_resolved
        or (manifest.parent / candidate.name).resolve() == actual_resolved
    )


def _require_digest(path: Path, expected: Any, label: str) -> str:
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise ValueError(f"{label} has no valid sha256")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} sha256 mismatch")
    return actual


def _validate_export_record(
    export: Mapping[str, Any],
    *,
    manifest: Path,
    checkpoint: Path,
    onnx_path: Path,
    checkpoint_contract: Mapping[str, Any],
) -> Dict[str, str]:
    if export.get("schema") != ONNX_EXPORT_SCHEMA:
        raise ValueError("ONNX admission record has an unsupported schema")
    if not _recorded_path_matches(
        export.get("checkpoint"),
        checkpoint,
        manifest=manifest,
    ):
        raise ValueError("ONNX admission record checkpoint path mismatch")
    if not _recorded_path_matches(
        export.get("onnx"),
        onnx_path,
        manifest=manifest,
    ):
        raise ValueError("ONNX admission record path mismatch")
    checkpoint_sha256 = _require_digest(
        checkpoint,
        export.get("checkpoint_sha256"),
        "ONNX admission checkpoint",
    )
    onnx_sha256 = _require_digest(
        onnx_path,
        export.get("onnx_sha256"),
        "ONNX admission artifact",
    )
    if export.get("contract") != dict(checkpoint_contract):
        raise ValueError("ONNX admission contract does not match checkpoint")
    validation = export.get("validation")
    if not isinstance(validation, Mapping) or validation.get("validated") is not True:
        raise ValueError("ONNX admission record is not numerically validated")
    return {
        "checkpoint_sha256": checkpoint_sha256,
        "onnx_sha256": onnx_sha256,
    }


def admit_runtime_artifacts(
    checkpoint: Path,
    onnx_path: Path | None,
) -> Dict[str, Any]:
    """Admit only artifacts bound to their recorded hashes and contracts."""

    checkpoint = Path(checkpoint)
    if not checkpoint.is_file():
        raise ValueError(f"checkpoint does not exist: {checkpoint}")
    try:
        checkpoint_payload = torch.load(
            checkpoint,
            map_location="cpu",
            weights_only=False,
        )
    except (OSError, RuntimeError) as error:
        raise ValueError(f"cannot load checkpoint {checkpoint}: {error}") from error
    if not isinstance(checkpoint_payload, Mapping):
        raise ValueError("checkpoint must contain a mapping")
    checkpoint_contract = validate_checkpoint_payload(checkpoint_payload)
    checkpoint_hash = sha256_file(checkpoint)

    proofs: list[Dict[str, Any]] = []
    session_path = checkpoint.parent / "session.json"
    if session_path.is_file():
        session = _load_json_object(session_path, "training session")
        if session.get("schema") != SESSION_SCHEMA:
            raise ValueError("training session schema is unsupported")
        session_status = session.get("status")
        if session_status not in {"complete", "deployment_pending"}:
            raise ValueError(
                "training session is not complete or awaiting deployment"
            )
        artifacts = session.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError("training session artifacts are missing")
        if not _recorded_path_matches(
            artifacts.get("checkpoint"),
            checkpoint,
            manifest=session_path,
        ):
            raise ValueError("training session checkpoint path mismatch")
        _require_digest(
            checkpoint,
            artifacts.get("checkpoint_sha256"),
            "training session checkpoint",
        )
        if session.get("contract") != checkpoint_contract:
            raise ValueError("training session contract does not match checkpoint")
        if session.get("reference") != checkpoint_payload.get("reference"):
            raise ValueError("training session reference does not match checkpoint")
        if session_status == "complete":
            proofs.append(
                {
                    "kind": "training-session",
                    "manifest": str(session_path),
                }
            )

    onnx = Path(onnx_path) if onnx_path is not None else None
    if onnx is not None and not onnx.is_file():
        raise ValueError(f"ONNX artifact does not exist: {onnx}")
    if onnx is not None:
        sidecar_path = onnx.with_suffix(onnx.suffix + ".json")
        deployment_path = onnx.parent / "deployment-report.json"
        if sidecar_path.is_file():
            export = _load_json_object(sidecar_path, "ONNX sidecar")
            hashes = _validate_export_record(
                export,
                manifest=sidecar_path,
                checkpoint=checkpoint,
                onnx_path=onnx,
                checkpoint_contract=checkpoint_contract,
            )
            proofs.append(
                {
                    "kind": "onnx-sidecar",
                    "manifest": str(sidecar_path),
                    **hashes,
                }
            )
        elif deployment_path.is_file():
            deployment = _load_json_object(
                deployment_path,
                "deployment report",
            )
            if (
                deployment.get("schema") != DEPLOYMENT_REPORT_SCHEMA
                or deployment.get("status") != "passed"
            ):
                raise ValueError("deployment report is not passed")
            tensorrt = deployment.get("tensorrt")
            if not isinstance(tensorrt, Mapping) or tensorrt.get("status") != "passed":
                raise ValueError(
                    "deployment report cannot admit artifacts without passed TensorRT"
                )
            engine = onnx.parent / "sonic_policy.engine"
            if not engine.is_file() or not _recorded_path_matches(
                tensorrt.get("engine"),
                engine,
                manifest=deployment_path,
            ):
                raise ValueError("deployment report TensorRT engine path mismatch")
            _require_digest(
                engine,
                tensorrt.get("engine_sha256"),
                "deployment report TensorRT engine",
            )
            maximum_error = tensorrt.get("max_abs_error")
            tolerance = tensorrt.get("tolerance")
            if (
                isinstance(maximum_error, bool)
                or not isinstance(maximum_error, (int, float))
                or isinstance(tolerance, bool)
                or not isinstance(tolerance, (int, float))
                or not math.isfinite(float(maximum_error))
                or not math.isfinite(float(tolerance))
                or float(tolerance) <= 0.0
                or float(maximum_error) > float(tolerance)
            ):
                raise ValueError(
                    "deployment report TensorRT numerical evidence is invalid"
                )
            export = deployment.get("onnx")
            if not isinstance(export, Mapping):
                raise ValueError("deployment report ONNX record is missing")
            hashes = _validate_export_record(
                export,
                manifest=deployment_path,
                checkpoint=checkpoint,
                onnx_path=onnx,
                checkpoint_contract=checkpoint_contract,
            )
            proofs.append(
                {
                    "kind": "deployment-report",
                    "manifest": str(deployment_path),
                    **hashes,
                }
            )
        else:
            raise ValueError(
                "ONNX artifact requires a hash-bound sidecar or deployment report"
            )

    if not proofs:
        raise ValueError(
            "checkpoint requires a hash-bound training session, ONNX sidecar, "
            "or deployment report"
        )
    return {
        "checkpoint_sha256": checkpoint_hash,
        "checkpoint_contract": checkpoint_contract,
        "proofs": proofs,
    }


class SonicRuntime:
    """Torch CUDA or ONNX Runtime CUDA policy with a shared safety envelope."""

    def __init__(
        self,
        checkpoint: Path,
        plan: DevicePlan,
        *,
        onnx_path: Path | None = None,
        backend: str = "auto",
        safety: SafetyEnvelope | None = None,
    ):
        self.plan = plan
        self.checkpoint = Path(checkpoint)
        self.onnx_path = Path(onnx_path) if onnx_path else None
        self.artifact_admission = admit_runtime_artifacts(
            self.checkpoint,
            self.onnx_path,
        )
        self.safety = safety or SafetyEnvelope()
        self.model = None
        self.session = None
        self.fallback_reason = ""
        selected = backend.lower()
        if selected not in {"auto", "torch", "onnx"}:
            raise ValueError("backend must be auto, torch or onnx")

        available_providers: list[str] = []
        ort = None
        if self.onnx_path is not None:
            try:
                import onnxruntime as imported_ort

                ort = imported_ort
                available_providers = list(ort.get_available_providers())
            except ImportError:
                self.fallback_reason = "onnxruntime is not installed"

        can_use_onnx = (
            ort is not None
            and self.onnx_path is not None
            and self.onnx_path.exists()
            and (
                "CUDAExecutionProvider" in available_providers
                or (
                    plan.torch_device.type == "cpu"
                    and "CPUExecutionProvider" in available_providers
                )
            )
        )
        if selected == "onnx" and not can_use_onnx:
            raise RuntimeError(
                "requested ONNX backend has no matching execution provider"
            )
        if (selected == "onnx") or (selected == "auto" and can_use_onnx):
            assert ort is not None and self.onnx_path is not None
            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"]
                if plan.torch_device.type == "cuda"
                else ["CPUExecutionProvider"]
            )
            self.session = ort.InferenceSession(
                str(self.onnx_path),
                providers=providers,
            )
            self.backend = "onnxruntime"
        else:
            if (
                selected == "auto"
                and self.onnx_path is not None
                and plan.torch_device.type == "cuda"
                and "CUDAExecutionProvider" not in available_providers
            ):
                self.fallback_reason = (
                    "ONNX Runtime CUDA provider unavailable; using Torch CUDA"
                )
            self.model, _ = load_checkpoint(self.checkpoint, plan)
            self.backend = "torch"

    def _raw_inference(
        self,
        observation: torch.Tensor | np.ndarray | Sequence[float],
        motion_token: torch.Tensor | np.ndarray | Sequence[float],
    ) -> torch.Tensor:
        obs = torch.as_tensor(observation, dtype=torch.float32).reshape(
            -1,
            OBSERVATION_DIM,
        )
        token = torch.as_tensor(motion_token, dtype=torch.float32).reshape(
            -1,
            MOTION_TOKEN_DIM,
        )
        if obs.shape[0] != 1 or token.shape[0] != 1:
            raise ValueError("deployment runtime accepts exactly one frame")
        if not torch.isfinite(obs).all() or not torch.isfinite(token).all():
            raise ValueError("observation and token must be finite")
        if self.backend == "onnxruntime":
            assert self.session is not None
            result = self.session.run(
                ["motor_residual"],
                {
                    "observation": obs.numpy(),
                    "motion_token": token.numpy(),
                },
            )[0]
            return torch.from_numpy(result[0]).float()
        assert self.model is not None
        obs = obs.to(self.plan.torch_device)
        token = token.to(self.plan.torch_device)
        with torch.inference_mode(), self.plan.autocast():
            mu, _, _ = self.model(obs, token)
            result = torch.tanh(mu.float())
        return result[0].cpu()

    def infer(
        self,
        observation: torch.Tensor | np.ndarray | Sequence[float],
        motion_token: torch.Tensor | np.ndarray | Sequence[float],
        *,
        sequence: int,
        timestamp: float | None = None,
        now: float | None = None,
    ) -> RuntimeResult:
        current_time = self.safety.clock() if now is None else float(now)
        timestamp = current_time if timestamp is None else timestamp
        try:
            raw = self._raw_inference(observation, motion_token)
        except (RuntimeError, ValueError):
            action, accepted, reason = self.safety.guard(
                torch.full((ACTION_DIM,), float("nan")),
                sequence=sequence,
                timestamp=timestamp,
                now=current_time,
            )
            return RuntimeResult(
                motor_residual=tuple(float(value) for value in action),
                accepted=accepted,
                reason=reason,
                sequence=int(sequence),
                backend=self.backend,
            )
        action, accepted, reason = self.safety.guard(
            raw,
            sequence=sequence,
            timestamp=timestamp,
            now=current_time,
        )
        return RuntimeResult(
            motor_residual=tuple(float(value) for value in action),
            accepted=accepted,
            reason=reason,
            sequence=int(sequence),
            backend=self.backend,
        )

    def watchdog(self, *, now: float | None = None) -> RuntimeResult:
        action, accepted, reason = self.safety.watchdog(now=now)
        return RuntimeResult(
            motor_residual=tuple(float(value) for value in action),
            accepted=accepted,
            reason=reason,
            sequence=self.safety.last_sequence,
            backend=self.backend,
        )


def verify_runtime(
    runtime: SonicRuntime,
    *,
    seed: int = 211,
) -> Dict[str, Any]:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    observation = torch.randn(OBSERVATION_DIM, generator=generator)
    token = torch.randn(MOTION_TOKEN_DIM, generator=generator)
    current_time = runtime.safety.clock()
    result = runtime.infer(
        observation,
        token,
        sequence=1,
        timestamp=current_time,
        now=current_time,
    )
    if not result.accepted:
        raise RuntimeError(f"fresh runtime frame was rejected: {result.reason}")
    values = np.asarray(result.motor_residual)
    if values.shape != (ACTION_DIM,) or not np.isfinite(values).all():
        raise RuntimeError("runtime produced invalid action")
    if np.max(np.abs(values)) > 1.0 + 1e-6:
        raise RuntimeError("runtime bypassed absolute action clamp")
    stale = runtime.infer(
        observation,
        token,
        sequence=2,
        timestamp=current_time,
        now=current_time + runtime.safety.stale_after_seconds + 0.01,
    )
    if stale.accepted or stale.reason != "stale-input-frame":
        raise RuntimeError("stale-frame watchdog validation failed")
    future = runtime.infer(
        observation,
        token,
        sequence=3,
        timestamp=(
            current_time
            + runtime.safety.maximum_future_skew_seconds
            + 0.01
        ),
        now=current_time,
    )
    if future.accepted or future.reason != "future-input-frame":
        raise RuntimeError("future-frame timestamp validation failed")
    nonfinite = runtime.infer(
        observation,
        token,
        sequence=4,
        timestamp=float("nan"),
        now=current_time,
    )
    if nonfinite.accepted or nonfinite.reason != "non-finite-timestamp":
        raise RuntimeError("non-finite timestamp validation failed")
    return {
        "backend": runtime.backend,
        "fallback_reason": runtime.fallback_reason,
        "artifact_admission": runtime.artifact_admission,
        "fresh_frame": asdict(result),
        "stale_frame": asdict(stale),
        "future_frame": asdict(future),
        "nonfinite_timestamp_frame": asdict(nonfinite),
        "validated": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the safe Dropbear SONIC deployment runtime",
    )
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--onnx")
    parser.add_argument("--backend", choices=("auto", "torch", "onnx"), default="auto")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--devices", default="")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument(
        "--amp",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--amp-dtype",
        choices=("bfloat16", "float16"),
        default="bfloat16",
    )
    parser.add_argument("--stale-after", type=float, default=0.10)
    parser.add_argument("--maximum-delta", type=float, default=0.12)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        plan = DevicePlan.resolve(
            args.device,
            devices=args.devices,
            allow_cpu=args.allow_cpu,
            amp=args.amp,
            amp_dtype=args.amp_dtype,
        )
        runtime = SonicRuntime(
            Path(args.checkpoint),
            plan,
            onnx_path=Path(args.onnx) if args.onnx else None,
            backend=args.backend,
            safety=SafetyEnvelope(
                stale_after_seconds=args.stale_after,
                maximum_delta=args.maximum_delta,
            ),
        )
        result = verify_runtime(runtime)
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
