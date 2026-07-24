import copy
import json

import pytest
import torch

from rl.dropbear_ppo import ACTION_NAMES
from rl.sonic_core import (
    ACTION_DIM,
    MOTION_TOKEN_DIM,
    OBSERVATION_DIM,
    DevicePlan,
    SonicActorCritic,
    build_model,
    validate_checkpoint_payload,
)
from rl.sonic_reference import REFERENCE_SCHEMA, SonicReferenceDataset
from rl.sonic_train import SonicTrainConfig, train_sonic


def test_device_plan_requires_explicit_cpu_test_override():
    with pytest.raises(RuntimeError, match="CPU mode is disabled"):
        DevicePlan.resolve("cpu")
    plan = DevicePlan.resolve("cpu", allow_cpu=True, amp=True)
    assert plan.primary == "cpu"
    assert plan.amp_enabled is False
    assert plan.as_manifest()["cuda_required"] is True


def test_token_conditioned_model_has_versioned_dropbear_shapes_and_gradient():
    model = SonicActorCritic()
    observation = torch.randn(3, OBSERVATION_DIM, requires_grad=True)
    token = torch.randn(3, MOTION_TOKEN_DIM, requires_grad=True)
    mu, value, log_std = model(observation, token)
    assert mu.shape == (3, ACTION_DIM)
    assert value.shape == (3,)
    assert log_std.shape == (3, ACTION_DIM)
    assert ACTION_DIM == 22
    assert len(ACTION_NAMES) == ACTION_DIM
    value.sum().backward()
    assert token.grad is not None
    assert float(token.grad.abs().sum()) > 0


def test_builtin_reference_is_deterministic_and_64_dimensional():
    first = SonicReferenceDataset.builtin(frame_count=24)
    second = SonicReferenceDataset.builtin(frame_count=24)
    assert first.sha256 == second.sha256
    assert torch.equal(first.q, second.q)
    assert torch.equal(first.tokens, second.tokens)
    assert first.tokens.shape == (24, MOTION_TOKEN_DIM)
    assert first.q.shape == (24, ACTION_DIM)
    assert first.metadata()["frequency_hz"] == 50.0


def test_reference_json_rejects_unversioned_dashboard_policy_shape(tmp_path):
    builtin = SonicReferenceDataset.builtin(frame_count=3)
    payload = {
        "jointOrder": list(ACTION_NAMES),
        "frequencyHz": 50,
        "frames": [
            {
                "time": index / 50,
                "q": builtin.q[index].tolist(),
                "dq": builtin.dq[index].tolist(),
                "base": {
                    "height": 0.8,
                    "x": 0.01 * index,
                    "vx": 0.26,
                    "roll": 0,
                    "pitch": 0,
                    "y": 0,
                    "yaw": 0,
                    "yawRate": 0,
                },
                "contactLoadsKg": builtin.contacts[index].tolist(),
            }
            for index in range(3)
        ],
    }
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="reference schema"):
        SonicReferenceDataset.from_json(path)


def test_reference_json_accepts_upstream_overlay_50hz_shape(tmp_path):
    builtin = SonicReferenceDataset.builtin(frame_count=3)
    payload = {
        "schema": REFERENCE_SCHEMA,
        "sampleRateHz": 50,
        "jointOrder": list(ACTION_NAMES),
        "frameCount": 3,
        "source": {"name": "unit-overlay"},
        "frames": [
            {
                "timeSec": index / 50,
                "jointPositionRad": builtin.q[index].tolist(),
                "jointVelocityRadSec": builtin.dq[index].tolist(),
                "rootPositionM": [0.01 * index, 0.0, 0.8],
                "rootOrientationWxyz": [1.0, 0.0, 0.0, 0.0],
                "contactLoadsKg": builtin.contacts[index].tolist(),
            }
            for index in range(3)
        ],
    }
    path = tmp_path / "overlay-reference.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = SonicReferenceDataset.from_json(path)
    assert loaded.q.shape == (3, ACTION_DIM)
    assert loaded.frequency_hz == 50.0
    assert loaded.base[1, 2] == pytest.approx(0.5)


