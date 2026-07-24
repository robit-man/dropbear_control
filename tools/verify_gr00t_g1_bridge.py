#!/usr/bin/env python3
"""Run the released G1 token through the complete Dropbear USD pose bridge.

This is a CUDA/geometry smoke test, not a physics or hardware admission.  It
uses NVIDIA's pinned standing-token fixture directly from the pinned upstream
checkout, executes the digest-verified released G1 decoder, and retargets the
result against the retained Dropbear USD articulation and passive loops.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_INITIAL_POSES = (
    PROJECT_ROOT
    / "references"
    / "GR00T-WholeBodyControl"
    / "gear_sonic"
    / "utils"
    / "inference"
    / "initial_poses.py"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="CUDA device index used by ONNX Runtime (default: 0)",
    )
    parser.add_argument(
        "--refinement-iterations",
        type=int,
        choices=range(0, 3),
        default=1,
        help="bounded Dropbear task-space DLS iterations (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON report path; stdout is always populated",
    )
    return parser.parse_args()


def _published_initial_token() -> list[float]:
    if not UPSTREAM_INITIAL_POSES.is_file():
        raise RuntimeError(
            "pinned upstream source is absent; run tools/bootstrap_gr00t_wbc.sh"
        )
    namespace = runpy.run_path(str(UPSTREAM_INITIAL_POSES))
    raw = namespace.get("LATENT_INITIAL_MOTION_TOKEN")
    if raw is None:
        raise RuntimeError("upstream LATENT_INITIAL_MOTION_TOKEN is absent")
    if hasattr(raw, "detach"):
        raw = raw.detach()
    if hasattr(raw, "cpu"):
        raw = raw.cpu()
    if hasattr(raw, "numpy"):
        raw = raw.numpy()
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    while isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
        raw = raw[0]
    token = [float(value) for value in raw]
    if len(token) != 64:
        raise RuntimeError(
            f"upstream standing token has {len(token)} values, expected 64"
        )
    return token


def _main() -> int:
    arguments = _arguments()
    sys.path.insert(0, str(PROJECT_ROOT))

    from integrations.gr00t_wbc.g1_shadow_decoder import G1ShadowDecoder
    from integrations.gr00t_wbc.usd_retarget import G1UsdDropbearRetargeter

    token = _published_initial_token()
    decoder_started = time.perf_counter()
    decoder = G1ShadowDecoder(PROJECT_ROOT, device_id=arguments.device)
    decoder_initialization_seconds = time.perf_counter() - decoder_started
    status = decoder.status_payload()
    if not decoder.available:
        raise RuntimeError(
            "released G1 decoder is unavailable: "
            f"{status.get('availabilityReason')}"
        )

    decode_started = time.perf_counter()
    g1_positions = decoder.decode_token(token, sequence=0)
    decode_seconds = time.perf_counter() - decode_started
    status = decoder.status_payload()

    retargeter = G1UsdDropbearRetargeter(PROJECT_ROOT)
    retarget_started = time.perf_counter()
    result = retargeter.retarget_g1_pose(
        g1_positions,
        refinement_iterations=arguments.refinement_iterations,
    )
    retarget_seconds = time.perf_counter() - retarget_started
    body_errors = {
        row.target: row.position_error_m
        for row in result.diagnostics.body_targets
    }
    maximum_body_error = max(body_errors.values())
    closure_residual = result.diagnostics.maximum_closure_residual_m
    checks = {
        "cudaDecoderAvailable": decoder.available,
        "cudaPrimaryProvider": (
            status["runtime"]["providers"][0] == "CUDAExecutionProvider"
        ),
        "g1OutputHas29FiniteValues": (
            len(g1_positions) == 29
            and all(
                isinstance(value, float)
                and value == value
                and abs(value) != float("inf")
                for value in g1_positions
            )
        ),
        "dropbearOutputHas22Values": len(result.joint_positions_rad) == 22,
        "taskResidualDidNotRegress": result.diagnostics.improved,
        "maximumClosureResidualBelow1mm": closure_residual < 0.001,
        "maximumPreviewBodyErrorBelow15cm": maximum_body_error < 0.15,
        "hardwareAuthorityDenied": (
            result.as_payload().get("hardwareAuthorized") is False
        ),
    }
    report: dict[str, Any] = {
        "schema": "dropbear-g1-usd-bridge-smoke-v1",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(checks.values()) else "failed",
        "role": "preview-and-retarget-teacher-only",
        "hardwareAuthorized": False,
        "contactDynamicsAuthoritative": False,
        "decoder": status,
        "timingSeconds": {
            "decoderInitialization": decoder_initialization_seconds,
            "oneTokenDecode": decode_seconds,
            "dropbearRetarget": retarget_seconds,
        },
        "source": {
            "fixture": "LATENT_INITIAL_MOTION_TOKEN",
            "tokenDimension": len(token),
            "decodedG1JointCount": len(g1_positions),
        },
        "target": {
            "dropbearMotorCount": len(result.joint_positions_rad),
            "seedTaskError": result.diagnostics.seed_task_error,
            "finalTaskError": result.diagnostics.final_task_error,
            "iterationsAccepted": result.diagnostics.iterations_accepted,
            "maximumClosureResidualM": closure_residual,
            "maximumBodyPositionErrorM": maximum_body_error,
            "bodyPositionErrorsM": body_errors,
        },
        "checks": checks,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        output = arguments.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
