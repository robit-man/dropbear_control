"""Train and export a Dropbear walking policy experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from typing import Any, Dict

import torch

from .dropbear_ppo import ACTION_NAMES, DropbearWalkEnv, PPO, RewardWeights


FIRMWARE_COMMIT = "13cf5ecaa39b8b89c794fe905dcea0490cfa7726"
USD_COMMIT = "3c37aedce6d445205671d5714d05ae28b8c90e2c"


def emit(payload: Dict[str, Any], jsonl: bool) -> None:
    if jsonl:
        print(json.dumps(payload, separators=(",", ":")), flush=True)
        return
    event = payload.get("event")
    if event == "progress":
        print(
            "update={update}/{updates} reward={reward:.3f} "
            "upright={upright_percent:.1f}% speed={speed:.3f} "
            "fall={fall_percent:.1f}% closure={closure_max_m:.6f}m".format(**payload),
            flush=True,
        )
    elif event == "complete":
        print(f"saved {payload['checkpoint']}", flush=True)
        print(f"policy {payload['policy']}", flush=True)
    else:
        print(payload, flush=True)


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def policy_selection_score(
    evaluation: Dict[str, Any],
    *,
    target_speed: float,
    target_turn_rate: float = 0.0,
    episode_seconds: float,
) -> float:
    """Rank deterministic previews with stability ahead of raw velocity."""

    completed_fraction = min(
        1.0,
        float(evaluation["durationSeconds"]) / max(episode_seconds, 1e-6),
    )
    speed_error = abs(float(evaluation["meanSpeed"]) - target_speed)
    turn_error = abs(
        float(evaluation.get("meanTurnRate", 0.0)) - target_turn_rate
    )
    return (
        float(evaluation["meanReward"])
        + 0.025 * float(evaluation["uprightPercent"])
        - 0.025 * float(evaluation["torsoTiltMeanDegrees"])
        - 1.5 * speed_error
        - 1.2 * turn_error
        - 2.0 * float(evaluation["comHeightRangeM"])
        - 2.0 * float(evaluation["comLateralPeakM"])
        + 0.5 * completed_fraction
    )


def gae_returns(
    rewards: torch.Tensor,
    values: torch.Tensor,
    dones: torch.Tensor,
    last_value: torch.Tensor,
    gamma: float = 0.99,
    lam: float = 0.95,
):
    advantages = torch.zeros_like(rewards)
    running = torch.zeros_like(last_value)
    for index in range(rewards.shape[0] - 1, -1, -1):
        next_value = last_value if index == rewards.shape[0] - 1 else values[index + 1]
        nonterminal = 1.0 - dones[index].float()
        delta = rewards[index] + gamma * next_value * nonterminal - values[index]
        running = delta + gamma * lam * nonterminal * running
        advantages[index] = running
    return advantages + values, advantages


def reward_weights_from_args(args: argparse.Namespace) -> RewardWeights:
    return RewardWeights(
        torso_stability=args.reward_torso,
        com_stability=args.reward_com,
        gait_contact=args.reward_gait_contact,
        gait_symmetry=args.reward_gait_symmetry,
        speed_tracking=args.reward_speed,
        leg_swing=args.reward_leg_swing,
        height_penalty=args.penalty_height,
        lateral_tilt_penalty=args.penalty_lateral_tilt,
        dorsal_tilt_penalty=args.penalty_dorsal_tilt,
        knee_contraction_penalty=args.penalty_knee_contraction,
        arm_swing_penalty=args.penalty_arm_swing,
        energy_penalty=args.penalty_energy,
        smoothness_penalty=args.penalty_smoothness,
        closure_penalty=args.penalty_closure,
        fall_penalty=args.penalty_fall,
    )


@torch.no_grad()
def export_policy(
    agent: PPO,
    args: argparse.Namespace,
    policy_path: Path | None,
    training_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    env = DropbearWalkEnv(
        num_envs=1,
        device=args.device,
        vertical_constraint=args.vertical_constraint,
        arm_swing=args.arm_swing,
        target_speed=args.target_speed,
        target_turn_rate=args.target_turn_rate,
        motion_profile=args.motion_profile,
        physics_backend=args.physics_backend,
        episode_seconds=args.episode_seconds,
        reward_weights=reward_weights_from_args(args),
        seed=args.seed + 1000,
    )
    obs = env.reset()
    frames = []
    rewards = []
    upright = []
    falls = []
    speeds = []
    turn_rates = []
    arm_errors = []
    closure = []
    com_heights = []
    com_lateral = []
    torso_tilt = []
    gait_symmetry = []
    lateral_tilt = []
    dorsal_tilt = []
    leg_swing = []
    knee_contraction = []
    max_steps = int(args.episode_seconds / env.dt)
    for index in range(max_steps):
        action, _, _ = agent.act(obs, deterministic=True)
        obs, reward, done, info = env.step(action)
        if index % 2 == 0:
            frames.append(
                {
                    "time": round(float(env.t[0]), 4),
                    "phase": round(float((env.t[0] * 1.2) % 1.0), 6),
                    "q": [round(float(value), 7) for value in env.q[0]],
                    "dq": [round(float(value), 7) for value in env.dq[0]],
                    "base": {
                        "height": round(float(env.base_height[0]), 7),
                        "x": round(float(env.base_x[0]), 7),
                        "y": round(float(env.base_y[0]), 7),
                        "vx": round(float(env.base_vx[0]), 7),
                        "roll": round(float(env.base_roll[0]), 7),
                        "pitch": round(float(env.base_pitch[0]), 7),
                        "yaw": round(float(env.base_yaw[0]), 7),
                        "yawRate": round(float(env.base_yaw_rate[0]), 7),
                    },
                    "contactLoadsKg": [
                        round(float(value), 5) for value in env.contact_loads_kg[0]
                    ],
                }
            )
        rewards.append(float(reward[0]))
        upright.append(float(info["upright"][0]))
        falls.append(float(info["fallen"][0]))
        speeds.append(float(info["speed"][0]))
        turn_rates.append(float(info["turn_rate"][0]))
        arm_errors.append(float(info["arm_swing_error"][0]))
        com_heights.append(float(info["com_height"][0]))
        com_lateral.append(abs(float(info["com_lateral"][0])))
        gait_symmetry.append(float(info["gait_symmetry_reward"][0]))
        lateral_tilt.append(
            math.degrees(abs(float(info["base_roll"][0])))
        )
        dorsal_tilt.append(
            math.degrees(abs(float(info["base_pitch"][0])))
        )
        leg_swing.append(float(info["leg_swing_reward"][0]))
        knee_contraction.append(
            math.degrees(float(info["knee_contraction"][0].mean()))
        )
        torso_tilt.append(
            math.degrees(
                math.hypot(
                    float(info["base_roll"][0]),
                    float(info["base_pitch"][0]),
                )
            )
        )
        closure.append(
            max(
                float(info["closure_residual"][0].max()),
                float(info["arm_closure_residual"][0].max()),
            )
        )
        if bool(done[0]):
            break

    evaluation = {
        "meanReward": sum(rewards) / max(1, len(rewards)),
        "uprightPercent": 100.0 * sum(upright) / max(1, len(upright)),
        "fallPercent": 100.0 * sum(falls) / max(1, len(falls)),
        "meanSpeed": sum(speeds) / max(1, len(speeds)),
        "meanTurnRate": sum(turn_rates) / max(1, len(turn_rates)),
        "turnRateError": (
            sum(
                abs(value - args.target_turn_rate)
                for value in turn_rates
            )
            / max(1, len(turn_rates))
        ),
        "pathRadiusM": (
            abs(sum(speeds) / max(1, len(speeds)))
            / max(abs(sum(turn_rates) / max(1, len(turn_rates))), 1e-6)
            if abs(args.target_turn_rate) > 1e-6
            else None
        ),
        "armSwingError": sum(arm_errors) / max(1, len(arm_errors)),
        "comHeightRangeM": (
            max(com_heights, default=0.0) - min(com_heights, default=0.0)
        ),
        "comLateralPeakM": max(com_lateral, default=0.0),
        "torsoTiltMeanDegrees": sum(torso_tilt) / max(1, len(torso_tilt)),
        "torsoTiltPeakDegrees": max(torso_tilt, default=0.0),
        "gaitSymmetryScore": (
            100.0 * sum(gait_symmetry) / max(1, len(gait_symmetry))
        ),
        "lateralTiltMeanDegrees": (
            sum(lateral_tilt) / max(1, len(lateral_tilt))
        ),
        "lateralTiltPeakDegrees": max(lateral_tilt, default=0.0),
        "dorsalTiltMeanDegrees": (
            sum(dorsal_tilt) / max(1, len(dorsal_tilt))
        ),
        "dorsalTiltPeakDegrees": max(dorsal_tilt, default=0.0),
        "legSwingScore": 100.0 * sum(leg_swing) / max(1, len(leg_swing)),
        "kneeContractionMeanDegrees": (
            sum(knee_contraction) / max(1, len(knee_contraction))
        ),
        "kneeContractionPeakDegrees": max(knee_contraction, default=0.0),
        "closureMaxM": max(closure, default=0.0),
        "durationSeconds": frames[-1]["time"] if frames else 0,
        "frameCount": len(frames),
    }
    policy = {
        "schema": "dropbear-walk-policy-v2",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "groundTruth": {
            "firmwareCommit": FIRMWARE_COMMIT,
            "usdCommit": USD_COMMIT,
            "kneeLockDegrees": 180,
            "actionOrdering": "12 leg motor sources followed by 10 arm motor sources",
            "elbowClosure": "Revolute41 motor with five passive joints and three retained constraints per arm",
        },
        "config": {
            "updates": args.updates,
            "rolloutSteps": args.steps,
            "parallelEnvs": args.envs,
            "ppoEpochs": args.epochs,
            "batchSize": args.batch_size,
            "policyEpochs": args.updates * args.epochs,
            "seed": args.seed,
            "targetSpeed": args.target_speed,
            "targetTurnRate": args.target_turn_rate,
            "motionProfile": args.motion_profile,
            "episodeSeconds": args.episode_seconds,
            "verticalConstraint": args.vertical_constraint,
            "armSwing": args.arm_swing,
            "rewardWeights": reward_weights_from_args(args).as_dict(),
            "device": args.device,
            "physicsBackend": args.physics_backend,
            "dt": env.dt,
        },
        "jointOrder": list(ACTION_NAMES),
        "training": training_metrics,
        "evaluation": evaluation,
        "frames": frames,
    }
    if policy_path is not None:
        write_json_atomic(policy_path, policy)
    return policy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updates", type=int, default=20)
    parser.add_argument("--steps", type=int, default=256)
    parser.add_argument("--envs", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-speed", type=float, default=0.26)
    parser.add_argument("--target-turn-rate", type=float, default=0.0)
    parser.add_argument(
        "--motion-profile",
        choices=("gentle-forward", "circle-walk", "custom"),
        default="gentle-forward",
    )
    parser.add_argument(
        "--physics-backend",
        choices=("teaching-plant-v2", "mujoco-usd-proxy-v1"),
        default="teaching-plant-v2",
    )
    parser.add_argument("--episode-seconds", type=float, default=8.0)
    parser.add_argument("--reward-torso", type=float, default=1.75)
    parser.add_argument("--reward-com", type=float, default=1.20)
    parser.add_argument("--reward-gait-contact", type=float, default=0.90)
    parser.add_argument("--reward-gait-symmetry", type=float, default=1.10)
    parser.add_argument("--reward-speed", type=float, default=0.55)
    parser.add_argument("--reward-leg-swing", type=float, default=0.28)
    parser.add_argument("--penalty-height", type=float, default=8.0)
    parser.add_argument("--penalty-lateral-tilt", type=float, default=5.0)
    parser.add_argument("--penalty-dorsal-tilt", type=float, default=4.5)
    parser.add_argument("--penalty-knee-contraction", type=float, default=0.18)
    parser.add_argument("--penalty-arm-swing", type=float, default=0.35)
    parser.add_argument("--penalty-energy", type=float, default=0.018)
    parser.add_argument("--penalty-smoothness", type=float, default=0.065)
    parser.add_argument("--penalty-closure", type=float, default=300.0)
    parser.add_argument("--penalty-fall", type=float, default=7.0)
    parser.add_argument(
        "--vertical-constraint",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--arm-swing",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--out", default="artifacts/rl/dropbear_ppo.pt")
    parser.add_argument("--policy-out", default="artifacts/rl/dropbear_policy.json")
    parser.add_argument("--live-policy-out")
    parser.add_argument("--init-checkpoint")
    parser.add_argument("--metrics-out", default="artifacts/rl/dropbear_metrics.json")
    parser.add_argument("--jsonl", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.updates <= 10_000:
        parser.error("--updates must be in [1, 10000]")
    if not math.isfinite(args.target_turn_rate) or not -1.2 <= args.target_turn_rate <= 1.2:
        parser.error("--target-turn-rate must be in [-1.2, 1.2]")
    if args.physics_backend == "mujoco-usd-proxy-v1":
        if args.device not in {"auto", "cpu"}:
            parser.error("MuJoCo Dropbear backend requires --device cpu")
        if args.envs > 32:
            parser.error("MuJoCo Dropbear backend supports at most 32 environments")
    coefficient_limits = {
        "reward_torso": 20.0,
        "reward_com": 20.0,
        "reward_gait_contact": 20.0,
        "reward_gait_symmetry": 20.0,
        "reward_speed": 20.0,
        "reward_leg_swing": 20.0,
        "penalty_height": 100.0,
        "penalty_lateral_tilt": 100.0,
        "penalty_dorsal_tilt": 100.0,
        "penalty_knee_contraction": 20.0,
        "penalty_arm_swing": 20.0,
        "penalty_energy": 20.0,
        "penalty_smoothness": 20.0,
        "penalty_closure": 5000.0,
        "penalty_fall": 100.0,
    }
    for name, maximum in coefficient_limits.items():
        value = float(getattr(args, name))
        if not math.isfinite(value) or not 0.0 <= value <= maximum:
            parser.error(
                f"--{name.replace('_', '-')} must be in [0, {maximum:g}]"
            )

    if args.device == "auto":
        args.device = (
            "cpu"
            if args.physics_backend == "mujoco-usd-proxy-v1"
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if args.device.startswith("cuda"):
        torch.cuda.manual_seed_all(args.seed)

    env = DropbearWalkEnv(
        args.envs,
        args.device,
        vertical_constraint=args.vertical_constraint,
        arm_swing=args.arm_swing,
        target_speed=args.target_speed,
        target_turn_rate=args.target_turn_rate,
        motion_profile=args.motion_profile,
        physics_backend=args.physics_backend,
        episode_seconds=args.episode_seconds,
        reward_weights=reward_weights_from_args(args),
        seed=args.seed,
    )
    agent = PPO(env.observation_dim, env.action_dim, args.device)
    if args.init_checkpoint:
        initial = torch.load(
            Path(args.init_checkpoint),
            map_location=args.device,
            weights_only=False,
        )
        if int(initial.get("obs_dim", -1)) != env.observation_dim:
            raise ValueError("initial checkpoint observation dimension mismatch")
        if int(initial.get("action_dim", -1)) != env.action_dim:
            raise ValueError("initial checkpoint action dimension mismatch")
        if initial.get("joint_order") != list(ACTION_NAMES):
            raise ValueError("initial checkpoint joint order mismatch")
        agent.net.load_state_dict(initial["model"])
    obs = env.reset()
    last_metrics: Dict[str, Any] = {}
    best_state: Dict[str, torch.Tensor] | None = None
    best_metrics: Dict[str, Any] | None = None
    best_evaluation: Dict[str, Any] | None = None
    best_score = -math.inf
    best_update = 0
    emit(
        {
            "event": "started",
            "updates": args.updates,
            "device": args.device,
            "observationDim": env.observation_dim,
            "actionDim": env.action_dim,
            "verticalConstraint": args.vertical_constraint,
            "armSwing": args.arm_swing,
            "motionProfile": args.motion_profile,
            "physicsBackend": args.physics_backend,
            "targetTurnRate": args.target_turn_rate,
            "rewardWeights": reward_weights_from_args(args).as_dict(),
            "initCheckpoint": args.init_checkpoint,
        },
        args.jsonl,
    )

    initial_metrics = {
        "event": "initial",
        "update": 0,
        "updates": args.updates,
        "source_checkpoint": args.init_checkpoint,
    }
    initial_preview = export_policy(
        agent,
        args,
        Path(args.live_policy_out) if args.live_policy_out else None,
        initial_metrics,
    )
    best_score = policy_selection_score(
        initial_preview["evaluation"],
        target_speed=args.target_speed,
        target_turn_rate=args.target_turn_rate,
        episode_seconds=args.episode_seconds,
    )
    best_update = 0
    best_metrics = dict(initial_metrics)
    best_evaluation = dict(initial_preview["evaluation"])
    best_state = {
        name: value.detach().cpu().clone()
        for name, value in agent.net.state_dict().items()
    }
    if args.live_policy_out:
        emit(
            {
                "event": "preview",
                "update": 0,
                "updates": args.updates,
                "policy": str(Path(args.live_policy_out)),
                "evaluation": initial_preview["evaluation"],
                "selectionScore": best_score,
                "isBest": True,
                "bestUpdate": 0,
            },
            args.jsonl,
        )

    for update in range(args.updates):
        states = []
        actions = []
        logps = []
        values = []
        rewards = []
        dones = []
        infos = []
        for _ in range(args.steps):
            action, logp, value = agent.act(obs)
            nxt, reward, done, info = env.step(action)
            states.append(obs)
            actions.append(action)
            logps.append(logp)
            values.append(value)
            rewards.append(reward)
            dones.append(done)
            infos.append(info)
            reset_obs = env.reset_done(done)
            obs = nxt.clone()
            obs[done] = reset_obs[done]

        states_t = torch.stack(states)
        actions_t = torch.stack(actions)
        logps_t = torch.stack(logps)
        values_t = torch.stack(values)
        rewards_t = torch.stack(rewards)
        dones_t = torch.stack(dones)
        with torch.no_grad():
            _, last_value = agent.net(obs)
        returns_t, advantages_t = gae_returns(
            rewards_t,
            values_t,
            dones_t,
            last_value,
        )
        optimizer = agent.update(
            states_t.reshape(-1, env.observation_dim),
            actions_t.reshape(-1, env.action_dim),
            logps_t.reshape(-1),
            returns_t.reshape(-1),
            advantages_t.reshape(-1),
            epochs=args.epochs,
            batch_size=args.batch_size,
        )
        latest = infos[-1]
        all_upright = torch.stack([row["upright"].float() for row in infos])
        all_fallen = torch.stack([row["fallen"].float() for row in infos])
        all_speed = torch.stack([row["speed"] for row in infos])
        all_turn_rate = torch.stack([row["turn_rate"] for row in infos])
        all_arm = torch.stack([row["arm_swing_error"] for row in infos])
        all_symmetry = torch.stack(
            [row["gait_symmetry_reward"] for row in infos]
        )
        all_leg_swing = torch.stack(
            [row["leg_swing_reward"] for row in infos]
        )
        all_knee_contraction = torch.stack(
            [row["knee_contraction"].mean(1) for row in infos]
        )
        all_roll = torch.stack([row["base_roll"] for row in infos])
        all_pitch = torch.stack([row["base_pitch"] for row in infos])
        all_com_height = torch.stack([row["com_height"] for row in infos])
        all_com_lateral = torch.stack([row["com_lateral"] for row in infos])
        all_leg_closure = torch.stack([row["closure_residual"] for row in infos])
        all_arm_closure = torch.stack([row["arm_closure_residual"] for row in infos])
        closure_max = torch.maximum(
            all_leg_closure.amax(),
            all_arm_closure.amax(),
        )
        last_metrics = {
            "event": "progress",
            "update": update + 1,
            "updates": args.updates,
            "reward": float(rewards_t.mean()),
            "upright_percent": 100.0 * float(all_upright.mean()),
            "fall_percent": 100.0 * float(all_fallen.mean()),
            "speed": float(all_speed.mean()),
            "turn_rate": float(all_turn_rate.mean()),
            "turn_rate_error": float(
                (all_turn_rate - args.target_turn_rate).abs().mean()
            ),
            "arm_swing_error": float(all_arm.mean()),
            "gait_symmetry_percent": 100.0 * float(all_symmetry.mean()),
            "leg_swing_percent": 100.0 * float(all_leg_swing.mean()),
            "knee_contraction_degrees": float(
                torch.rad2deg(all_knee_contraction).mean()
            ),
            "lateral_tilt_degrees": float(
                torch.rad2deg(all_roll.abs()).mean()
            ),
            "dorsal_tilt_degrees": float(
                torch.rad2deg(all_pitch.abs()).mean()
            ),
            "torso_tilt_degrees": float(
                torch.rad2deg(torch.sqrt(all_roll.square() + all_pitch.square())).mean()
            ),
            "com_variation_m": float(all_com_height.std(unbiased=False)),
            "com_lateral_m": float(all_com_lateral.abs().mean()),
            "closure_max_m": float(closure_max),
            "base_height": float(latest["base_height"].mean()),
            **optimizer,
        }
        emit(last_metrics, args.jsonl)
        preview = export_policy(
            agent,
            args,
            Path(args.live_policy_out) if args.live_policy_out else None,
            last_metrics,
        )
        selection_score = policy_selection_score(
            preview["evaluation"],
            target_speed=args.target_speed,
            target_turn_rate=args.target_turn_rate,
            episode_seconds=args.episode_seconds,
        )
        is_best = selection_score > best_score
        if is_best:
            best_score = selection_score
            best_update = update + 1
            best_metrics = dict(last_metrics)
            best_evaluation = dict(preview["evaluation"])
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in agent.net.state_dict().items()
            }
        if args.live_policy_out:
            emit(
                {
                    "event": "preview",
                    "update": update + 1,
                    "updates": args.updates,
                    "policy": str(Path(args.live_policy_out)),
                    "evaluation": preview["evaluation"],
                    "selectionScore": selection_score,
                    "isBest": is_best,
                    "bestUpdate": best_update,
                },
                args.jsonl,
            )

    selected_metrics = dict(best_metrics or last_metrics)
    if best_state is not None:
        agent.net.load_state_dict(best_state)
        selected_metrics.update(
            {
                "selected_update": best_update,
                "selection_score": best_score,
                "final_update": args.updates,
                "selection_evaluation": best_evaluation,
            }
        )

    checkpoint_path = Path(args.out)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model": agent.net.state_dict(),
            "obs_dim": env.observation_dim,
            "action_dim": env.action_dim,
            "joint_order": list(ACTION_NAMES),
            "config": vars(args),
            "selection": {
                "selected_update": selected_metrics.get("selected_update"),
                "selection_score": selected_metrics.get("selection_score"),
                "completed_updates": args.updates,
            },
            "ground_truth": {
                "firmware_commit": FIRMWARE_COMMIT,
                "usd_commit": USD_COMMIT,
            },
        },
        checkpoint_path,
    )
    policy = export_policy(agent, args, Path(args.policy_out), selected_metrics)
    metrics_path = Path(args.metrics_out)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        metrics_path,
        {
            "training": selected_metrics,
            "evaluation": policy["evaluation"],
            "checkpoint": str(checkpoint_path),
            "policy": str(Path(args.policy_out)),
        },
    )
    emit(
        {
            "event": "complete",
            "checkpoint": str(checkpoint_path),
            "policy": str(Path(args.policy_out)),
            "metrics": str(metrics_path),
            "evaluation": policy["evaluation"],
        },
        args.jsonl,
    )


if __name__ == "__main__":
    main()
