"""Reduced-coordinate adapter for Dropbear's retained closed linkages.

PhysX remains authoritative for the complete 93-body passive-joint solution.
This module performs the safe, testable portion needed at the policy boundary:

* map the 22 motor coordinates to their authored USD joints;
* expose exact motor/passive/constraint topology from the articulation;
* project the validated knee and elbow reduced outputs used by local policy
  references; and
* report domain and closure residuals without pretending to solve every
  passive body transform outside PhysX.
"""

from __future__ import annotations

from dataclasses import dataclass
import bisect
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .embodiment import (
    ACTION_COUNT,
    ACTION_NAMES,
    CONTRACT,
    EmbodimentContractError,
    find_project_root,
)
from .order_converter import DropbearOrderConverter


@dataclass(frozen=True)
class LinkageProjection:
    side: str
    linkage: str
    input_motor_rad: float
    output_angle_rad: float
    residual_m: float
    in_validated_domain: bool


@dataclass(frozen=True)
class ClosureProjection:
    usd_motor_positions: Mapping[str, float]
    linkage_outputs: tuple[LinkageProjection, ...]
    maximum_residual_m: float
    all_in_validated_domain: bool


@dataclass(frozen=True)
class _FourBarGeometry:
    ground: float = 0.105
    input_link: float = 0.075
    coupler: float = 0.145
    output_link: float = 0.115
    motor_offset: float = -0.18


