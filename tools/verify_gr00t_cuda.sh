#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_python="${project_root}/.gr00t-venv/bin/python"
cuda_devices="${DROPBEAR_CUDA_DEVICES:-0}"
session_id="${DROPBEAR_VERIFY_SESSION:-cuda-verified-$(date -u +%Y%m%dT%H%M%SZ)}"

if [[ ! -x "${runtime_python}" ]]; then
  echo "Run tools/setup_gr00t_runtime.sh first." >&2
  exit 2
fi

cd "${project_root}"
"${runtime_python}" -m rl.sonic_smoke \
  --output-dir artifacts/rl/sonic-smoke \
  --session-id "${session_id}" \
  --device cuda \
  --devices "${cuda_devices}" \
  --amp \
  --amp-dtype bfloat16 \
  --updates 1 \
  --rollout-steps 16 \
  --environments 128 \
  --ppo-epochs 1 \
  --batch-size 2048 \
  --require-onnx-cuda \
  --tensorrt \
  --tensorrt-fp16

report_path="artifacts/rl/sonic-smoke/${session_id}/smoke-report.json"
"${runtime_python}" - "${report_path}" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
report = json.loads(path.read_text(encoding="utf-8"))
if report.get("schema") != "dropbear-sonic-cuda-smoke-v1":
    raise SystemExit("verification report schema mismatch")
if report.get("status") != "passed":
    raise SystemExit("verification report did not pass")
device = report.get("device", {})
if device.get("allow_cpu") is not False or not str(
    device.get("primary", "")
).startswith("cuda:"):
    raise SystemExit("verification was not CUDA-only")
onnx = report.get("onnx", {})
validation = onnx.get("validation", {})
if (
    validation.get("validated") is not True
    or "CUDAExecutionProvider" not in validation.get("providers", [])
):
    raise SystemExit("ONNX Runtime CUDA numerical verification did not pass")
tensorrt = report.get("tensorrt", {})
if tensorrt.get("status") != "passed":
    raise SystemExit("TensorRT build and numerical verification did not pass")
if len(str(tensorrt.get("engine_sha256", ""))) != 64:
    raise SystemExit("TensorRT engine is not hash-bound")
for backend in ("torch", "onnxruntime"):
    admission = report.get("runtime", {}).get(backend, {}).get(
        "artifact_admission",
        {},
    )
    if len(str(admission.get("checkpoint_sha256", ""))) != 64:
        raise SystemExit(f"{backend} runtime checkpoint admission is missing")
print(f"CUDA, ONNX Runtime CUDA, and TensorRT admission passed: {path}")
PY

echo "Verified report: ${report_path}"