def test_reference_json_rejects_non_50hz_overlay(tmp_path):
    builtin = SonicReferenceDataset.builtin(frame_count=2)
    payload = {
        "schema": REFERENCE_SCHEMA,
        "jointOrder": list(ACTION_NAMES),
        "sampleRateHz": 25,
        "frameCount": 2,
        "frames": [
            {
                "timeSec": index / 25,
                "jointPositionRad": builtin.q[index].tolist(),
                "jointVelocityRadSec": builtin.dq[index].tolist(),
                "rootPositionM": [0.0, 0.0, 0.8],
                "rootOrientationWxyz": [1.0, 0.0, 0.0, 0.0],
                "contactLoadsKg": builtin.contacts[index].tolist(),
            }
            for index in range(2)
        ],
    }
    path = tmp_path / "25hz-reference.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 50 Hz"):
        SonicReferenceDataset.from_json(path)


def test_reference_json_rejects_noncanonical_order_and_off_grid_timestamp(
    tmp_path,
):
    builtin = SonicReferenceDataset.builtin(frame_count=2)
    payload = {
        "schema": REFERENCE_SCHEMA,
        "sampleRateHz": 50,
        "jointOrder": list(ACTION_NAMES),
        "frameCount": 2,
        "frames": [
            {
                "timeSec": index / 50,
                "jointPositionRad": builtin.q[index].tolist(),
                "jointVelocityRadSec": builtin.dq[index].tolist(),
                "rootPositionM": [0.0, 0.0, 0.8],
                "rootOrientationWxyz": [1.0, 0.0, 0.0, 0.0],
                "contactLoadsKg": builtin.contacts[index].tolist(),
            }
            for index in range(2)
        ],
    }
    path = tmp_path / "invalid-reference.json"
    reversed_order = copy.deepcopy(payload)
    reversed_order["jointOrder"] = list(reversed(ACTION_NAMES))
    path.write_text(json.dumps(reversed_order), encoding="utf-8")
    with pytest.raises(ValueError, match="joint order"):
        SonicReferenceDataset.from_json(path)

    off_grid = copy.deepcopy(payload)
    off_grid["frames"][1]["timeSec"] = 0.0202
    path.write_text(json.dumps(off_grid), encoding="utf-8")
    with pytest.raises(ValueError, match="exact 50 Hz timeline"):
        SonicReferenceDataset.from_json(path)

    nonfinite = copy.deepcopy(payload)
    nonfinite["frames"][1]["timeSec"] = float("nan")
    path.write_text(json.dumps(nonfinite), encoding="utf-8")
    with pytest.raises(ValueError, match="exact 50 Hz timeline"):
        SonicReferenceDataset.from_json(path)


def test_reference_rejects_knee_below_lock_and_negative_contacts():
    builtin = SonicReferenceDataset.builtin(frame_count=3)
    invalid_knee = builtin.q.clone()
    invalid_knee[1, 4] = -0.01
    with pytest.raises(ValueError, match="left_knee"):
        SonicReferenceDataset(
            invalid_knee,
            builtin.dq,
            builtin.base,
            builtin.contacts,
        )

    invalid_contacts = builtin.contacts.clone()
    invalid_contacts[0, 2] = -0.01
    with pytest.raises(ValueError, match="contact loads cannot be negative"):
        SonicReferenceDataset(
            builtin.q,
            builtin.dq,
            builtin.base,
            invalid_contacts,
        )


