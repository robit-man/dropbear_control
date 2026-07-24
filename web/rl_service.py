"""Loopback-only process manager for local Dropbear PPO experiments."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import importlib.util
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid
from typing import Any


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
    payload = json.loads(raw, parse_constant=_reject_json_constant)
    _require_finite_json(payload)
    return payload


class RLTrainingManager:
    """Run at most one bounded training job and retain its progress stream."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.experiment_root = self.project_root / "artifacts" / "rl" / "experiments"
        self.lock = threading.RLock()
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.state: dict[str, Any] = self._idle_state()
        self.events: deque[dict[str, Any]] = deque(maxlen=240)
        self._restore_latest_completed()

    @staticmethod
    def _idle_state() -> dict[str, Any]:
        return {
            "state": "idle",
            "experimentId": None,
            "startedAt": None,
            "finishedAt": None,
            "pid": None,
            "config": None,
            "progress": None,
            "previewUpdate": None,
            "previewEvaluation": None,
            "evaluation": None,
            "policyUrl": None,
            "livePolicyUrl": None,
            "metricsUrl": None,
            "error": None,
        }

    @staticmethod
    def _bounded_int(
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
    def _bounded_float(
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
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise ValueError(f"{key} must be in [{minimum}, {maximum}]")
        return value

    def _validated_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = payload.get("device", "auto")
        if not isinstance(device, str):
            raise ValueError("device must be a string")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        physics_backend = payload.get(
            "physicsBackend", "teaching-plant-v2"
        )
        if not isinstance(physics_backend, str):
            raise ValueError("physicsBackend must be a string")
        if physics_backend not in {
            "teaching-plant-v2",
            "mujoco-usd-proxy-v1",
        }:
            raise ValueError(
                "physicsBackend is not available on this local runtime"
            )
        if (
            physics_backend == "mujoco-usd-proxy-v1"
            and importlib.util.find_spec("mujoco") is None
        ):
            raise ValueError("MuJoCo physics backend is not installed")
        if physics_backend == "mujoco-usd-proxy-v1" and device == "cuda":
            raise ValueError("MuJoCo physics backend requires the CPU device")
        motion_profile = payload.get("motionProfile", "gentle-forward")
        if not isinstance(motion_profile, str):
            raise ValueError("motionProfile must be a string")
        if motion_profile not in {"gentle-forward", "circle-walk", "custom"}:
            raise ValueError("motionProfile is not supported")
        init_checkpoint = None
        raw_checkpoint = payload.get("initCheckpoint")
        if raw_checkpoint not in (None, ""):
            if not isinstance(raw_checkpoint, str):
                raise ValueError("initCheckpoint must be a string")
            candidate = (self.project_root / raw_checkpoint).resolve()
            experiment_root = self.experiment_root.resolve()
            if (
                not candidate.is_relative_to(experiment_root)
                or candidate.suffix != ".pt"
                or not candidate.is_file()
            ):
                raise ValueError(
                    "initCheckpoint must be an existing .pt file under "
                    "artifacts/rl/experiments"
                )
            init_checkpoint = str(candidate.relative_to(self.project_root))
        reward_payload = payload.get("rewardWeights", {})
        if not isinstance(reward_payload, dict):
            raise ValueError("rewardWeights must be an object")
        reward_weights = {
            "torso": self._bounded_float(
                reward_payload, "torso", 1.75, 0.0, 20.0
            ),
            "com": self._bounded_float(
                reward_payload, "com", 1.20, 0.0, 20.0
            ),
            "gaitContact": self._bounded_float(
                reward_payload, "gaitContact", 0.90, 0.0, 20.0
            ),
            "gaitSymmetry": self._bounded_float(
                reward_payload, "gaitSymmetry", 1.10, 0.0, 20.0
            ),
            "speed": self._bounded_float(
                reward_payload, "speed", 0.55, 0.0, 20.0
            ),
            "legSwing": self._bounded_float(
                reward_payload, "legSwing", 0.28, 0.0, 20.0
            ),
            "height": self._bounded_float(
                reward_payload, "height", 8.0, 0.0, 100.0
            ),
            "lateralTilt": self._bounded_float(
                reward_payload, "lateralTilt", 5.0, 0.0, 100.0
            ),
            "dorsalTilt": self._bounded_float(
                reward_payload, "dorsalTilt", 4.5, 0.0, 100.0
            ),
            "kneeContraction": self._bounded_float(
                reward_payload, "kneeContraction", 0.18, 0.0, 20.0
            ),
            "armSwing": self._bounded_float(
                reward_payload, "armSwing", 0.35, 0.0, 20.0
            ),
            "energy": self._bounded_float(
                reward_payload, "energy", 0.018, 0.0, 20.0
            ),
            "smoothness": self._bounded_float(
                reward_payload, "smoothness", 0.065, 0.0, 20.0
            ),
            "closure": self._bounded_float(
                reward_payload, "closure", 300.0, 0.0, 5000.0
            ),
            "fall": self._bounded_float(
                reward_payload, "fall", 7.0, 0.0, 100.0
            ),
        }
        vertical_constraint = payload.get("verticalConstraint", False)
        arm_swing = payload.get("armSwing", True)
        if type(vertical_constraint) is not bool:
            raise ValueError("verticalConstraint must be a boolean")
        if type(arm_swing) is not bool:
            raise ValueError("armSwing must be a boolean")
        return {
            "updates": self._bounded_int(payload, "updates", 12, 1, 10_000),
            "steps": self._bounded_int(payload, "steps", 128, 16, 2048),
            "envs": self._bounded_int(
                payload,
                "envs",
                8 if physics_backend == "mujoco-usd-proxy-v1" else 32,
                1,
                32 if physics_backend == "mujoco-usd-proxy-v1" else 512,
            ),
            "epochs": self._bounded_int(payload, "epochs", 4, 1, 20),
            "batchSize": self._bounded_int(payload, "batchSize", 1024, 32, 32768),
            "seed": self._bounded_int(payload, "seed", 7, 0, 2_147_483_647),
            "targetSpeed": self._bounded_float(
                payload,
                "targetSpeed",
                0.26,
                0.0,
                1.2,
            ),
            "targetTurnRate": self._bounded_float(
                payload,
                "targetTurnRate",
                0.0,
                -1.2,
                1.2,
            ),
            "episodeSeconds": self._bounded_float(
                payload,
                "episodeSeconds",
                8.0,
                1.0,
                30.0,
            ),
            "verticalConstraint": vertical_constraint,
            "armSwing": arm_swing,
            "rewardWeights": reward_weights,
            "device": device,
            "initCheckpoint": init_checkpoint,
            "physicsBackend": physics_backend,
            "motionProfile": motion_profile,
        }

    @staticmethod
    def _read_json_file(path: Path) -> dict[str, Any]:
        try:
            payload = _strict_json_loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

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

    def _config_from_policy(
        self,
        policy_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize a persisted browser-policy config for another run."""

        return self._validated_config(
            {
                "updates": policy_config.get("updates", 12),
                "steps": policy_config.get("rolloutSteps", 128),
                "envs": policy_config.get("parallelEnvs", 32),
                "epochs": policy_config.get("ppoEpochs", 4),
                "batchSize": policy_config.get("batchSize", 1024),
                "seed": policy_config.get("seed", 7),
                "targetSpeed": policy_config.get("targetSpeed", 0.26),
                "targetTurnRate": policy_config.get("targetTurnRate", 0.0),
                "motionProfile": policy_config.get(
                    "motionProfile", "custom"
                ),
                "episodeSeconds": policy_config.get(
                    "episodeSeconds", 8.0
                ),
                "verticalConstraint": policy_config.get(
                    "verticalConstraint", False
                ),
                "armSwing": policy_config.get("armSwing", True),
                "rewardWeights": policy_config.get("rewardWeights", {}),
                "device": policy_config.get("device", "auto"),
                "physicsBackend": policy_config.get(
                    "physicsBackend", "teaching-plant-v2"
                ),
            }
        )

    def _persist_current_session(self) -> None:
        experiment_id = self.state.get("experimentId")
        if not experiment_id:
            return
        output_dir = self.experiment_root / str(experiment_id)
        if not output_dir.is_dir():
            return
        payload = {
            "schema": "dropbear-rl-session-v1",
            "experimentId": experiment_id,
            "state": self.state.get("state"),
            "startedAt": self.state.get("startedAt"),
            "finishedAt": self.state.get("finishedAt"),
            "config": self.state.get("config"),
            "progress": self.state.get("progress"),
            "previewUpdate": self.state.get("previewUpdate"),
            "previewEvaluation": self.state.get("previewEvaluation"),
            "evaluation": self.state.get("evaluation"),
            "error": self.state.get("error"),
            "groundTruth": {
                "usdRepository": "https://github.com/Hyperspawn/dropbear_rl",
                "usdCommit": "3c37aedce6d445205671d5714d05ae28b8c90e2c",
                "usdPath": "dropbear_model/Dropbear/usd/dropbear.usd",
                "rigidBodies": 93,
                "authoredMasses": 93,
                "collisionGroups": 93,
                "physicsJoints": 117,
                "closureConstraints": 27,
            },
        }
        self._write_json_atomic(output_dir / "session.json", payload)

    def _session_from_directory(self, output_dir: Path) -> dict[str, Any]:
        experiment_id = output_dir.name
        record = self._read_json_file(output_dir / "session.json")
        policy = self._read_json_file(output_dir / "policy.json")
        metrics = self._read_json_file(output_dir / "metrics.json")
        policy_config = policy.get("config")
        if not isinstance(policy_config, dict):
            policy_config = {}
        config = record.get("config")
        if not isinstance(config, dict):
            try:
                config = self._config_from_policy(policy_config)
            except (ValueError, TypeError):
                config = None

        policy_path = output_dir / "policy.json"
        live_policy_path = output_dir / "live-policy.json"
        checkpoint_path = output_dir / "checkpoint.pt"
        metrics_path = output_dir / "metrics.json"
        evaluation = record.get("evaluation")
        if not isinstance(evaluation, dict):
            evaluation = metrics.get("evaluation")
        if not isinstance(evaluation, dict):
            evaluation = policy.get("evaluation")
        if not isinstance(evaluation, dict):
            evaluation = None
        progress = record.get("progress")
        if not isinstance(progress, dict):
            training = metrics.get("training")
            progress = training if isinstance(training, dict) else None

        created_at = (
            record.get("startedAt")
            or policy.get("createdAt")
            or datetime.fromtimestamp(
                output_dir.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        )
        finished_at = record.get("finishedAt")
        if not finished_at and metrics_path.is_file():
            finished_at = datetime.fromtimestamp(
                metrics_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        state = str(record.get("state") or "")
        if metrics_path.is_file() and policy_path.is_file():
            state = "complete"
        elif state not in {"running", "stopping", "stopped", "error"}:
            state = "interrupted"

        if self.state.get("experimentId") == experiment_id:
            active = self.state
            state = str(active.get("state") or state)
            config = active.get("config") or config
            progress = active.get("progress") or progress
            evaluation = active.get("evaluation") or evaluation
            created_at = active.get("startedAt") or created_at
            finished_at = active.get("finishedAt") or finished_at

        return {
            "experimentId": experiment_id,
            "state": state,
            "createdAt": created_at,
            "finishedAt": finished_at,
            "config": config,
            "progress": progress,
            "evaluation": evaluation,
            "policyUrl": (
                f"/artifacts/rl/experiments/{experiment_id}/policy.json"
                if policy_path.is_file()
                else None
            ),
            "livePolicyUrl": (
                f"/artifacts/rl/experiments/{experiment_id}/live-policy.json"
                if live_policy_path.is_file()
                else None
            ),
            "metricsUrl": (
                f"/artifacts/rl/experiments/{experiment_id}/metrics.json"
                if metrics_path.is_file()
                else None
            ),
            "checkpointPath": (
                str(checkpoint_path.relative_to(self.project_root))
                if checkpoint_path.is_file()
                else None
            ),
            "checkpointAvailable": checkpoint_path.is_file(),
            "groundTruth": record.get("groundTruth")
            or policy.get("groundTruth"),
        }

    def list_sessions(self) -> dict[str, Any]:
        """Return every retained run without exposing arbitrary file paths."""

        with self.lock:
            if not self.experiment_root.is_dir():
                return {
                    "schema": "dropbear-rl-session-index-v1",
                    "selectedExperimentId": self.state.get("experimentId"),
                    "count": 0,
                    "sessions": [],
                }
            sessions = [
                self._session_from_directory(output_dir)
                for output_dir in self.experiment_root.iterdir()
                if output_dir.is_dir() and not output_dir.name.startswith(".")
            ]
            def session_time(item: dict[str, Any]) -> float:
                try:
                    return datetime.strptime(
                        item["experimentId"][:16],
                        "%Y%m%dT%H%M%SZ",
                    ).replace(tzinfo=timezone.utc).timestamp()
                except ValueError:
                    try:
                        return datetime.fromisoformat(
                            str(item.get("createdAt"))
                        ).timestamp()
                    except (TypeError, ValueError):
                        return 0.0

            sessions.sort(key=session_time, reverse=True)
            return {
                "schema": "dropbear-rl-session-index-v1",
                "selectedExperimentId": self.state.get("experimentId"),
                "count": len(sessions),
                "sessions": sessions,
            }

    def _restore_latest_completed(self) -> None:
        """Restore the newest finished experiment after a dashboard restart."""

        if not self.experiment_root.is_dir():
            return
        candidates = sorted(
            (
                path
                for path in self.experiment_root.iterdir()
                if path.is_dir()
                and (path / "policy.json").is_file()
                and (path / "metrics.json").is_file()
            ),
            key=lambda path: (path / "metrics.json").stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return
        output_dir = candidates[0]
        try:
            policy = _strict_json_loads(
                (output_dir / "policy.json").read_text(encoding="utf-8")
            )
            metrics = _strict_json_loads(
                (output_dir / "metrics.json").read_text(encoding="utf-8")
            )
            policy_config = policy.get("config", {})
            config = self._config_from_policy(policy_config)
            training = dict(metrics.get("training") or {})
            evaluation = dict(metrics.get("evaluation") or {})
            completed_updates = int(
                training.get("final_update", config["updates"])
            )
            progress = {
                **training,
                "event": "progress",
                "update": completed_updates,
                "updates": config["updates"],
                "reward": training.get(
                    "reward", evaluation.get("meanReward")
                ),
                "upright_percent": training.get(
                    "upright_percent", evaluation.get("uprightPercent")
                ),
                "fall_percent": training.get(
                    "fall_percent", evaluation.get("fallPercent")
                ),
                "speed": training.get(
                    "speed", evaluation.get("meanSpeed")
                ),
                "closure_max_m": training.get(
                    "closure_max_m", evaluation.get("closureMaxM")
                ),
                "torso_tilt_degrees": training.get(
                    "torso_tilt_degrees",
                    evaluation.get("torsoTiltMeanDegrees"),
                ),
                "com_variation_m": training.get(
                    "com_variation_m",
                    evaluation.get("comHeightRangeM"),
                ),
            }
            experiment_id = output_dir.name
            finished_at = datetime.fromtimestamp(
                (output_dir / "metrics.json").stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
            self.state = {
                **self._idle_state(),
                "state": "complete",
                "experimentId": experiment_id,
                "finishedAt": finished_at,
                "config": config,
                "progress": progress,
                "previewUpdate": training.get("selected_update"),
                "previewEvaluation": evaluation,
                "evaluation": evaluation,
                "policyUrl": (
                    f"/artifacts/rl/experiments/{experiment_id}/policy.json"
                ),
                "livePolicyUrl": (
                    f"/artifacts/rl/experiments/{experiment_id}/live-policy.json"
                ),
                "metricsUrl": (
                    f"/artifacts/rl/experiments/{experiment_id}/metrics.json"
                ),
            }
            self.events.append(
                {
                    "event": "restored",
                    "experimentId": experiment_id,
                    "message": "restored latest completed experiment",
                }
            )
            self._persist_current_session()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.state = self._idle_state()
            self.events.clear()

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._validated_config(payload)
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise RuntimeError("an RL experiment is already running")

            experiment_id = (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-"
                + uuid.uuid4().hex[:8]
            )
            output_dir = self.experiment_root / experiment_id
            output_dir.mkdir(parents=True, exist_ok=False)
            checkpoint = output_dir / "checkpoint.pt"
            policy = output_dir / "policy.json"
            live_policy = output_dir / "live-policy.json"
            metrics = output_dir / "metrics.json"
            command = [
                sys.executable,
                "-m",
                "rl.train_walk",
                "--updates",
                str(config["updates"]),
                "--steps",
                str(config["steps"]),
                "--envs",
                str(config["envs"]),
                "--epochs",
                str(config["epochs"]),
                "--batch-size",
                str(config["batchSize"]),
                "--seed",
                str(config["seed"]),
                "--target-speed",
                str(config["targetSpeed"]),
                "--target-turn-rate",
                str(config["targetTurnRate"]),
                "--motion-profile",
                config["motionProfile"],
                "--physics-backend",
                config["physicsBackend"],
                "--episode-seconds",
                str(config["episodeSeconds"]),
                "--reward-torso",
                str(config["rewardWeights"]["torso"]),
                "--reward-com",
                str(config["rewardWeights"]["com"]),
                "--reward-gait-contact",
                str(config["rewardWeights"]["gaitContact"]),
                "--reward-gait-symmetry",
                str(config["rewardWeights"]["gaitSymmetry"]),
                "--reward-speed",
                str(config["rewardWeights"]["speed"]),
                "--reward-leg-swing",
                str(config["rewardWeights"]["legSwing"]),
                "--penalty-height",
                str(config["rewardWeights"]["height"]),
                "--penalty-lateral-tilt",
                str(config["rewardWeights"]["lateralTilt"]),
                "--penalty-dorsal-tilt",
                str(config["rewardWeights"]["dorsalTilt"]),
                "--penalty-knee-contraction",
                str(config["rewardWeights"]["kneeContraction"]),
                "--penalty-arm-swing",
                str(config["rewardWeights"]["armSwing"]),
                "--penalty-energy",
                str(config["rewardWeights"]["energy"]),
                "--penalty-smoothness",
                str(config["rewardWeights"]["smoothness"]),
                "--penalty-closure",
                str(config["rewardWeights"]["closure"]),
                "--penalty-fall",
                str(config["rewardWeights"]["fall"]),
                "--device",
                config["device"],
                "--out",
                str(checkpoint),
                "--policy-out",
                str(policy),
                "--live-policy-out",
                str(live_policy),
                "--metrics-out",
                str(metrics),
                "--jsonl",
                "--vertical-constraint"
                if config["verticalConstraint"]
                else "--no-vertical-constraint",
                "--arm-swing" if config["armSwing"] else "--no-arm-swing",
            ]
            if config["initCheckpoint"]:
                command.extend(
                    ["--init-checkpoint", config["initCheckpoint"]]
                )
            self.events.clear()
            self.process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            self.state = {
                **self._idle_state(),
                "state": "running",
                "experimentId": experiment_id,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "pid": self.process.pid,
                "config": config,
                "policyUrl": f"/artifacts/rl/experiments/{experiment_id}/policy.json",
                "livePolicyUrl": f"/artifacts/rl/experiments/{experiment_id}/live-policy.json",
                "metricsUrl": f"/artifacts/rl/experiments/{experiment_id}/metrics.json",
            }
            self._persist_current_session()
            self.reader = threading.Thread(
                target=self._read_output,
                args=(self.process, experiment_id),
                daemon=True,
            )
            self.reader.start()
            return self.snapshot()

    def _read_output(
        self,
        process: subprocess.Popen[str],
        experiment_id: str,
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
            except (json.JSONDecodeError, ValueError):
                event = {"event": "log", "message": line[-1200:]}
            with self.lock:
                if self.state.get("experimentId") != experiment_id:
                    continue
                self.events.append(event)
                if event.get("event") == "progress":
                    self.state["progress"] = event
                    self._persist_current_session()
                elif event.get("event") == "preview":
                    self.state["previewUpdate"] = event.get("update")
                    self.state["previewEvaluation"] = event.get("evaluation")
                    self._persist_current_session()
                elif event.get("event") == "complete":
                    self.state["evaluation"] = event.get("evaluation")
                    self._persist_current_session()

        return_code = process.wait()
        with self.lock:
            if self.state.get("experimentId") != experiment_id:
                return
            if self.state["state"] == "stopping":
                self.state["state"] = "stopped"
            elif return_code == 0:
                self.state["state"] = "complete"
            else:
                self.state["state"] = "error"
                self.state["error"] = f"trainer exited with status {return_code}"
            self.state["finishedAt"] = datetime.now(timezone.utc).isoformat()
            self.state["pid"] = None
            self._persist_current_session()
            if self.process is process:
                self.process = None

    def stop(self) -> dict[str, Any]:
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return self.snapshot()
            self.state["state"] = "stopping"
            self._persist_current_session()
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
                        "RL trainer process group did not terminate"
                    )
                    self.state["finishedAt"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    self._persist_current_session()
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
                self._persist_current_session()
        return self.snapshot()

    def shutdown(self) -> None:
        """Stop and reap a trainer before the dashboard exits."""

        self.stop()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            state = dict(self.state)
            state["events"] = list(self.events)
            return state
