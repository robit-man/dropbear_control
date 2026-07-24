"""Validate a trained Dropbear walk against the authored residual-zero gait."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict

import torch

from .dropbear_ppo import ACTION_NAMES, DropbearWalkEnv, RewardWeights
from .train_walk import policy_selection_score, write_json_atomic


@torch.no_grad()
def authored_reference_rollout(policy: Dict[str, Any]) -> Dict[str, Any]:
    config = policy["config"]
    env = DropbearWalkEnv(
        num_envs=1,
        device="cpu",
        vertical_constraint=bool(config["verticalConstraint"]),
        arm_swing=bool(config["armSwing"]),
        target_speed=float(config["targetSpeed"]),
        target_turn_rate=float(config.get("targetTurnRate", 0.0)),
        motion_profile=str(config.get("motionProfile", "custom")),
        physics_backend=str(
            config.get("physicsBackend", "teaching-plant-v2")
        ),
        episode_seconds=float(config.get("episodeSeconds", 8.0)),
        reward_weights=RewardWeights.from_dict(config.get("rewardWeights")),
        seed=int(config["seed"]) + 1000,
    )
    env.reset()
    frames = []
    rows = []
    max_steps = int(float(config.get("episodeSeconds", 8.0)) / env.dt)
    for index in range(max_steps):
        _, reward, done, info = env.step(torch.zeros(1, env.action_dim))
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
                        round(float(value), 5)
                        for value in env.contact_loads_kg[0]
                    ],
                }
            )
        rows.append(
            {
                "reward": float(reward[0]),
                "upright": float(info["upright"][0]),
                "fallen": float(info["fallen"][0]),
                "speed": float(info["speed"][0]),
                "turnRate": float(info["turn_rate"][0]),
                "arm": float(info["arm_swing_error"][0]),
                "comHeight": float(info["com_height"][0]),
                "comLateral": abs(float(info["com_lateral"][0])),
                "symmetry": float(info["gait_symmetry_reward"][0]),
                "lateralTilt": math.degrees(
                    abs(float(info["base_roll"][0]))
                ),
                "dorsalTilt": math.degrees(
                    abs(float(info["base_pitch"][0]))
                ),
                "legSwing": float(info["leg_swing_reward"][0]),
                "kneeContraction": math.degrees(
                    float(info["knee_contraction"][0].mean())
                ),
                "tilt": math.degrees(
                    math.hypot(
                        float(info["base_roll"][0]),
                        float(info["base_pitch"][0]),
                    )
                ),
                "closure": max(
                    float(info["closure_residual"][0].max()),
                    float(info["arm_closure_residual"][0].max()),
                ),
            }
        )
        if bool(done[0]):
            break

    count = max(1, len(rows))
    evaluation = {
        "meanReward": sum(row["reward"] for row in rows) / count,
        "uprightPercent": 100.0 * sum(row["upright"] for row in rows) / count,
        "fallPercent": 100.0 * sum(row["fallen"] for row in rows) / count,
        "meanSpeed": sum(row["speed"] for row in rows) / count,
        "meanTurnRate": sum(row["turnRate"] for row in rows) / count,
        "turnRateError": (
            sum(
                abs(
                    row["turnRate"]
                    - float(config.get("targetTurnRate", 0.0))
                )
                for row in rows
            )
            / count
        ),
        "armSwingError": sum(row["arm"] for row in rows) / count,
        "comHeightRangeM": (
            max((row["comHeight"] for row in rows), default=0.0)
            - min((row["comHeight"] for row in rows), default=0.0)
        ),
        "comLateralPeakM": max(
            (row["comLateral"] for row in rows),
            default=0.0,
        ),
        "torsoTiltMeanDegrees": sum(row["tilt"] for row in rows) / count,
        "torsoTiltPeakDegrees": max(
            (row["tilt"] for row in rows),
            default=0.0,
        ),
        "gaitSymmetryScore": (
            100.0 * sum(row["symmetry"] for row in rows) / count
        ),
        "lateralTiltMeanDegrees": (
            sum(row["lateralTilt"] for row in rows) / count
        ),
        "lateralTiltPeakDegrees": max(
            (row["lateralTilt"] for row in rows),
            default=0.0,
        ),
        "dorsalTiltMeanDegrees": (
            sum(row["dorsalTilt"] for row in rows) / count
        ),
        "dorsalTiltPeakDegrees": max(
            (row["dorsalTilt"] for row in rows),
            default=0.0,
        ),
        "legSwingScore": (
            100.0 * sum(row["legSwing"] for row in rows) / count
        ),
        "kneeContractionMeanDegrees": (
            sum(row["kneeContraction"] for row in rows) / count
        ),
        "kneeContractionPeakDegrees": max(
            (row["kneeContraction"] for row in rows),
            default=0.0,
        ),
        "closureMaxM": max((row["closure"] for row in rows), default=0.0),
        "durationSeconds": frames[-1]["time"] if frames else 0.0,
        "frameCount": len(frames),
    }
    return {
        "schema": "dropbear-walk-policy-v2",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "groundTruth": policy["groundTruth"],
        "config": {
            **config,
            "source": "authored-zero-residual-reference",
        },
        "jointOrder": list(ACTION_NAMES),
        "training": {
            "mode": "authored-zero-residual-reference",
        },
        "evaluation": evaluation,
        "frames": frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy")
    parser.add_argument("--out")
    parser.add_argument("--reference-policy-out")
    parser.add_argument("--expected-policy-epochs", type=int, default=1000)
    args = parser.parse_args()

    policy_path = Path(args.policy)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schema") != "dropbear-walk-policy-v2":
        raise SystemExit("unsupported policy schema")
    if policy.get("jointOrder") != list(ACTION_NAMES):
        raise SystemExit("policy joint order does not match the 22-motor plant")

    reference = authored_reference_rollout(policy)
    if args.reference_policy_out:
        write_json_atomic(Path(args.reference_policy_out), reference)

    config = policy["config"]
    trained = policy["evaluation"]
    baseline = reference["evaluation"]
    target_speed = float(config["targetSpeed"])
    target_turn_rate = float(config.get("targetTurnRate", 0.0))
    episode_seconds = float(config.get("episodeSeconds", 8.0))
    trained_score = policy_selection_score(
        trained,
        target_speed=target_speed,
        target_turn_rate=target_turn_rate,
        episode_seconds=episode_seconds,
    )
    baseline_score = policy_selection_score(
        baseline,
        target_speed=target_speed,
        target_turn_rate=target_turn_rate,
        episode_seconds=episode_seconds,
    )
    completed_policy_epochs = int(config["updates"]) * int(config["ppoEpochs"])
    checks = {
        "policyEpochs": completed_policy_epochs == args.expected_policy_epochs,
        "freeRoot": config["verticalConstraint"] is False,
        "armSwing": config["armSwing"] is True,
        "forward": float(trained["meanSpeed"]) > 0.05,
        "targetSpeed": abs(float(trained["meanSpeed"]) - target_speed) <= 0.12,
        "targetTurnRate": (
            abs(float(trained.get("meanTurnRate", 0.0)) - target_turn_rate)
            <= max(0.12, abs(target_turn_rate) * 0.45)
        ),
        "closedChains": float(trained["closureMaxM"]) <= 5e-4,
        "stableNonRegression": trained_score >= baseline_score,
    }
    deltas = {
        key: float(trained[key]) - float(baseline[key])
        for key in (
            "meanReward",
            "uprightPercent",
            "meanSpeed",
            "comHeightRangeM",
            "comLateralPeakM",
            "torsoTiltMeanDegrees",
            "torsoTiltPeakDegrees",
            "gaitSymmetryScore",
            "lateralTiltMeanDegrees",
            "dorsalTiltMeanDegrees",
            "legSwingScore",
            "kneeContractionMeanDegrees",
            "durationSeconds",
        )
    }
    report = {
        "schema": "dropbear-walk-validation-v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "policy": str(policy_path),
        "completedPolicyEpochs": completed_policy_epochs,
        "selectedUpdate": policy.get("training", {}).get("selected_update"),
        "trainedSelectionScore": trained_score,
        "baselineSelectionScore": baseline_score,
        "trained": trained,
        "authoredReference": baseline,
        "deltas": deltas,
        "checks": checks,
        "passed": all(checks.values()),
    }
    if args.out:
        write_json_atomic(Path(args.out), report)
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