def test_cpu_training_writes_checkpoint_and_session_manifest(tmp_path):
    result = train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="unit",
            device="cpu",
            allow_cpu=True,
            amp=False,
            updates=1,
            rollout_steps=2,
            environments=2,
            ppo_epochs=1,
            batch_size=4,
            reference_frames=8,
            hidden_dim=128,
        )
    )
    manifest = json.loads(
        (tmp_path / "unit" / "session.json").read_text(encoding="utf-8")
    )
    checkpoint = torch.load(
        tmp_path / "unit" / "sonic_policy.pt",
        map_location="cpu",
        weights_only=False,
    )
    assert result["status"] == "complete"
    assert manifest["schema"] == "dropbear-sonic-training-session-v1"
    assert manifest["contract"]["motion_token_dim"] == 64
    assert manifest["contract"]["action_dim"] == 22
    assert len(manifest["artifacts"]["checkpoint_sha256"]) == 64
    assert checkpoint["schema"] == "dropbear-sonic-checkpoint-v1"
    assert checkpoint["contract"]["joint_order"] == list(ACTION_NAMES)
    assert manifest["contract"] == checkpoint["contract"]
    assert (
        checkpoint["contract"]["action_semantics"]["schema"]
        == "dropbear-local-reference-residual-v1"
    )


def test_required_deployment_is_not_indexed_as_complete_after_training(
    tmp_path,
):
    result = train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="pending-deployment",
            device="cpu",
            allow_cpu=True,
            amp=False,
            updates=1,
            rollout_steps=2,
            environments=2,
            ppo_epochs=1,
            batch_size=4,
            reference_frames=8,
            hidden_dim=128,
        ),
        deployment_required=True,
    )
    manifest = json.loads(
        (
            tmp_path
            / "pending-deployment"
            / "session.json"
        ).read_text(encoding="utf-8")
    )
    assert result["status"] == "deployment_pending"
    assert manifest["status"] == "deployment_pending"


def test_checkpoint_validation_requires_exact_physical_action_contract(tmp_path):
    result = train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="contract",
            device="cpu",
            allow_cpu=True,
            amp=False,
            updates=1,
            rollout_steps=2,
            environments=2,
            ppo_epochs=1,
            batch_size=4,
            reference_frames=8,
            hidden_dim=128,
        )
    )
    payload = torch.load(
        result["checkpoint_path"],
        map_location="cpu",
        weights_only=False,
    )
    validate_checkpoint_payload(payload)

    mutations = []
    changed_scale = copy.deepcopy(payload)
    changed_scale["contract"]["action_semantics"]["scale_rad"][5] += 0.001
    mutations.append((changed_scale, "action_semantics"))
    changed_formula = copy.deepcopy(payload)
    changed_formula["contract"]["action_semantics"]["formula"] = "other"
    mutations.append((changed_formula, "action_semantics"))
    changed_knees = copy.deepcopy(payload)
    changed_knees["contract"]["action_semantics"]["knee_indices"] = [3, 8]
    mutations.append((changed_knees, "action_semantics"))
    changed_frequency = copy.deepcopy(payload)
    changed_frequency["contract"]["frequency_hz"] = 49.0
    mutations.append((changed_frequency, "frequency_hz"))
    changed_reference = copy.deepcopy(payload)
    changed_reference["reference"]["joint_order"] = list(reversed(ACTION_NAMES))
    mutations.append((changed_reference, "reference joint order"))
    changed_token = copy.deepcopy(payload)
    changed_token["contract"]["motion_token_semantics"]["source"] = "other"
    mutations.append((changed_token, "motion-token semantics"))

    for candidate, message in mutations:
        with pytest.raises(ValueError, match=message):
            validate_checkpoint_payload(candidate)


@pytest.mark.skipif(
    torch.cuda.device_count() < 2,
    reason="requires two CUDA devices",
)
def test_multi_gpu_device_selection_and_data_parallel_forward():
    plan = DevicePlan.resolve("cuda", devices="0,1", amp=True)
    model = build_model(plan, hidden_dim=128)
    observation = torch.zeros(8, OBSERVATION_DIM, device=plan.torch_device)
    token = torch.zeros(8, MOTION_TOKEN_DIM, device=plan.torch_device)
    with torch.inference_mode(), plan.autocast():
        mu, value, log_std = model(observation, token)
    assert isinstance(model, torch.nn.DataParallel)
    assert mu.shape == (8, ACTION_DIM)
    assert value.shape == (8,)
    assert log_std.shape == (8, ACTION_DIM)
