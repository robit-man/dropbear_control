"""Normalized upstream SONIC action to Dropbear motor-coordinate radians."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

from .embodiment import ACTION_NAMES


UPSTREAM_ACTION_SEMANTICS = "dropbear-upstream-fixed-center-residual-v1"


class UpstreamSonicActionAdapter:
    """Implement the exact action formula in the embodiment contract.

    This adapter is for a future upstream 784-input SONIC checkpoint. It must
    not be used with the local teaching-plant checkpoint, whose residual is
    defined around a time-varying authored reference.
    """

    def __init__(self, project_root: Path | None = None):
        root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        path = (
            root
            / "integrations"
            / "gr00t_wbc"
            / "config"
            / "dropbear_embodiment.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        actions = payload.get("actions")
        if (
            not isinstance(actions, list)
            or tuple(item.get("name") for item in actions) != ACTION_NAMES
        ):
            raise ValueError("embodiment actions do not match canonical order")
        self.centers = tuple(float(item["centerRad"]) for item in actions)
        self.scales = tuple(float(item["scaleRad"]) for item in actions)
        self.limits = tuple(
            (float(item["positionLimitRad"][0]), float(item["positionLimitRad"][1]))
            for item in actions
        )

    def decode(self, action: Sequence[float]) -> tuple[float, ...]:
        values = tuple(float(item) for item in action)
        if len(values) != len(ACTION_NAMES):
            raise ValueError(f"action must contain {len(ACTION_NAMES)} values")
        if not all(math.isfinite(item) for item in values):
            raise ValueError("action must contain finite values")
        targets = []
        for value, center, scale, limits in zip(
            values,
            self.centers,
            self.scales,
            self.limits,
        ):
            residual = max(-1.0, min(1.0, value))
            targets.append(
                max(limits[0], min(limits[1], center + residual * scale))
            )
        return tuple(targets)

    def contract(self) -> dict[str, Any]:
        return {
            "schema": UPSTREAM_ACTION_SEMANTICS,
            "source": (
                "integrations/gr00t_wbc/config/"
                "dropbear_embodiment.json"
            ),
            "formula": (
                "target_rad = center_rad + clamp(action,-1,1) * scale_rad"
            ),
            "joint_order": list(ACTION_NAMES),
            "center_rad": list(self.centers),
            "scale_rad": list(self.scales),
            "position_limit_rad": [list(value) for value in self.limits],
        }
