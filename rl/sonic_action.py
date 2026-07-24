"""Versioned post-processing for the local CUDA residual-policy artifact."""

from __future__ import annotations

import math
import time
from typing import Any, Sequence

from .dropbear_ppo import (
    ACTION_NAMES,
    LOCAL_POLICY_ACTION_SCALE,
    LOCAL_POLICY_RESIDUAL_GAIN,
)


LOCAL_ACTION_SEMANTICS = "dropbear-local-reference-residual-v1"
LOCAL_RESIDUAL_SCALE_RAD = tuple(
    value * LOCAL_POLICY_RESIDUAL_GAIN
    for value in LOCAL_POLICY_ACTION_SCALE
)


def _finite_vector(
    value: Sequence[float],
    label: str,
) -> tuple[float, ...]:
    result = tuple(float(item) for item in value)
    if len(result) != len(ACTION_NAMES):
        raise ValueError(
            f"{label} must contain exactly {len(ACTION_NAMES)} values"
        )
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite values")
    return result


def residual_to_reference(
    residual: Sequence[float],
    authored_reference_rad: Sequence[float],
) -> tuple[float, ...]:
    """Apply the exact local teaching-plant action formula.

    Zero residual reproduces the supplied time-varying authored reference.
    This is intentionally different from the fixed-center upstream SONIC
    embodiment formula.
    """

    action = _finite_vector(residual, "residual")
    reference = _finite_vector(
        authored_reference_rad,
        "authored_reference_rad",
    )
    target = [
        base
        + max(-1.0, min(1.0, offset)) * scale
        for base, offset, scale in zip(
            reference,
            action,
            LOCAL_RESIDUAL_SCALE_RAD,
        )
    ]
    target[4] = max(0.0, min(math.pi, target[4]))
    target[7] = max(0.0, min(math.pi, target[7]))
    return tuple(target)


def reference_payload(
    residual: Sequence[float],
    authored_reference_rad: Sequence[float],
    *,
    session_id: str,
    sequence: int,
    source_token_sequence: int | None = None,
    generated_steady_time_ns: int | None = None,
) -> dict[str, Any]:
    """Create the exact JSON frame accepted by the SIL WBC guard."""

    if not session_id:
        raise ValueError("session_id is required")
    if int(sequence) < 0:
        raise ValueError("sequence must be non-negative")
    payload: dict[str, Any] = {
        "schema": "dropbear-wbc-reference-v1",
        "session_id": session_id,
        "sequence": int(sequence),
        "generated_steady_time_ns": (
            time.monotonic_ns()
            if generated_steady_time_ns is None
            else int(generated_steady_time_ns)
        ),
        "joint_names": list(ACTION_NAMES),
        "positions": list(
            residual_to_reference(residual, authored_reference_rad)
        ),
        "action_semantics": LOCAL_ACTION_SEMANTICS,
    }
    if source_token_sequence is not None:
        payload["source_token_sequence"] = int(source_token_sequence)
    return payload


def action_contract() -> dict[str, Any]:
    return {
        "schema": LOCAL_ACTION_SEMANTICS,
        "output": "normalized residual in [-1, 1]",
        "formula": (
            "target_rad = authored_reference_rad + "
            "clamp(residual,-1,1) * scale_rad"
        ),
        "joint_order": list(ACTION_NAMES),
        "scale_rad": list(LOCAL_RESIDUAL_SCALE_RAD),
        "knee_indices": [4, 7],
        "knee_limit_rad": [0.0, math.pi],
        "reference_required": True,
    }
