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
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from typing import Any
import uuid


TOKEN_DIMENSION = 64
MAX_PROMPT_LENGTH = 256


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
