import json

import pytest
import torch

from rl.sonic_smoke import _require_passed_tensorrt, run_smoke


def test_tensorrt_admission_is_fail_closed():
    _require_passed_tensorrt(
        {
            "status": "passed",
            "engine_sha256": "a" * 64,
            "max_abs_error": 1e-5,
            "tolerance": 1e-3,
        }
    )
    with pytest.raises(RuntimeError, match="did not pass"):
        _require_passed_tensorrt(
            {
                "status": "skipped",
                "reason": "TensorRT unavailable",
            }
        )


def test_end_to_end_cpu_smoke_is_explicitly_test_only(tmp_path):
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    report = run_smoke(
        output_dir=tmp_path,
        session_id="cpu-smoke",
        device="cpu",
        devices="",
        allow_cpu=True,
        amp=False,
        updates=1,
        rollout_steps=2,
        environments=2,
        ppo_epochs=1,
        batch_size=4,
        require_onnx_cuda=False,
        tensorrt=False,
    )
    persisted = json.loads(
        (tmp_path / "cpu-smoke" / "smoke-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "passed"
    assert persisted["schema"] == "dropbear-sonic-cuda-smoke-v1"
    assert persisted["device"]["allow_cpu"] is True
    assert persisted["runtime"]["torch"]["validated"]
    assert persisted["runtime"]["onnxruntime"]["validated"]


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA unavailable")
def test_quick_cuda_training_export_and_onnxruntime(tmp_path):
    pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.skip("ONNX Runtime CUDA provider unavailable")
    report = run_smoke(
        output_dir=tmp_path,
        session_id="cuda-smoke",
        device="cuda",
        devices="0",
        amp=True,
        updates=1,
        rollout_steps=2,
        environments=8,
        ppo_epochs=1,
        batch_size=16,
        require_onnx_cuda=True,
        tensorrt=False,
    )
    assert report["status"] == "passed"
    assert report["device"]["primary"] == "cuda:0"
    assert "CUDAExecutionProvider" in report["onnx"]["validation"]["providers"]
