"""Canonical Dropbear embodiment contract and source-asset verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PACKAGE_DIR / "config" / "dropbear_embodiment.json"
CONTRACT: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

ACTION_NAMES = tuple(action["name"] for action in CONTRACT["actions"])
USD_JOINT_NAMES = tuple(action["usdJoint"] for action in CONTRACT["actions"])
ROS_JOINT_NAMES = tuple(action["rosJoint"] for action in CONTRACT["actions"])
ACTION_COUNT = int(CONTRACT["actionContract"]["count"])
OBSERVATION_DIM = int(
    CONTRACT["observationContract"]["decoderTotalDimension"]
)


class EmbodimentContractError(ValueError):
    """The checked-in embodiment or a source artifact violates its contract."""


@dataclass(frozen=True)
class SourceVerification:
    """Result of verifying all pinned Dropbear source artifacts."""

    project_root: Path
    verified_paths: tuple[Path, ...]
    articulation_statistics: Mapping[str, int]
    physics_statistics: Mapping[str, int]


def find_project_root(start: Path | None = None) -> Path:
    """Find the repository root without relying on the process directory."""

    candidate = (start or PACKAGE_DIR).resolve()
    for path in (candidate, *candidate.parents):
        if (path / "web" / "assets" / "robot" / "dropbear-articulation.json").is_file():
            return path
    raise EmbodimentContractError(
        "could not locate the repository containing the Dropbear articulation"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_contract(contract: Mapping[str, Any] = CONTRACT) -> None:
    """Validate ordering, dimensions and fail-closed actuator semantics."""

    actions = contract.get("actions")
    if not isinstance(actions, list) or len(actions) != ACTION_COUNT:
        raise EmbodimentContractError(
            f"actions must contain exactly {ACTION_COUNT} entries"
        )
    indices = [action.get("index") for action in actions]
    if indices != list(range(ACTION_COUNT)):
        raise EmbodimentContractError("action indices must be contiguous and ordered")
    for field in ("name", "usdJoint", "rosJoint"):
        values = [action.get(field) for action in actions]
        if any(not isinstance(value, str) or not value for value in values):
            raise EmbodimentContractError(f"every action requires {field}")
        if len(set(values)) != ACTION_COUNT:
            raise EmbodimentContractError(f"{field} values must be unique")
    if contract["actionContract"].get("passiveJointsCommandable") is not False:
        raise EmbodimentContractError("passive closed-loop joints must not be commandable")

    dimensions = contract["observationContract"]["decoderTerms"]
    total = sum(int(term["dimension"]) * int(term["history"]) for term in dimensions)
    expected = int(contract["observationContract"]["decoderTotalDimension"])
    if total != expected:
        raise EmbodimentContractError(
            f"decoder observation dimension is {total}, expected {expected}"
        )

    for action in actions:
        lower, upper = action["positionLimitRad"]
        center = float(action["centerRad"])
        scale = float(action["scaleRad"])
        if not float(lower) < float(upper):
            raise EmbodimentContractError(f"{action['name']} has an invalid limit")
        if not float(lower) <= center <= float(upper) or scale <= 0.0:
            raise EmbodimentContractError(
                f"{action['name']} has an invalid center or scale"
            )

    knees = {actions[4]["name"]: actions[4], actions[7]["name"]: actions[7]}
    for name, action in knees.items():
        if action["positionLimitRad"][0] != 0.0:
            raise EmbodimentContractError(f"{name} permits hyperextension past lock")


def verify_source_assets(project_root: Path | None = None) -> SourceVerification:
    """Verify hashes, source statistics, action joints and closure topology."""

    validate_contract()
    root = (project_root or find_project_root()).resolve()
    verified: list[Path] = []
    for artifact in CONTRACT["sourceAssets"]:
        path = root / artifact["path"]
        if not path.is_file():
            raise EmbodimentContractError(f"missing source asset: {path}")
        actual = _sha256(path)
        if actual != artifact["sha256"]:
            raise EmbodimentContractError(
                f"source asset digest drift for {artifact['path']}: {actual}"
            )
        verified.append(path)

    articulation_path = root / "web/assets/robot/dropbear-articulation.json"
    articulation = json.loads(articulation_path.read_text(encoding="utf-8"))
    statistics = articulation.get("statistics", {})
    for field, expected in CONTRACT["expectedSourceStatistics"].items():
        if statistics.get(field) != expected:
            raise EmbodimentContractError(
                f"articulation statistic {field}={statistics.get(field)!r}, "
                f"expected {expected!r}"
            )

    physics_path = root / "web/assets/robot/dropbear-physics-manifest.json"
    physics = json.loads(physics_path.read_text(encoding="utf-8"))
    physics_statistics = physics.get("statistics", {})
    for field, expected in CONTRACT["expectedPhysicsStatistics"].items():
        if physics_statistics.get(field) != expected:
            raise EmbodimentContractError(
                f"physics-manifest statistic "
                f"{field}={physics_statistics.get(field)!r}, "
                f"expected {expected!r}"
            )
    if len(physics.get("joints", [])) != int(
        CONTRACT["expectedPhysicsStatistics"]["physicsJoints"]
    ):
        raise EmbodimentContractError(
            "physics-manifest joint rows do not match physicsJoints"
        )

    source_joints = {joint["name"] for joint in articulation.get("joints", [])}
    missing = sorted(set(USD_JOINT_NAMES) - source_joints)
    if missing:
        raise EmbodimentContractError(
            f"articulation is missing commanded motor joints: {missing}"
        )

    closure_names = {
        joint["name"]
        for joint in articulation.get("joints", [])
        if joint.get("closure")
    }
    topology = articulation.get("browserKinematics", {})
    required_closures: set[str] = set()
    required_topology_joints: set[str] = set()
    for arm in topology.get("armLinkages", []):
        required_closures.update(arm["closureConstraints"])
        required_topology_joints.update(arm["closureConstraints"])
        required_topology_joints.update(arm["passiveJoints"])
        required_topology_joints.add(arm["elbowMotor"])
        required_topology_joints.add(arm["wristOutput"])
    for leg in topology.get("calfLinkages", []):
        required_closures.update(
            {
                leg["inner"]["ankleClosure"],
                leg["outer"]["ankleClosure"],
            }
        )
        required_topology_joints.update(
            {
                leg["inner"]["motorCrank"],
                leg["inner"]["rodPivot"],
                leg["inner"]["ankleClosure"],
                leg["outer"]["motorCrank"],
                leg["outer"]["rodPivot"],
                leg["outer"]["ankleClosure"],
                leg["footPivot"],
            }
        )
    missing_closures = sorted(required_closures - closure_names)
    if missing_closures:
        raise EmbodimentContractError(
            f"articulation is missing retained closure joints: {missing_closures}"
        )
    missing_topology = sorted(required_topology_joints - source_joints)
    if missing_topology:
        raise EmbodimentContractError(
            f"articulation is missing closed-linkage topology: {missing_topology}"
        )

    expected_can = {
        action["canId"]: action["usdJoint"]
        for action in CONTRACT["actions"]
        if action["canId"] is not None
    }
    actual_can = {
        row["canId"]: row["usdJoint"] for row in articulation["canBindings"]
    }
    if expected_can != actual_can:
        raise EmbodimentContractError("leg CAN-to-USD action binding drift")

    expected_arms = {
        action["name"]: action["usdJoint"]
        for action in CONTRACT["actions"][12:]
    }
    actual_arms = {
        f"{row['side']}_{row['physicalJoint']}": row["usdJoint"]
        for row in articulation["armMotorBindings"]
    }
    if expected_arms != actual_arms:
        raise EmbodimentContractError("arm semantic-to-USD action binding drift")

    return SourceVerification(
        project_root=root,
        verified_paths=tuple(verified),
        articulation_statistics=statistics,
        physics_statistics=physics_statistics,
    )


validate_contract()
