"""Convert dashboard walking rollouts into validated 50 Hz SONIC references."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .closure_adapter import DropbearClosureAdapter
from .embodiment import (
    ACTION_COUNT,
    ACTION_NAMES,
    CONTRACT,
    EmbodimentContractError,
    verify_source_assets,
)


REFERENCE_SCHEMA = "dropbear-sonic-motion-reference-v1"
SAMPLE_RATE_HZ = 50
SAMPLE_PERIOD_SEC = 1.0 / SAMPLE_RATE_HZ


class MotionReferenceError(ValueError):
    """A motion source or converted bundle violates the Dropbear contract."""


def _finite_vector(
    value: Any, expected: int, label: str
) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise MotionReferenceError(f"{label} must be a numeric sequence")
    result = [float(item) for item in value]
    if len(result) != expected or not all(math.isfinite(item) for item in result):
        raise MotionReferenceError(
            f"{label} must contain exactly {expected} finite values"
        )
    return result


def _lerp(left: float, right: float, alpha: float) -> float:
    return left + (right - left) * alpha


def _lerp_vector(
    left: Sequence[float], right: Sequence[float], alpha: float
) -> list[float]:
    return [_lerp(float(a), float(b), alpha) for a, b in zip(left, right)]


def _roll_pitch_to_wxyz(roll: float, pitch: float) -> list[float]:
    """Convert source roll/pitch with zero yaw to a normalized quaternion."""

    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    return [cr * cp, sr * cp, cr * sp, -sr * sp]


def _source_frame(frame: Mapping[str, Any], index: int) -> dict[str, Any]:
    base = frame.get("base")
    if not isinstance(base, Mapping):
        raise MotionReferenceError(f"source frame {index} has no base state")
    q = _finite_vector(frame.get("q"), ACTION_COUNT, f"source frame {index} q")
    dq = _finite_vector(
        frame.get("dq"), ACTION_COUNT, f"source frame {index} dq"
    )
    contacts = _finite_vector(
        frame.get("contactLoadsKg", [0.0] * 4),
        4,
        f"source frame {index} contactLoadsKg",
    )
    state = {
        "time": float(frame.get("time")),
        "q": q,
        "dq": dq,
        "base": {
            "x": float(base.get("x", 0.0)),
            "y": float(base.get("y", 0.0)),
            "height": float(base.get("height")),
            "roll": float(base.get("roll", 0.0)),
            "pitch": float(base.get("pitch", 0.0)),
        },
        "contactLoadsKg": contacts,
    }
    scalar_values = [
        state["time"],
        *state["base"].values(),
    ]
    if not all(math.isfinite(value) for value in scalar_values):
        raise MotionReferenceError(f"source frame {index} has non-finite state")
    return state


def _interpolate_frame(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    alpha: float,
) -> dict[str, Any]:
    return {
        "q": _lerp_vector(left["q"], right["q"], alpha),
        "dq": _lerp_vector(left["dq"], right["dq"], alpha),
        "base": {
            key: _lerp(left["base"][key], right["base"][key], alpha)
            for key in ("x", "y", "height", "roll", "pitch")
        },
        "contactLoadsKg": _lerp_vector(
            left["contactLoadsKg"], right["contactLoadsKg"], alpha
        ),
    }


def convert_policy(
    source: Mapping[str, Any],
    *,
    source_name: str = "in-memory",
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Convert a `dropbear-walk-policy-v2` rollout to a 50 Hz bundle."""

    if source.get("schema") != "dropbear-walk-policy-v2":
        raise MotionReferenceError(
            "source must use schema dropbear-walk-policy-v2"
        )
    if tuple(source.get("jointOrder", ())) != ACTION_NAMES:
        raise MotionReferenceError("source jointOrder does not match the 22-motor contract")
    raw_frames = source.get("frames")
    if not isinstance(raw_frames, list) or len(raw_frames) < 2:
        raise MotionReferenceError("source must contain at least two frames")
    frames = [_source_frame(frame, index) for index, frame in enumerate(raw_frames)]
    source_times = [frame["time"] for frame in frames]
    if any(
        current <= previous
        for previous, current in zip(source_times, source_times[1:])
    ):
        raise MotionReferenceError("source frame times must be strictly increasing")

    verification = verify_source_assets(project_root)
    closure = DropbearClosureAdapter(verification.project_root)
    start, end = source_times[0], source_times[-1]
    duration = end - start
    count = int(math.floor(duration * SAMPLE_RATE_HZ + 1e-8)) + 1
    output_frames: list[dict[str, Any]] = []
    source_index = 0
    for index in range(count):
        absolute_time = min(end, start + index * SAMPLE_PERIOD_SEC)
        while (
            source_index + 1 < len(frames) - 1
            and frames[source_index + 1]["time"] < absolute_time
        ):
            source_index += 1
        left, right = frames[source_index], frames[source_index + 1]
        span = right["time"] - left["time"]
        alpha = 0.0 if span <= 0.0 else (absolute_time - left["time"]) / span
        state = _interpolate_frame(left, right, max(0.0, min(1.0, alpha)))
        projection = closure.project(state["q"])
        base = state["base"]
        output_frames.append(
            {
                "timeSec": round(index * SAMPLE_PERIOD_SEC, 9),
                "rootPositionM": [base["x"], base["y"], base["height"]],
                "rootOrientationWxyz": _roll_pitch_to_wxyz(
                    base["roll"], base["pitch"]
                ),
                "jointPositionRad": state["q"],
                "jointVelocityRadSec": state["dq"],
                "contactLoadsKg": state["contactLoadsKg"],
                "reducedClosure": {
                    "leftKneeOutputRad": projection.linkage_outputs[0].output_angle_rad,
                    "rightKneeOutputRad": projection.linkage_outputs[1].output_angle_rad,
                    "leftElbowOutputRad": projection.linkage_outputs[2].output_angle_rad,
                    "rightElbowOutputRad": projection.linkage_outputs[3].output_angle_rad,
                    "maximumResidualM": projection.maximum_residual_m,
                    "validatedDomain": projection.all_in_validated_domain,
                },
            }
        )

    result = {
        "schema": REFERENCE_SCHEMA,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": source_name,
            "schema": source["schema"],
            "frameCount": len(frames),
            "sourceSamplePeriodSec": min(
                current - previous
                for previous, current in zip(source_times, source_times[1:])
            ),
        },
        "embodiment": {
            "schema": CONTRACT["schema"],
            "usdCommit": source.get("groundTruth", {}).get("usdCommit"),
            "actionCount": ACTION_COUNT,
            "passiveJointsCommandable": False,
        },
        "sampleRateHz": SAMPLE_RATE_HZ,
        "jointOrder": list(ACTION_NAMES),
        "frameCount": len(output_frames),
        "frames": output_frames,
    }
    validate_reference(result, project_root=verification.project_root)
    return result


