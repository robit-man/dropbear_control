"""Single end-to-end CUDA verification for Dropbear SONIC integration.

The smoke run performs:

1. a tiny token-conditioned PPO training session on CUDA;
2. ONNX export and Torch numerical comparison;
3. ONNX Runtime CUDA execution and numerical comparison;
4. Torch/ONNX safe-runtime watchdog and clamp checks; and
5. TensorRT 10.13 engine build plus CUDA numerical verification when enabled.

CPU requires ``--allow-cpu`` and is intended only for automated unit tests.
The final stdout line and ``smoke-report.json`` contain the complete report.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time
from typing import Any, Dict

from .sonic_core import DevicePlan, write_json_atomic
from .sonic_export import export_sonic_onnx
from .sonic_runtime import SafetyEnvelope, SonicRuntime, verify_runtime
from .sonic_tensorrt import build_and_verify_tensorrt
from .sonic_train import SonicTrainConfig, train_sonic


def _require_passed_tensorrt(report: Dict[str, Any]) -> None:
    if report.get("status") != "passed":
        raise RuntimeError(
            "TensorRT was enabled but build and numerical verification "
            f"did not pass: {report.get('reason', 'unknown reason')}"
        )
    engine_digest = report.get("engine_sha256")
    if (
        not isinstance(engine_digest, str)
        or len(engine_digest) != 64
        or any(character not in "0123456789abcdef" for character in engine_digest)
    ):
        raise RuntimeError("passed TensorRT report has no valid engine sha256")
    maximum_error = report.get("max_abs_error")
    tolerance = report.get("tolerance")
    if (
        isinstance(maximum_error, bool)
        or not isinstance(maximum_error, (int, float))
        or isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(maximum_error))
        or not math.isfinite(float(tolerance))
        or float(tolerance) <= 0.0
        or float(maximum_error) > float(tolerance)
    ):
        raise RuntimeError("passed TensorRT report has invalid numerical evidence")


def run_smoke(
    *,
    output_dir: Path,
    session_id: str = "cuda-smoke",
    device: str = "cuda",
    devices: str = "0",
    allow_cpu: bool = False,
    amp: bool = True,
    amp_dtype: str = "bfloat16",
    updates: int = 1,
    rollout_steps: int = 16,
    environments: int = 128,
    ppo_epochs: int = 1,
    batch_size: int = 2048,
    require_onnx_cuda: bool = True,
    tensorrt: bool = True,
    tensorrt_fp16: bool = True,
) -> Dict[str, Any]:
    started = time.perf_counter()
    plan = DevicePlan.resolve(
        device,
        devices=devices,
        allow_cpu=allow_cpu,
        amp=amp,
        amp_dtype=amp_dtype,
    )
    training = train_sonic(
        SonicTrainConfig(
            output_dir=str(output_dir),
            session_id=session_id,
            device=device,
            devices=devices,
            allow_cpu=allow_cpu,
            amp=amp,
            amp_dtype=amp_dtype,
            updates=updates,
            rollout_steps=rollout_steps,
            environments=environments,
            ppo_epochs=ppo_epochs,
            batch_size=batch_size,
            reference_frames=max(100, rollout_steps * 2),
        ),
        jsonl=False,
    )
    checkpoint = Path(training["checkpoint_path"])
    session_dir = checkpoint.parent
    onnx_path = session_dir / "sonic_policy.onnx"
    exported = export_sonic_onnx(
        checkpoint,
        onnx_path,
        plan,
        batch_size=min(8, max(1, environments)),
    )
    providers = exported["validation"].get("providers", [])
    if (
        require_onnx_cuda
        and plan.torch_device.type == "cuda"
        and "CUDAExecutionProvider" not in providers
    ):
        raise RuntimeError(
            "ONNX Runtime CUDA verification is required but "
            f"providers were {providers}"
        )

    torch_runtime = SonicRuntime(
        checkpoint,
        plan,
        backend="torch",
        safety=SafetyEnvelope(),
    )
    torch_verification = verify_runtime(torch_runtime)
    onnx_runtime = SonicRuntime(
        checkpoint,
        plan,
        onnx_path=onnx_path,
        backend="onnx",
        safety=SafetyEnvelope(),
    )
    onnx_verification = verify_runtime(onnx_runtime)
    if tensorrt:
        tensorrt_report = build_and_verify_tensorrt(
            onnx_path,
            session_dir / "sonic_policy.engine",
            checkpoint,
            plan,
            fp16=tensorrt_fp16,
        )
        _require_passed_tensorrt(tensorrt_report)
    else:
        tensorrt_report = {
            "available": False,
            "status": "skipped",
            "reason": "disabled by CLI",
        }
    report = {
        "schema": "dropbear-sonic-cuda-smoke-v1",
        "status": "passed",
        "session_id": session_id,
        "elapsed_seconds": time.perf_counter() - started,
        "device": plan.as_manifest(),
        "training": {
            "manifest": training["manifest_path"],
            "checkpoint": training["checkpoint_path"],
            "metrics": training["metrics"],
        },
        "onnx": exported,
        "runtime": {
            "torch": torch_verification,
            "onnxruntime": onnx_verification,
        },
        "tensorrt": tensorrt_report,
    }
    report_path = session_dir / "smoke-report.json"
    report["report_path"] = str(report_path)
    write_json_atomic(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train, export and deploy-verify Dropbear SONIC on CUDA",
    )
    parser.add_argument("--output-dir", default="artifacts/rl/sonic-smoke")
    parser.add_argument("--session-id", default="cuda-smoke")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--devices", default="0")
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
    parser.add_argument("--updates", type=int, default=1)
    parser.add_argument("--rollout-steps", type=int, default=16)
    parser.add_argument("--environments", type=int, default=128)
    parser.add_argument("--ppo-epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument(
        "--require-onnx-cuda",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--tensorrt",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--tensorrt-fp16",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        report = run_smoke(
            output_dir=Path(args.output_dir),
            session_id=args.session_id,
            device=args.device,
            devices=args.devices,
            allow_cpu=args.allow_cpu,
            amp=args.amp,
            amp_dtype=args.amp_dtype,
            updates=args.updates,
            rollout_steps=args.rollout_steps,
            environments=args.environments,
            ppo_epochs=args.ppo_epochs,
            batch_size=args.batch_size,
            require_onnx_cuda=args.require_onnx_cuda,
            tensorrt=args.tensorrt,
            tensorrt_fp16=args.tensorrt_fp16,
        )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
