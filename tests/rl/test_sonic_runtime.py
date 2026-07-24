import json
import shutil

import numpy as np
import pytest
import torch

from rl.sonic_core import ACTION_DIM, DevicePlan
from rl.sonic_export import export_sonic_onnx
from rl.sonic_runtime import SafetyEnvelope, SonicRuntime, verify_runtime
from rl.sonic_train import SonicTrainConfig, train_sonic


def test_safety_envelope_clamps_slew_and_rejects_stale_frames():
    clock_value = [10.0]
    safety = SafetyEnvelope(
        maximum_delta=0.05,
        stale_after_seconds=0.1,
        clock=lambda: clock_value[0],
    )
    action, accepted, reason = safety.guard(
        np.full(ACTION_DIM, 4.0, dtype=np.float32),
        sequence=1,
        timestamp=10.0,
    )
    assert accepted
    assert reason == "accepted-absolute-clamp"
    assert torch.allclose(action, torch.full((ACTION_DIM,), 0.05))

    clock_value[0] = 10.2
    action, accepted, reason = safety.guard(
        np.ones(ACTION_DIM, dtype=np.float32),
        sequence=2,
        timestamp=10.0,
    )
    assert not accepted
    assert reason == "stale-input-frame"
    assert torch.equal(action, torch.zeros(ACTION_DIM))


def test_safety_envelope_rejects_replay_nonfinite_and_estop():
    safety = SafetyEnvelope(maximum_delta=1.0)
    now = safety.clock()
    _, accepted, _ = safety.guard(
        torch.zeros(ACTION_DIM),
        sequence=4,
        timestamp=now,
        now=now,
    )
    assert accepted
    _, accepted, reason = safety.guard(
        torch.zeros(ACTION_DIM),
        sequence=4,
        timestamp=now,
        now=now,
    )
    assert not accepted
    assert reason == "non-monotonic-sequence"
    _, accepted, reason = safety.guard(
        torch.full((ACTION_DIM,), float("nan")),
        sequence=5,
        timestamp=now,
        now=now,
    )
    assert not accepted
    assert reason == "non-finite-action"
    safety.emergency_stop()
    action, accepted, reason = safety.watchdog(now=now)
    assert not accepted
    assert reason == "emergency-stop"
    assert torch.equal(action, torch.zeros(ACTION_DIM))


def test_safety_envelope_rejects_nonfinite_and_excessively_future_timestamps():
    safety = SafetyEnvelope(
        maximum_delta=1.0,
        maximum_future_skew_seconds=0.02,
    )
    action = torch.zeros(ACTION_DIM)
    _, accepted, reason = safety.guard(
        action,
        sequence=1,
        timestamp=float("nan"),
        now=10.0,
    )
    assert not accepted
    assert reason == "non-finite-timestamp"
    _, accepted, reason = safety.guard(
        action,
        sequence=1,
        timestamp=10.0201,
        now=10.0,
    )
    assert not accepted
    assert reason == "future-input-frame"
    _, accepted, reason = safety.guard(
        action,
        sequence=1,
        timestamp=10.02,
        now=10.0,
    )
    assert accepted
    assert reason == "accepted"
    _, accepted, reason = safety.watchdog(now=float("inf"))
    assert not accepted
    assert reason == "non-finite-clock"


def test_onnx_export_and_cpu_runtime_numerically_validate(tmp_path):
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="runtime",
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
    checkpoint = tmp_path / "runtime" / "sonic_policy.pt"
    onnx_path = tmp_path / "runtime" / "sonic_policy.onnx"
    plan = DevicePlan.resolve("cpu", allow_cpu=True, amp=False)
    exported = export_sonic_onnx(checkpoint, onnx_path, plan, batch_size=2)
    assert exported["validation"]["validated"]
    assert exported["validation"]["max_abs_error"] < 2e-4

    runtime = SonicRuntime(
        checkpoint,
        plan,
        onnx_path=onnx_path,
        backend="onnx",
    )
    verification = verify_runtime(runtime)
    assert verification["validated"]
    assert verification["backend"] == "onnxruntime"
    proof_kinds = {
        proof["kind"]
        for proof in verification["artifact_admission"]["proofs"]
    }
    assert "training-session" in proof_kinds
    assert "onnx-sidecar" in proof_kinds

    sidecar_path = onnx_path.with_suffix(".onnx.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["onnx_sha256"] = "0" * 64
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ValueError, match="ONNX admission artifact sha256 mismatch"):
        SonicRuntime(
            checkpoint,
            plan,
            onnx_path=onnx_path,
            backend="onnx",
        )


def test_pending_deployment_requires_the_hash_bound_onnx_sidecar(tmp_path):
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="pending",
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
    checkpoint = tmp_path / "pending" / "sonic_policy.pt"
    onnx_path = tmp_path / "pending" / "sonic_policy.onnx"
    plan = DevicePlan.resolve("cpu", allow_cpu=True, amp=False)
    with pytest.raises(ValueError, match="hash-bound"):
        SonicRuntime(checkpoint, plan, backend="torch")

    export_sonic_onnx(checkpoint, onnx_path, plan, batch_size=2)
    runtime = SonicRuntime(
        checkpoint,
        plan,
        onnx_path=onnx_path,
        backend="torch",
    )
    proof_kinds = {
        proof["kind"]
        for proof in runtime.artifact_admission["proofs"]
    }
    assert proof_kinds == {"onnx-sidecar"}


def test_runtime_rejects_checkpoint_without_hash_bound_manifest(tmp_path):
    train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="runtime",
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
    standalone = tmp_path / "standalone" / "sonic_policy.pt"
    standalone.parent.mkdir()
    shutil.copyfile(tmp_path / "runtime" / "sonic_policy.pt", standalone)
    plan = DevicePlan.resolve("cpu", allow_cpu=True, amp=False)
    with pytest.raises(ValueError, match="hash-bound"):
        SonicRuntime(standalone, plan, backend="torch")


def test_runtime_rejects_tampered_checkpoint_hash(tmp_path):
    train_sonic(
        SonicTrainConfig(
            output_dir=str(tmp_path),
            session_id="runtime",
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
    checkpoint = tmp_path / "runtime" / "sonic_policy.pt"
    with checkpoint.open("ab") as stream:
        stream.write(b"tampered")
    plan = DevicePlan.resolve("cpu", allow_cpu=True, amp=False)
    with pytest.raises(ValueError, match="sha256 mismatch"):
        SonicRuntime(checkpoint, plan, backend="torch")
