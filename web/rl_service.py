"""Loopback-only process manager for local Dropbear PPO experiments."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from typing import Any


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
        value = int(payload.get(key, default))
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
        value = float(payload.get(key, default))
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be in [{minimum}, {maximum}]")
        return value

    def _validated_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = str(payload.get("device", "auto"))
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        init_checkpoint = None
        if payload.get("initCheckpoint"):
            candidate = (self.project_root / str(payload["initCheckpoint"])).resolve()
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
        return {
            "updates": self._bounded_int(payload, "updates", 12, 1, 200),
            "steps": self._bounded_int(payload, "steps", 128, 16, 2048),
            "envs": self._bounded_int(payload, "envs", 32, 1, 512),
            "epochs": self._bounded_int(payload, "epochs", 4, 1, 20),
            "batchSize": self._bounded_int(payload, "batchSize", 1024, 32, 32768),
            "seed": self._bounded_int(payload, "seed", 7, 0, 2_147_483_647),
            "targetSpeed": self._bounded_float(
                payload,
                "targetSpeed",
                0.35,
                0.0,
                1.2,
            ),
            "episodeSeconds": self._bounded_float(
                payload,
                "episodeSeconds",
                8.0,
                1.0,
                30.0,
            ),
            "verticalConstraint": bool(payload.get("verticalConstraint", False)),
            "armSwing": bool(payload.get("armSwing", True)),
            "device": device,
            "initCheckpoint": init_checkpoint,
        }

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
                "--episode-seconds",
                str(config["episodeSeconds"]),
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
                event = json.loads(line)
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
                elif event.get("event") == "preview":
                    self.state["previewUpdate"] = event.get("update")
                    self.state["previewEvaluation"] = event.get("evaluation")
                elif event.get("event") == "complete":
                    self.state["evaluation"] = event.get("evaluation")

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

    def stop(self) -> dict[str, Any]:
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return self.snapshot()
            self.state["state"] = "stopping"
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            state = dict(self.state)
            state["events"] = list(self.events)
            return state
