"""Export and verify a local Dropbear residual-policy deployment bundle.

The bundle is deliberately named a residual engine: it does not contain
NVIDIA SONIC weights, a gait reference generator, or an Isaac/PhysX plant.
Absolute motor-coordinate references require the versioned post-processing
contract recorded alongside the checkpoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .sonic_core import DevicePlan, write_json_atomic
from .sonic_export import export_sonic_onnx
from .sonic_runtime import SafetyEnvelope, SonicRuntime, verify_runtime
from .sonic_tensorrt import build_and_verify_tensorrt


def deploy_sonic(
    checkpoint: Path,
    plan: DevicePlan,
    *,
    require_tensorrt: bool = True,
    tensorrt_fp16: bool = True,
) -> Dict[str, Any]:
    """Build and numerically verify the CUDA residual-policy artifacts."""

    checkpoint = Path(checkpoint)
    if not checkpoint.is_file():
        raise ValueError(f"checkpoint does not exist: {checkpoint}")
    directory = checkpoint.parent
    onnx_path = directory / "sonic_policy.onnx"
    export = export_sonic_onnx(
        checkpoint,
        onnx_path,
        plan,
        batch_size=8,
    )
    providers = export.get("validation", {}).get("providers", [])
    if (
        plan.torch_device.type == "cuda"
        and "CUDAExecutionProvider" not in providers
    ):
        raise RuntimeError(
            "deployment requires ONNX Runtime CUDA numerical verification"
        )
    torch_runtime = SonicRuntime(
        checkpoint,
        plan,
        onnx_path=onnx_path,
        backend="torch",
        safety=SafetyEnvelope(),
    )
    onnx_runtime = SonicRuntime(
        checkpoint,
        plan,
        onnx_path=onnx_path,
        backend="onnx",
        safety=SafetyEnvelope(),
    )
    runtime = {
        "torch": verify_runtime(torch_runtime),
        "onnxruntime": verify_runtime(onnx_runtime),
    }
    tensorrt = build_and_verify_tensorrt(
        onnx_path,
        directory / "sonic_policy.engine",
        checkpoint,
        plan,
        fp16=tensorrt_fp16,
    )
    if require_tensorrt and tensorrt.get("status") != "passed":
        raise RuntimeError(
            "TensorRT 10.13 engine build and numeric verification are required"
        )
    report = {
        "schema": "dropbear-sonic-residual-deployment-v1",
        "status": "passed",
        "artifactSemantics": (
            "normalized residual; absolute target requires "
            "dropbear-local-reference-residual-v1 post-processing"
        ),
        "device": plan.as_manifest(),
        "onnx": export,
        "runtime": runtime,
        "tensorrt": tensorrt,
    }
    report_path = directory / "deployment-report.json"
    report["report_path"] = str(report_path)
    write_json_atomic(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy-verify a Dropbear CUDA residual policy",
    )
    parser.add_argument("--checkpoint", required=True)
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
    parser.add_argument(
        "--require-tensorrt",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--tensorrt-fp16",
        action=argparse.BooleanOptionalAction,
        default=True,
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
        report = deploy_sonic(
            Path(args.checkpoint),
            plan,
            require_tensorrt=args.require_tensorrt,
            tensorrt_fp16=args.tensorrt_fp16,
        )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    else:
        print(
            f"verified residual deployment {report['report_path']} "
            f"TensorRT={report['tensorrt']['status']}"
        )


if __name__ == "__main__":
    main()
