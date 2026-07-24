"""Train the CUDA-first Dropbear compatibility controller.

The CLI is an end-to-end CUDA smoke and integration trainer.  It intentionally
uses the repository's differentiable teaching plant so it can run without
Isaac Lab.  Its 90-observation/64-token/22-action artifacts are deliberately
incompatible with the pinned upstream 784-input SONIC ABI.

Examples::

    python3 -m rl.sonic_train --devices 0,1 --updates 10
    python3 -m rl.sonic_train --device cpu --allow-cpu --updates 1

The second form is explicitly test-only.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any, Dict
import uuid

import torch

from .dropbear_ppo import DropbearWalkEnv
from .sonic_core import (
    ACTION_DIM,
    OBSERVATION_DIM,
    DevicePlan,
    SonicPPO,
    configure_cuda,
    save_checkpoint,
    session_manifest,
    sha256_file,
    write_json_atomic,
)
from .sonic_reference import load_reference


@dataclass(frozen=True)
class SonicTrainConfig:
    output_dir: str = "artifacts/rl/sonic"
    session_id: str = ""
    reference_path: str = ""
    device: str = "cuda"
    devices: str = ""
    allow_cpu: bool = False
    amp: bool = True
    amp_dtype: str = "bfloat16"
    seed: int = 47
    updates: int = 20
    rollout_steps: int = 128
    environments: int = 256
    ppo_epochs: int = 4
    batch_size: int = 4096
    hidden_dim: int = 256
    learning_rate: float = 3e-4
    reference_frames: int = 400
    reference_tracking_weight: float = 0.35
    target_speed: float = 0.26
    target_turn_rate: float = 0.0
    motion_profile: str = "gentle-forward"
    vertical_constraint: bool = False

    def validate(self) -> None:
        if not 1 <= self.updates <= 10_000:
            raise ValueError("updates must be in [1, 10000]")
        if not 2 <= self.rollout_steps <= 100_000:
            raise ValueError("rollout_steps must be in [2, 100000]")
        if not 1 <= self.environments <= 65_536:
            raise ValueError("environments must be in [1, 65536]")
        if not 1 <= self.ppo_epochs <= 64:
            raise ValueError("ppo_epochs must be in [1, 64]")
        if not 1 <= self.batch_size <= 1_048_576:
            raise ValueError("batch_size must be in [1, 1048576]")
        if self.hidden_dim not in {128, 256, 512, 1024}:
            raise ValueError("hidden_dim must be one of 128, 256, 512, 1024")
        if not math.isfinite(self.learning_rate) or not 1e-7 <= self.learning_rate <= 0.1:
            raise ValueError("learning_rate must be in [1e-7, 0.1]")
        if not 2 <= self.reference_frames <= 1_000_000:
            raise ValueError("reference_frames must be in [2, 1000000]")
        if (
            not math.isfinite(self.reference_tracking_weight)
            or not 0.0 <= self.reference_tracking_weight <= 20.0
        ):
            raise ValueError("reference_tracking_weight must be in [0, 20]")
        if self.motion_profile not in {"gentle-forward", "circle-walk", "custom"}:
            raise ValueError(f"unsupported motion profile: {self.motion_profile}")


def gae_returns(
    rewards: torch.Tensor,
    values: torch.Tensor,
    dones: torch.Tensor,
    last_value: torch.Tensor,
    gamma: float = 0.99,
    lam: float = 0.95,
) -> tuple[torch.Tensor, torch.Tensor]:
    advantages = torch.zeros_like(rewards)
    running = torch.zeros_like(last_value)
    for index in range(rewards.shape[0] - 1, -1, -1):
        next_value = last_value if index == rewards.shape[0] - 1 else values[index + 1]
        nonterminal = 1.0 - dones[index].float()
        delta = rewards[index] + gamma * next_value * nonterminal - values[index]
        running = delta + gamma * lam * nonterminal * running
        advantages[index] = running
    return advantages + values, advantages


def _config_payload(config: SonicTrainConfig) -> Dict[str, Any]:
    payload = asdict(config)
    # The default is CUDA and allow_cpu must stay visibly test-only.
    payload["cuda_first"] = True
    payload["runtime_mode"] = (
        "local teaching-plant compatibility validation; "
        "authoritative Isaac/PhysX run absent"
    )
    return payload


def _emit(event: Dict[str, Any], *, jsonl: bool) -> None:
    if jsonl:
        print(
            json.dumps(
                event,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            ),
            flush=True,
        )
        return
    name = event.get("event")
    if name == "progress":
        print(
            "update={update}/{updates} reward={reward:.4f} "
            "tracking={tracking_reward:.4f} upright={upright_percent:.1f}% "
            "fall={fall_percent:.1f}%".format(**event),
            flush=True,
        )
    else:
        print(json.dumps(event, sort_keys=True), flush=True)


def train_sonic(
    config: SonicTrainConfig,
    *,
    jsonl: bool = False,
    deployment_required: bool = False,
) -> Dict[str, Any]:
    """Run a complete session and return its manifest."""

    config.validate()
    plan = DevicePlan.resolve(
        config.device,
        devices=config.devices,
        allow_cpu=config.allow_cpu,
        amp=config.amp,
        amp_dtype=config.amp_dtype,
    )
    configure_cuda(plan, config.seed)
    reference = load_reference(
        Path(config.reference_path) if config.reference_path else None,
        frame_count=config.reference_frames,
        target_speed=config.target_speed,
        target_turn_rate=config.target_turn_rate,
        motion_profile=config.motion_profile,
    )
    env = DropbearWalkEnv(
        num_envs=config.environments,
        device=plan.primary,
        dt=1.0 / reference.frequency_hz,
        vertical_constraint=config.vertical_constraint,
        arm_swing=True,
        target_speed=config.target_speed,
        target_turn_rate=config.target_turn_rate,
        motion_profile=config.motion_profile,
        physics_backend="teaching-plant-v2",
        seed=config.seed,
    )
    if env.observation_dim != OBSERVATION_DIM or env.action_dim != ACTION_DIM:
        raise RuntimeError("teaching plant no longer matches the SONIC contract")
    agent = SonicPPO(
        plan,
        learning_rate=config.learning_rate,
        hidden_dim=config.hidden_dim,
    )
    session_id = config.session_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    output_dir = Path(config.output_dir) / session_id
    checkpoint_path = output_dir / "sonic_policy.pt"
    manifest_path = output_dir / "session.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    _emit(
        {
            "event": "started",
            "session_id": session_id,
            "device": plan.as_manifest(),
            "reference": reference.metadata(),
            "updates": config.updates,
            "observation_dim": OBSERVATION_DIM,
            "motion_token_dim": 64,
            "action_dim": ACTION_DIM,
        },
        jsonl=jsonl,
    )

    observation = env.reset()
    final_metrics: Dict[str, Any] = {}
    started = time.perf_counter()

    for update in range(config.updates):
        observations = []
        motion_tokens = []
        actions = []
        log_probabilities = []
        values = []
        rewards = []
        dones = []
        tracking_rewards = []
        upright_samples = []
        fallen_samples = []
        closure_samples = []

        for _ in range(config.rollout_steps):
            # The reference frame is derived from each plant lane's actual
            # clock. This keeps reset phase, token, tracking reward, and the
            # residual baseline identical instead of advancing a disconnected
            # global counter.
            reference_index = torch.floor(
                env.t.detach().cpu() * reference.frequency_hz + 1e-6
            ).to(torch.long)
            ref = reference.sample(reference_index, plan.torch_device)
            action, log_probability, value = agent.act(
                observation,
                ref["token"],
            )
            next_observation, plant_reward, done, info = env.step(
                action,
                reference_override=ref["q"],
            )
            tracking_error = (env.q - ref["q"]).square().mean(dim=1)
            tracking_reward = torch.exp(-4.0 * tracking_error)
            reward = (
                plant_reward
                + config.reference_tracking_weight * tracking_reward
            )

            observations.append(observation)
            motion_tokens.append(ref["token"])
            actions.append(action)
            log_probabilities.append(log_probability)
            values.append(value)
            rewards.append(reward)
            dones.append(done)
            tracking_rewards.append(tracking_reward)
            upright_samples.append(info["upright"].float())
            fallen_samples.append(info["fallen"].float())
            closure_samples.append(
                torch.maximum(
                    info["closure_residual"].amax(dim=1),
                    info["arm_closure_residual"].amax(dim=1),
                )
            )

            reset_observation = env.reset_done(done)
            observation = next_observation.clone()
            observation[done] = reset_observation[done]

        # Bootstrap with the token matching each lane's post-reset plant time.
        final_reference_index = torch.floor(
            env.t.detach().cpu() * reference.frequency_hz + 1e-6
        ).to(torch.long)
        final_ref = reference.sample(
            final_reference_index,
            plan.torch_device,
        )
        with torch.no_grad():
            last_value = agent.value(observation, final_ref["token"])

        observations_t = torch.stack(observations)
        tokens_t = torch.stack(motion_tokens)
        actions_t = torch.stack(actions)
        log_probabilities_t = torch.stack(log_probabilities)
        values_t = torch.stack(values)
        rewards_t = torch.stack(rewards)
        dones_t = torch.stack(dones)
        returns_t, advantages_t = gae_returns(
            rewards_t,
            values_t,
            dones_t,
            last_value,
        )
        optimizer = agent.update(
            observations_t.reshape(-1, OBSERVATION_DIM),
            tokens_t.reshape(-1, 64),
            actions_t.reshape(-1, ACTION_DIM),
            log_probabilities_t.reshape(-1),
            returns_t.reshape(-1),
            advantages_t.reshape(-1),
            epochs=config.ppo_epochs,
            batch_size=config.batch_size,
        )
        final_metrics = {
            "event": "progress",
            "update": update + 1,
            "updates": config.updates,
            "reward": float(rewards_t.mean()),
            "plant_reward": float(
                rewards_t.mean()
                - config.reference_tracking_weight
                * torch.stack(tracking_rewards).mean()
            ),
            "tracking_reward": float(torch.stack(tracking_rewards).mean()),
            "upright_percent": 100.0 * float(torch.stack(upright_samples).mean()),
            "fall_percent": 100.0 * float(torch.stack(fallen_samples).mean()),
            "closure_max_m": float(torch.stack(closure_samples).amax()),
            "samples": (update + 1)
            * config.rollout_steps
            * config.environments,
            "elapsed_seconds": time.perf_counter() - started,
            **optimizer,
        }
        _emit(final_metrics, jsonl=jsonl)

    checkpoint_payload = save_checkpoint(
        checkpoint_path,
        agent.net,
        config=_config_payload(config),
        reference=reference.metadata(),
        metrics=final_metrics,
    )
    manifest = session_manifest(
        session_id=session_id,
        status=(
            "deployment_pending"
            if deployment_required
            else "complete"
        ),
        plan=plan,
        checkpoint=checkpoint_path,
        reference=reference.metadata(),
        config=_config_payload(config),
        metrics=final_metrics,
    )
    write_json_atomic(manifest_path, manifest)
    result = dict(manifest)
    result["manifest_path"] = str(manifest_path)
    result["checkpoint_path"] = str(checkpoint_path)
    _emit(
        {
            "event": (
                "training_complete"
                if deployment_required
                else "complete"
            ),
            "session_id": session_id,
            "checkpoint": str(checkpoint_path),
            "manifest": str(manifest_path),
            "checkpoint_schema": checkpoint_payload["schema"],
            "deployment_required": deployment_required,
        },
        jsonl=jsonl,
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train the CUDA-first Dropbear compatibility controller",
    )
    parser.add_argument("--output-dir", default="artifacts/rl/sonic")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--reference-path", default="")
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--devices",
        default="",
        help="comma-separated CUDA device indices; e.g. 0,1",
    )
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="explicit test-only CPU fallback",
    )
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
    parser.add_argument("--seed", type=int, default=47)
    parser.add_argument("--updates", type=int, default=20)
    parser.add_argument("--rollout-steps", type=int, default=128)
    parser.add_argument("--environments", type=int, default=256)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--reference-frames", type=int, default=400)
    parser.add_argument("--reference-tracking-weight", type=float, default=0.35)
    parser.add_argument("--target-speed", type=float, default=0.26)
    parser.add_argument("--target-turn-rate", type=float, default=0.0)
    parser.add_argument(
        "--motion-profile",
        choices=("gentle-forward", "circle-walk", "custom"),
        default="gentle-forward",
    )
    parser.add_argument(
        "--vertical-constraint",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--jsonl", action="store_true")
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="export ONNX and build/verify a TensorRT residual engine",
    )
    parser.add_argument(
        "--require-tensorrt",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = SonicTrainConfig(
            **{
                key: value
                for key, value in vars(args).items()
                if key not in {"jsonl", "deploy", "require_tensorrt"}
            }
        )
        result = train_sonic(
            config,
            jsonl=args.jsonl,
            deployment_required=args.deploy,
        )
        if args.deploy:
            from .sonic_deploy import deploy_sonic

            plan = DevicePlan.resolve(
                config.device,
                devices=config.devices,
                allow_cpu=config.allow_cpu,
                amp=config.amp,
                amp_dtype=config.amp_dtype,
            )
            manifest_path = Path(result["manifest_path"])
            try:
                deployment = deploy_sonic(
                    Path(result["checkpoint_path"]),
                    plan,
                    require_tensorrt=args.require_tensorrt,
                )
            except (RuntimeError, ValueError) as error:
                failed = dict(result)
                failed["status"] = "error"
                failed["deployment_error"] = str(error)
                failed["finished_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                failed.pop("manifest_path", None)
                failed.pop("checkpoint_path", None)
                write_json_atomic(manifest_path, failed)
                raise
            completed = dict(result)
            completed["status"] = "complete"
            completed["finished_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            completed["deployment"] = {
                "schema": deployment["schema"],
                "status": deployment["status"],
                "report_path": deployment["report_path"],
                "report_sha256": sha256_file(
                    Path(deployment["report_path"])
                ),
                "onnx_sha256": deployment["onnx"]["onnx_sha256"],
                "engine_sha256": deployment["tensorrt"].get(
                    "engine_sha256"
                ),
            }
            completed.pop("manifest_path", None)
            completed.pop("checkpoint_path", None)
            write_json_atomic(manifest_path, completed)
            _emit(
                {
                    "event": "deployment",
                    "status": deployment["status"],
                    "report": deployment["report_path"],
                    "onnx_error": deployment["onnx"]["validation"][
                        "max_abs_error"
                    ],
                    "tensorrt_status": deployment["tensorrt"]["status"],
                    "tensorrt_error": deployment["tensorrt"].get(
                        "max_abs_error"
                    ),
                },
                jsonl=args.jsonl,
            )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
