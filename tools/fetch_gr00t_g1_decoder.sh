#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_root="${project_root}/references/GR00T-WholeBodyControl"
runtime_python="${project_root}/.gr00t-venv/bin/python"
lock_file="${project_root}/integrations/gr00t_wbc/UPSTREAM_LOCK.json"

if [[ ! -x "${runtime_python}" ]]; then
  echo "GR00T runtime is missing; run tools/setup_gr00t_runtime.sh first" >&2
  exit 2
fi
if [[ ! -d "${upstream_root}/.git" ]]; then
  "${project_root}/tools/bootstrap_gr00t_wbc.sh"
fi

readarray -t decoder_lock < <(
  "${runtime_python}" - "${lock_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    decoder = json.load(stream)["releasedG1ShadowDecoder"]
print(decoder["modelPath"])
print(decoder["sha256"])
print(decoder["input"]["name"])
print(",".join(str(value) for value in decoder["input"]["shape"]))
print(decoder["output"]["name"])
print(",".join(str(value) for value in decoder["output"]["shape"]))
PY
)

model_relative="${decoder_lock[0]}"
expected_sha256="${decoder_lock[1]}"
expected_input_name="${decoder_lock[2]}"
expected_input_shape="${decoder_lock[3]}"
expected_output_name="${decoder_lock[4]}"
expected_output_shape="${decoder_lock[5]}"
model_path="${upstream_root}/${model_relative}"

"${runtime_python}" "${upstream_root}/download_from_hf.py" \
  --output-dir "${upstream_root}/gear_sonic_deploy" \
  --no-planner

resolved_sha256="$(sha256sum "${model_path}" | cut -d' ' -f1)"
if [[ "${resolved_sha256}" != "${expected_sha256}" ]]; then
  echo "Released G1 SONIC decoder SHA-256 mismatch" >&2
  echo "  expected: ${expected_sha256}" >&2
  echo "  resolved: ${resolved_sha256}" >&2
  exit 3
fi

"${runtime_python}" - \
  "${model_path}" \
  "${expected_input_name}" \
  "${expected_input_shape}" \
  "${expected_output_name}" \
  "${expected_output_shape}" <<'PY'
import onnx
import sys

path, input_name, input_shape, output_name, output_shape = sys.argv[1:]
model = onnx.load(path, load_external_data=False)
graph = model.graph
if len(graph.input) != 1 or len(graph.output) != 1:
    raise SystemExit("released decoder must have exactly one input and output")

def shape(value_info):
    return ",".join(
        str(dimension.dim_value)
        for dimension in value_info.type.tensor_type.shape.dim
    )

if graph.input[0].name != input_name or shape(graph.input[0]) != input_shape:
    raise SystemExit(
        f"decoder input mismatch: {graph.input[0].name} {shape(graph.input[0])}"
    )
if graph.output[0].name != output_name or shape(graph.output[0]) != output_shape:
    raise SystemExit(
        f"decoder output mismatch: {graph.output[0].name} {shape(graph.output[0])}"
    )
print(f"Verified released G1 SONIC decoder: {path}")
PY

echo "  sha256: ${resolved_sha256}"
echo "  role: preview/retarget teacher only; never a hardware command"
