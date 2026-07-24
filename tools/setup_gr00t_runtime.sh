#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${project_root}/.gr00t-venv"
python_bin="${PYTHON_BIN:-python3}"

if [[ ! -x "${runtime_dir}/bin/python" ]]; then
  "${python_bin}" -m venv --system-site-packages "${runtime_dir}"
fi

"${runtime_dir}/bin/python" -m pip install \
  --disable-pip-version-check \
  -r "${project_root}/requirements-gr00t-runtime-lock.txt"

"${runtime_dir}/bin/python" - <<'PY'
import json

import onnx
import onnxruntime
import tensorrt
import torch
import zmq

payload = {
    "torch": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "cuda_runtime": torch.version.cuda,
    "cuda_devices": [
        {
            "index": index,
            "name": torch.cuda.get_device_name(index),
            "capability": list(torch.cuda.get_device_capability(index)),
        }
        for index in range(torch.cuda.device_count())
    ],
    "onnx": onnx.__version__,
    "onnxruntime": onnxruntime.__version__,
    "onnx_providers": onnxruntime.get_available_providers(),
    "tensorrt": tensorrt.__version__,
    "pyzmq": zmq.__version__,
}
print(json.dumps(payload, indent=2))
if not payload["cuda_available"]:
    raise SystemExit("CUDA is required for the GR00T compatibility runtime")
if "CUDAExecutionProvider" not in payload["onnx_providers"]:
    raise SystemExit("ONNX Runtime CUDAExecutionProvider is unavailable")
if not payload["tensorrt"].startswith("10.13"):
    raise SystemExit("TensorRT 10.13.x is required by the x86_64 runtime lock")
PY
