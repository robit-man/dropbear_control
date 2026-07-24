"""Export and numerically verify the Dropbear SONIC contract as ONNX.

The exporter always computes a Torch reference.  It then validates with
ONNX Runtime when available (CUDA provider preferred, CPU provider acceptable
for numerical export checking).  Runtime deployment remains CUDA-first and
falls back to the Torch CUDA checkpoint when ONNX Runtime CUDA is unavailable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch
from torch import nn

from .sonic_core import (
    MOTION_TOKEN_DIM,
    OBSERVATION_DIM,
    DevicePlan,
    load_checkpoint,
    sha256_file,
    write_json_atomic,
)


class SonicDeterministicPolicy(nn.Module):
    """ONNX-safe deterministic actor wrapper."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(
        self,
        observation: torch.Tensor,
        motion_token: torch.Tensor,
    ) -> torch.Tensor:
        mu, _, _ = self.model(observation, motion_token)
        return torch.tanh(mu.float())


def _onnx_runtime_validation(
    path: Path,
    observation: np.ndarray,
    motion_token: np.ndarray,
    expected: np.ndarray,
    *,
    prefer_cuda: bool,
) -> Dict[str, Any]:
    try:
        import onnxruntime as ort
    except ImportError:
        return {
            "backend": "torch-fallback",
            "reason": "onnxruntime is not installed",
            "validated": True,
            "max_abs_error": 0.0,
        }
    available = ort.get_available_providers()
    if prefer_cuda and "CUDAExecutionProvider" in available:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    elif "CPUExecutionProvider" in available:
        providers = ["CPUExecutionProvider"]
    else:
        return {
            "backend": "torch-fallback",
            "reason": f"no usable ONNX Runtime provider in {available}",
            "validated": True,
            "max_abs_error": 0.0,
        }
    session = ort.InferenceSession(str(path), providers=providers)
    actual = session.run(
        ["motor_residual"],
        {
            "observation": observation,
            "motion_token": motion_token,
        },
    )[0]
    maximum_error = float(np.max(np.abs(actual - expected)))
    if not np.isfinite(actual).all() or maximum_error > 2e-4:
        raise RuntimeError(
            f"ONNX numerical validation failed; max_abs_error={maximum_error}"
        )
    return {
        "backend": "onnxruntime",
        "providers": session.get_providers(),
        "validated": True,
        "max_abs_error": maximum_error,
    }


def export_sonic_onnx(
    checkpoint: Path,
    output: Path,
    plan: DevicePlan,
    *,
    opset: int = 18,
    batch_size: int = 4,
) -> Dict[str, Any]:
    """Export a deterministic action graph and validate it against Torch."""

    try:
        import onnx
    except ImportError as error:
        raise RuntimeError(
            "ONNX export requires the `onnx` package; install onnx>=1.16"
        ) from error
    model, payload = load_checkpoint(checkpoint, plan)
    wrapper = SonicDeterministicPolicy(model).to(plan.torch_device).eval()
    generator = torch.Generator(device="cpu").manual_seed(193)
    observation_cpu = torch.randn(
        batch_size,
        OBSERVATION_DIM,
        generator=generator,
    )
    token_cpu = torch.randn(
        batch_size,
        MOTION_TOKEN_DIM,
        generator=generator,
    )
    observation = observation_cpu.to(plan.torch_device)
    token = token_cpu.to(plan.torch_device)
    # The ONNX graph is exported in fp32; compare against the same precision.
    with torch.inference_mode():
        expected = wrapper(observation, token).float().cpu().numpy()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.onnx.export(
        wrapper,
        (observation, token),
        temporary,
        export_params=True,
        opset_version=int(opset),
        do_constant_folding=True,
        input_names=["observation", "motion_token"],
        output_names=["motor_residual"],
        dynamic_axes={
            "observation": {0: "batch"},
            "motion_token": {0: "batch"},
            "motor_residual": {0: "batch"},
        },
        dynamo=False,
    )
    onnx_model = onnx.load(str(temporary))
    onnx.checker.check_model(onnx_model)
    temporary.replace(output)
    runtime = _onnx_runtime_validation(
        output,
        observation_cpu.numpy(),
        token_cpu.numpy(),
        expected,
        prefer_cuda=plan.torch_device.type == "cuda",
    )
    result = {
        "schema": "dropbear-sonic-onnx-export-v1",
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
        "onnx": str(output),
        "onnx_sha256": sha256_file(output),
        "opset": int(opset),
        "contract": payload["contract"],
        "device": plan.as_manifest(),
        "validation": runtime,
    }
    write_json_atomic(output.with_suffix(output.suffix + ".json"), result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Dropbear SONIC ONNX")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--opset", type=int, default=18)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--devices", default="")
    parser.add_argument("--allow-cpu", action="store_true")
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
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        plan = DevicePlan.resolve(
            args.device,
            devices=args.devices,
            allow_cpu=args.allow_cpu,
            amp=args.amp,
            amp_dtype=args.amp_dtype,
        )
        result = export_sonic_onnx(
            Path(args.checkpoint),
            Path(args.out),
            plan,
            opset=args.opset,
            batch_size=args.batch_size,
        )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            f"exported {result['onnx']} "
            f"validation={result['validation']['backend']} "
            f"error={result['validation']['max_abs_error']:.3e}"
        )


if __name__ == "__main__":
    main()
