from pathlib import Path
import json

import pytest

from web.rl_service import RLTrainingManager


def test_training_manager_accepts_ten_thousand_updates_and_reward_weights(
    tmp_path: Path,
):
    manager = RLTrainingManager(tmp_path)
    config = manager._validated_config(
        {
            "updates": 10_000,
            "motionProfile": "circle-walk",
            "targetTurnRate": 0.28,
            "rewardWeights": {
                "torso": 2.0,
                "com": 1.1,
                "gaitContact": 0.4,
                "gaitSymmetry": 1.4,
                "speed": 0.9,
                "legSwing": 0.38,
                "height": 8.5,
                "lateralTilt": 6.0,
                "dorsalTilt": 5.0,
                "kneeContraction": 0.12,
                "armSwing": 1.75,
                "energy": 0.02,
                "smoothness": 0.08,
                "closure": 400.0,
                "fall": 12.0,
            },
        }
    )
    assert config["updates"] == 10_000
    assert config["rewardWeights"]["armSwing"] == 1.75
    assert config["rewardWeights"]["closure"] == 400.0
    assert config["rewardWeights"]["gaitSymmetry"] == 1.4
    assert config["rewardWeights"]["legSwing"] == 0.38
    assert config["rewardWeights"]["lateralTilt"] == 6.0
    assert config["rewardWeights"]["dorsalTilt"] == 5.0
    assert config["rewardWeights"]["kneeContraction"] == 0.12
    assert config["physicsBackend"] == "teaching-plant-v2"
    assert config["motionProfile"] == "circle-walk"
    assert config["targetTurnRate"] == 0.28


def test_training_manager_rejects_out_of_range_updates_and_nonfinite_weights(
    tmp_path: Path,
):
    manager = RLTrainingManager(tmp_path)
    with pytest.raises(ValueError, match="updates"):
        manager._validated_config({"updates": 10_001})
    with pytest.raises(ValueError, match="armSwing"):
        manager._validated_config(
            {"rewardWeights": {"armSwing": float("nan")}}
        )
    with pytest.raises(ValueError, match="physicsBackend"):
        manager._validated_config({"physicsBackend": "pretend-physx"})


def test_training_manager_restores_latest_completed_experiment(tmp_path: Path):
    experiment = (
        tmp_path
        / "artifacts"
        / "rl"
        / "experiments"
        / "20260724T010203Z-restored"
    )
    experiment.mkdir(parents=True)
    (experiment / "policy.json").write_text(
        json.dumps(
            {
                "config": {
                    "updates": 10_000,
                    "rolloutSteps": 64,
                    "parallelEnvs": 8,
                    "ppoEpochs": 3,
                    "seed": 4,
                    "targetSpeed": 0.4,
                    "episodeSeconds": 6,
                    "verticalConstraint": False,
                    "armSwing": True,
                    "rewardWeights": {"armSwing": 1.2},
                    "device": "cpu",
                }
            }
        ),
        encoding="utf-8",
    )
    (experiment / "metrics.json").write_text(
        json.dumps(
            {
                "training": {
                    "final_update": 10_000,
                    "reward": 3.1,
                    "upright_percent": 99.0,
                },
                "evaluation": {"meanReward": 3.2, "uprightPercent": 100.0},
            }
        ),
        encoding="utf-8",
    )

    state = RLTrainingManager(tmp_path).snapshot()
    assert state["state"] == "complete"
    assert state["experimentId"] == experiment.name
    assert state["progress"]["update"] == 10_000
    assert state["config"]["rewardWeights"]["armSwing"] == 1.2
    assert state["events"][0]["event"] == "restored"

    index = RLTrainingManager(tmp_path).list_sessions()
    assert index["count"] == 1
    restored = index["sessions"][0]
    assert restored["experimentId"] == experiment.name
    assert restored["state"] == "complete"
    assert restored["policyUrl"].endswith("/policy.json")
    assert restored["checkpointAvailable"] is False
    assert restored["config"]["updates"] == 10_000


def test_session_index_retains_incomplete_and_warm_start_metadata(
    tmp_path: Path,
):
    experiment_root = tmp_path / "artifacts" / "rl" / "experiments"
    older = experiment_root / "20260724T010000Z-older"
    newer = experiment_root / "20260724T020000Z-newer"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "live-policy.json").write_text("{}", encoding="utf-8")
    (newer / "policy.json").write_text(
        json.dumps(
            {
                "createdAt": "2026-07-24T02:00:00+00:00",
                "config": {
                    "updates": 44,
                    "rolloutSteps": 96,
                    "parallelEnvs": 12,
                    "ppoEpochs": 5,
                    "batchSize": 256,
                    "rewardWeights": {"torso": 3.0},
                },
            }
        ),
        encoding="utf-8",
    )
    (newer / "metrics.json").write_text(
        json.dumps({"evaluation": {"meanReward": 4.5}}),
        encoding="utf-8",
    )
    (newer / "checkpoint.pt").write_bytes(b"checkpoint")

    sessions = RLTrainingManager(tmp_path).list_sessions()["sessions"]
    assert [row["experimentId"] for row in sessions] == [
        newer.name,
        older.name,
    ]
    assert sessions[0]["config"]["updates"] == 44
    assert sessions[0]["config"]["batchSize"] == 256
    assert sessions[0]["checkpointAvailable"] is True
    assert sessions[0]["checkpointPath"].endswith("/checkpoint.pt")
    assert sessions[0]["evaluation"]["meanReward"] == 4.5
    assert sessions[1]["state"] == "interrupted"