class DropbearClosureAdapter:
    """Closure-aware adapter over the canonical 22-motor policy surface."""

    ELBOW_MOTOR_SAMPLES = (
        -1.0471976,
        -0.7853982,
        -0.5235988,
        -0.2617994,
        0.0,
        0.2617994,
        0.5235988,
        0.7853982,
        1.0471976,
        1.3089969,
    )
    ELBOW_OUTPUT_SAMPLES = (
        -0.1813566,
        -0.1439713,
        -0.1020135,
        -0.0546698,
        0.0,
        0.0651861,
        0.1455621,
        0.2471768,
        0.3747834,
        0.5180507,
    )

    def __init__(self, project_root: Path | None = None) -> None:
        root = (project_root or find_project_root()).resolve()
        path = root / "web/assets/robot/dropbear-articulation.json"
        self.articulation = json.loads(path.read_text(encoding="utf-8"))
        self.converter = DropbearOrderConverter()
        self.geometry = _FourBarGeometry()
        self._topology = self._read_topology()

    @property
    def full_passive_projection_supported(self) -> bool:
        """Full passive poses must be obtained from the PhysX articulation."""

        return False

    @property
    def topology(self) -> Mapping[str, Any]:
        return self._topology

    def _read_topology(self) -> dict[str, Any]:
        browser = self.articulation["browserKinematics"]
        arms: dict[str, Any] = {}
        for row in browser["armLinkages"]:
            arms[row["side"]] = {
                "motor": row["elbowMotor"],
                "passiveJoints": tuple(row["passiveJoints"]),
                "closureConstraints": tuple(row["closureConstraints"]),
                "output": row["wristOutput"],
            }
        legs: dict[str, Any] = {}
        for row in browser["calfLinkages"]:
            legs[row["side"]] = {
                "motorCranks": (
                    row["outer"]["motorCrank"],
                    row["inner"]["motorCrank"],
                ),
                "passiveJoints": (
                    row["outer"]["rodPivot"],
                    row["inner"]["rodPivot"],
                    row["footPivot"],
                ),
                "closureConstraints": (
                    row["outer"]["ankleClosure"],
                    row["inner"]["ankleClosure"],
                ),
            }
        return {
            "arms": arms,
            "legs": legs,
            "fullPassiveProjectionAuthority": "Isaac/PhysX",
        }

    @staticmethod
    def _finite_motor_vector(values: Sequence[float]) -> tuple[float, ...]:
        if len(values) != ACTION_COUNT:
            raise EmbodimentContractError(
                f"motor vector has {len(values)} values, expected {ACTION_COUNT}"
            )
        result = tuple(float(value) for value in values)
        if not all(math.isfinite(value) for value in result):
            raise EmbodimentContractError("motor vector contains non-finite values")
        for value, action in zip(result, CONTRACT["actions"]):
            lower, upper = action["positionLimitRad"]
            if value < lower or value > upper:
                raise EmbodimentContractError(
                    f"{action['name']}={value:.6f} exceeds [{lower:.6f}, {upper:.6f}]"
                )
        return result

    def motor_to_usd(self, values: Sequence[float]) -> dict[str, float]:
        motor = self._finite_motor_vector(values)
        return dict(
            zip(
                self.converter.names("usd"),
                self.converter.convert_vector(motor, "policy", "usd"),
            )
        )

    def usd_to_motor(self, values: Mapping[str, float]) -> list[float]:
        converted = self.converter.convert_mapping(values, "usd", "policy")
        return list(
            self._finite_motor_vector(
                [converted[name] for name in ACTION_NAMES]
            )
        )

    def _project_leg(
        self, side: str, hip_pitch: float, knee_motor: float
    ) -> LinkageProjection:
        g = self.geometry
        theta = hip_pitch + g.motor_offset
        ax, ay = g.input_link * math.cos(theta), g.input_link * math.sin(theta)
        bx = g.ground + g.output_link * math.cos(knee_motor)
        by = g.output_link * math.sin(knee_motor)
        dx, dy = bx - ax, by - ay
        distance = math.sqrt(dx * dx + dy * dy + 1e-12)
        denominator = 2.0 * g.coupler * distance
        cos_alpha_raw = (
            g.coupler * g.coupler
            + distance * distance
            - g.output_link * g.output_link
        ) / max(denominator, 1e-12)
        reachable = -1.0 <= cos_alpha_raw <= 1.0
        cos_alpha = max(-1.0, min(1.0, cos_alpha_raw))
        alpha = math.atan2(dy, dx)
        coupler_angle = alpha + math.acos(cos_alpha)
        cx = ax + g.coupler * math.cos(coupler_angle)
        cy = ay + g.coupler * math.sin(coupler_angle)
        residual = abs(math.hypot(cx - bx, cy - by) - g.output_link)
        output = math.atan2(cy - ay, cx - ax) - theta
        return LinkageProjection(
            side=side,
            linkage="knee_four_bar_reduced",
            input_motor_rad=knee_motor,
            output_angle_rad=output,
            residual_m=residual,
            in_validated_domain=reachable and 0.0 <= knee_motor <= math.pi,
        )

    def _project_elbow(
        self, side: str, motor_angle: float
    ) -> LinkageProjection:
        samples = self.ELBOW_MOTOR_SAMPLES
        outputs = self.ELBOW_OUTPUT_SAMPLES
        clamped = max(samples[0], min(samples[-1], motor_angle))
        upper = max(1, min(len(samples) - 1, bisect.bisect_left(samples, clamped)))
        lower = upper - 1
        blend = (clamped - samples[lower]) / (samples[upper] - samples[lower])
        output = outputs[lower] + blend * (outputs[upper] - outputs[lower])
        overrun = max(0.0, samples[0] - motor_angle) + max(
            0.0, motor_angle - samples[-1]
        )
        return LinkageProjection(
            side=side,
            linkage="elbow_usd_sampled_reduced",
            input_motor_rad=motor_angle,
            output_angle_rad=output,
            residual_m=overrun * 0.04,
            in_validated_domain=samples[0] <= motor_angle <= samples[-1],
        )

    def project(self, values: Sequence[float]) -> ClosureProjection:
        motor = self._finite_motor_vector(values)
        outputs = (
            self._project_leg("left", motor[5], motor[4]),
            self._project_leg("right", motor[6], motor[7]),
            self._project_elbow("left", motor[15]),
            self._project_elbow("right", motor[20]),
        )
        return ClosureProjection(
            usd_motor_positions=self.motor_to_usd(motor),
            linkage_outputs=outputs,
            maximum_residual_m=max(row.residual_m for row in outputs),
            all_in_validated_domain=all(
                row.in_validated_domain for row in outputs
            ),
        )