def validate_reference(
    reference: Mapping[str, Any],
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Fail-closed validation used before training-data or deployment import."""

    if reference.get("schema") != REFERENCE_SCHEMA:
        raise MotionReferenceError(f"reference schema must be {REFERENCE_SCHEMA}")
    if reference.get("sampleRateHz") != SAMPLE_RATE_HZ:
        raise MotionReferenceError("reference must be sampled at exactly 50 Hz")
    if tuple(reference.get("jointOrder", ())) != ACTION_NAMES:
        raise MotionReferenceError("reference jointOrder is not canonical")
    frames = reference.get("frames")
    if not isinstance(frames, list) or len(frames) < 2:
        raise MotionReferenceError("reference must contain at least two frames")
    if reference.get("frameCount") != len(frames):
        raise MotionReferenceError("reference frameCount does not match frames")

    closure = DropbearClosureAdapter(project_root)
    maximum_residual = 0.0
    for index, frame in enumerate(frames):
        expected_time = index * SAMPLE_PERIOD_SEC
        actual_time = float(frame.get("timeSec"))
        if not math.isfinite(actual_time) or abs(actual_time - expected_time) > 1e-7:
            raise MotionReferenceError(
                f"frame {index} is not on the exact 50 Hz timeline"
            )
        root = _finite_vector(
            frame.get("rootPositionM"), 3, f"frame {index} rootPositionM"
        )
        quaternion = _finite_vector(
            frame.get("rootOrientationWxyz"),
            4,
            f"frame {index} rootOrientationWxyz",
        )
        norm = math.sqrt(sum(value * value for value in quaternion))
        if abs(norm - 1.0) > 1e-6:
            raise MotionReferenceError(
                f"frame {index} root quaternion is not normalized"
            )
        if root[2] <= 0.0:
            raise MotionReferenceError(f"frame {index} root height must be positive")
        q = _finite_vector(
            frame.get("jointPositionRad"),
            ACTION_COUNT,
            f"frame {index} jointPositionRad",
        )
        _finite_vector(
            frame.get("jointVelocityRadSec"),
            ACTION_COUNT,
            f"frame {index} jointVelocityRadSec",
        )
        contact_loads = _finite_vector(
            frame.get("contactLoadsKg"),
            4,
            f"frame {index} contactLoadsKg",
        )
        if any(value < 0.0 for value in contact_loads):
            raise MotionReferenceError(
                f"frame {index} contactLoadsKg cannot be negative"
            )
        projection = closure.project(q)
        if not projection.all_in_validated_domain:
            raise MotionReferenceError(
                f"frame {index} leaves a validated closed-linkage domain"
            )
        maximum_residual = max(maximum_residual, projection.maximum_residual_m)

    if maximum_residual > 5e-4:
        raise MotionReferenceError(
            f"reduced closure residual {maximum_residual:.9f} m exceeds 0.0005 m"
        )
    return {
        "valid": True,
        "schema": REFERENCE_SCHEMA,
        "sampleRateHz": SAMPLE_RATE_HZ,
        "frameCount": len(frames),
        "durationSec": frames[-1]["timeSec"],
        "maximumReducedClosureResidualM": maximum_residual,
        "fullPassiveProjectionAuthority": "Isaac/PhysX",
    }


def write_csv_bundle(reference: Mapping[str, Any], directory: Path) -> None:
    """Write the pinned upstream reader's root-only CSV motion layout."""

    validate_reference(reference)
    directory.mkdir(parents=True, exist_ok=True)
    tables = {
        "joint_pos.csv": (
            [f"joint_{index}" for index in range(ACTION_COUNT)],
            [frame["jointPositionRad"] for frame in reference["frames"]],
        ),
        "joint_vel.csv": (
            [f"joint_vel_{index}" for index in range(ACTION_COUNT)],
            [frame["jointVelocityRadSec"] for frame in reference["frames"]],
        ),
        "body_pos.csv": (
            ["body_0_x", "body_0_y", "body_0_z"],
            [frame["rootPositionM"] for frame in reference["frames"]],
        ),
        "body_quat.csv": (
            ["body_0_w", "body_0_x", "body_0_y", "body_0_z"],
            [frame["rootOrientationWxyz"] for frame in reference["frames"]],
        ),
    }
    for name, (header, rows) in tables.items():
        with (directory / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
    motion_name = str(reference.get("source", {}).get("name", "dropbear"))
    (directory / "metadata.txt").write_text(
        "\n".join(
            (
                f"Metadata for: {motion_name}",
                "==============================",
                "",
                "Body part indexes:",
                "[0]",
                "",
                f"Total timesteps: {len(reference['frames'])}",
                "",
            )
        ),
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MotionReferenceError(f"cannot read JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise MotionReferenceError(f"{path} must contain a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert or validate Dropbear SONIC motion references"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--csv-dir", type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "convert":
            result = convert_policy(
                _load_json(args.input), source_name=str(args.input)
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8"
            )
            if args.csv_dir:
                write_csv_bundle(result, args.csv_dir)
            report = validate_reference(result)
        else:
            report = validate_reference(_load_json(args.input))
    except (MotionReferenceError, EmbodimentContractError) as error:
        print(json.dumps({"valid": False, "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
