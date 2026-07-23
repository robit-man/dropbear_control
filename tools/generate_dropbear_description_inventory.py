#!/usr/bin/env python3
"""Inventory pinned Dropbear robot-description candidates without promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DROPBEAR = ROOT / "references/Dropbear"
PINNED_COMMIT = "13cf5ecaa39b8b89c794fe905dcea0490cfa7726"
RECONCILIATION = ROOT / "generated/dropbear_reconciliation/reconciliation.json"
SCHEMA = ROOT / "schemas/dropbear-description-inventory.schema.json"
OUTPUT = ROOT / "generated/dropbear_description/inventory.json"
DESCRIPTION_ROOTS = (
    "CAD_Files/Assembly/Full_Body/URDF/",
    "Sim/Gazebo/",
    "Sim/RViz/",
)


class InventoryError(RuntimeError):
    """Pinned source or generated inventory violates the observation contract."""


def canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(DROPBEAR), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise InventoryError(
            f"git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def git_blobs(oids: list[str]) -> dict[str, bytes]:
    """Read only selected objects in one batch.

    The Dropbear checkout is sparse/partial. `ls-tree -l` would ask Git for
    sizes of every unrelated CAD blob and can trigger a repository-wide fetch.
    A selected `cat-file --batch` keeps object acquisition bounded to this
    inventory.
    """
    requested = sorted(set(oids))
    raw = git(
        "cat-file",
        "--batch",
        input_bytes=("".join(f"{oid}\n" for oid in requested)).encode("ascii"),
    )
    result: dict[str, bytes] = {}
    offset = 0
    for expected in requested:
        newline = raw.find(b"\n", offset)
        if newline < 0:
            raise InventoryError("truncated git cat-file batch header")
        header = raw[offset:newline].decode("ascii")
        offset = newline + 1
        parts = header.split()
        if len(parts) != 3 or parts[0] != expected or parts[1] != "blob":
            raise InventoryError(f"unexpected git cat-file header: {header}")
        size = int(parts[2])
        value = raw[offset : offset + size]
        offset += size
        if len(value) != size or raw[offset : offset + 1] != b"\n":
            raise InventoryError(f"truncated git blob: {expected}")
        offset += 1
        result[expected] = value
    if offset != len(raw):
        raise InventoryError("unexpected trailing bytes from git cat-file batch")
    return result


def selected(path: str) -> bool:
    lower = path.lower()
    if not path.startswith(DESCRIPTION_ROOTS):
        return False
    return lower.endswith((".urdf", ".xacro")) or (
        "controller" in lower and lower.endswith((".yaml", ".yml"))
    )


def tree_files() -> list[dict[str, Any]]:
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    if head != PINNED_COMMIT:
        raise InventoryError(
            f"Dropbear checkout drift: expected {PINNED_COMMIT}, found {head}"
        )
    result: list[dict[str, Any]] = []
    raw = git("ls-tree", "-rz", "--full-tree", PINNED_COMMIT)
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, oid = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if object_type == "blob" and selected(path):
            result.append(
                {
                    "path": path,
                    "mode": mode,
                    "git_object_id": oid,
                }
            )
    result.sort(key=lambda item: item["path"])
    if not result:
        raise InventoryError("no description candidates found in pinned tree")
    return result


def classification(path: str) -> str:
    if "/install/" in path:
        return "install_derivative"
    if "/build/" in path:
        return "build_derivative"
    if path.lower().endswith(".urdf"):
        return "expanded_generated_candidate"
    return "source_candidate"


def description_kind(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".xacro"):
        return "xacro"
    if lower.endswith(".urdf"):
        return "urdf"
    return "controller_yaml"


def package_family(path: str) -> str:
    if path.startswith("CAD_Files/"):
        if "dropbear_simplified_urdf" in path:
            return "cad_simplified"
        return "cad_detailed"
    if path.startswith("Sim/Gazebo/dropbear-sim/"):
        return "gazebo_dropbear"
    if path.startswith("Sim/Gazebo/dropbear_detailed_urdf/"):
        return "gazebo_detailed"
    if path.startswith("Sim/Gazebo/dropbear_simplified_urdf/"):
        return "gazebo_simplified"
    if path.startswith("Sim/RViz/detailed_urdf/"):
        return "rviz_detailed"
    if path.startswith("Sim/RViz/simplified_urdf/"):
        return "rviz_simplified"
    if path.startswith("Sim/RViz/dropbear_urdf/"):
        return "rviz_legacy"
    raise InventoryError(f"unclassified description package path: {path}")


def logical_key(path: str) -> str:
    for marker in ("/urdf/", "/config/"):
        if marker in path:
            return marker[1:] + path.split(marker, 1)[1]
    return Path(path).name


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def first_descendant(element: ET.Element, wanted: str) -> ET.Element | None:
    for child in element.iter():
        if child is element:
            continue
        if local_name(child.tag) == wanted:
            return child
    return None


def child_value(element: ET.Element, wanted: str, attribute: str) -> str | None:
    child = first_descendant(element, wanted)
    if child is None:
        return None
    value = child.attrib.get(attribute)
    if value is not None:
        return value
    text = (child.text or "").strip()
    return text or None


def xml_observations(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    try:
        root = ET.fromstring(text)
        parse_status = "xml_parsed"
        parse_error = None
        elements = list(root.iter())
    except ET.ParseError as error:
        # A malformed candidate remains inventoried. The fallback extracts only
        # directly stated tokens and grants no structural authority.
        parse_status = "regex_fallback"
        parse_error = str(error)
        elements = []

    if elements:
        links = sorted(
            {
                value
                for element in elements
                if local_name(element.tag) == "link"
                for value in [element.attrib.get("name")]
                if value
            }
        )
        meshes = sorted(
            {
                value
                for element in elements
                if local_name(element.tag) == "mesh"
                for value in [element.attrib.get("filename")]
                if value
            }
        )
        macros = sorted(
            {
                value
                for element in elements
                if local_name(element.tag) == "macro"
                for value in [element.attrib.get("name")]
                if value
            }
        )
        plugins = sorted(
            {
                value
                for element in elements
                if local_name(element.tag) == "plugin"
                for value in [
                    element.attrib.get("filename")
                    or (element.text or "").strip()
                ]
                if value
            }
        )
        joints: list[dict[str, Any]] = []
        for element in elements:
            if local_name(element.tag) != "joint":
                continue
            name = element.attrib.get("name")
            if not name:
                continue
            mimic = first_descendant(element, "mimic")
            axis = first_descendant(element, "axis")
            axis_value = None
            if axis is not None:
                axis_value = axis.attrib.get("xyz")
                if axis_value is None:
                    xyz = first_descendant(axis, "xyz")
                    axis_value = ((xyz.text or "").strip() if xyz is not None else None) or None
            origin = first_descendant(element, "origin")
            joints.append(
                {
                    "name": name,
                    "type": element.attrib.get("type"),
                    "parent": child_value(element, "parent", "link"),
                    "child": child_value(element, "child", "link"),
                    "axis_xyz": axis_value,
                    "origin_xyz": origin.attrib.get("xyz") if origin is not None else None,
                    "origin_rpy": origin.attrib.get("rpy") if origin is not None else None,
                    "mimic_joint": mimic.attrib.get("joint") if mimic is not None else None,
                    "mimic_multiplier": mimic.attrib.get("multiplier") if mimic is not None else None,
                    "mimic_offset": mimic.attrib.get("offset") if mimic is not None else None,
                }
            )
        joints.sort(
            key=lambda item: (
                item["name"],
                item["parent"] or "",
                item["child"] or "",
            )
        )
        transmission_joints = sorted(
            {
                joint.attrib["name"]
                for transmission in elements
                if local_name(transmission.tag) == "transmission"
                for joint in transmission.iter()
                if local_name(joint.tag) == "joint" and joint.attrib.get("name")
            }
        )
        ros2_control_joints = sorted(
            {
                joint.attrib["name"]
                for control in elements
                if local_name(control.tag) == "ros2_control"
                for joint in control.iter()
                if local_name(joint.tag) == "joint" and joint.attrib.get("name")
            }
        )
    else:
        links = sorted(set(re.findall(r"<link\s+[^>]*name=[\"']([^\"']+)", text)))
        meshes = sorted(set(re.findall(r"<mesh\s+[^>]*filename=[\"']([^\"']+)", text)))
        macros = sorted(set(re.findall(r"<(?:xacro:)?macro\s+[^>]*name=[\"']([^\"']+)", text)))
        plugins = sorted(
            set(
                re.findall(
                    r"<plugin\s+[^>]*(?:filename=[\"']([^\"']+)|>([^<]+)</plugin>)",
                    text,
                )
            )
        )
        plugins = sorted({part for pair in plugins for part in pair if part})
        joints = [
            {
                "name": match.group(1),
                "type": match.group(2),
                "parent": None,
                "child": None,
                "axis_xyz": None,
                "origin_xyz": None,
                "origin_rpy": None,
                "mimic_joint": None,
                "mimic_multiplier": None,
                "mimic_offset": None,
            }
            for match in re.finditer(
                r"<joint\s+[^>]*name=[\"']([^\"']+)[\"'][^>]*"
                r"type=[\"']([^\"']+)[\"']",
                text,
            )
        ]
        transmission_joints = []
        ros2_control_joints = []

    mimic_edges = sorted(
        [
            {
                "joint": joint["name"],
                "mimics": joint["mimic_joint"],
                "multiplier": joint["mimic_multiplier"],
                "offset": joint["mimic_offset"],
            }
            for joint in joints
            if joint["mimic_joint"] is not None
        ],
        key=lambda item: (item["joint"], item["mimics"]),
    )
    return {
        "parse_status": parse_status,
        "parse_error": parse_error,
        "links": links,
        "joints": joints,
        "mesh_references": meshes,
        "xacro_macros": macros,
        "plugin_references": plugins,
        "transmission_joint_names": transmission_joints,
        "ros2_control_joint_names": ros2_control_joints,
        "controller_joint_names": [],
        "mimic_edges": mimic_edges,
    }


def yaml_observations(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    joint_names = sorted(
        set(
            re.findall(
                r"^\s*-\s+([A-Za-z][A-Za-z0-9_${}\- ]*)\s*(?:#.*)?$",
                text,
                flags=re.MULTILINE,
            )
        )
    )
    return {
        "parse_status": "yaml_lexical",
        "parse_error": None,
        "links": [],
        "joints": [],
        "mesh_references": [],
        "xacro_macros": [],
        "plugin_references": [],
        "transmission_joint_names": [],
        "ros2_control_joint_names": [],
        "controller_joint_names": joint_names,
        "mimic_edges": [],
    }


def observations(raw: bytes, kinds: list[str]) -> dict[str, Any]:
    return (
        yaml_observations(raw)
        if kinds == ["controller_yaml"]
        else xml_observations(raw)
    )


def load_reconciliation() -> dict[str, Any]:
    try:
        value = json.loads(RECONCILIATION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InventoryError(f"cannot read reconciliation: {error}") from error
    if not isinstance(value, dict):
        raise InventoryError("reconciliation root must be an object")
    if value["generated_from"]["dropbear_repository_commit"] != PINNED_COMMIT:
        raise InventoryError("reconciliation commit differs from description inventory")
    return value


def question_records(
    files: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    reconciliation: dict[str, Any],
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    ros_by_side = {
        row["chirality"]: row["joint_ids"]
        for row in reconciliation["ros_leg_groups"]
    }
    if set(ros_by_side) != {"left", "right"}:
        raise InventoryError("reconciliation must contain both ROS leg groups")
    actuators_by_side: dict[str, list[dict[str, Any]]] = {"left": [], "right": []}
    for actuator in reconciliation["actuators"]:
        actuators_by_side[actuator["chirality"]].append(actuator)
        questions.append(
            {
                "question_id": (
                    "map-" + actuator["canonical_joint_name"].replace("_", "-")
                ),
                "kind": "actuator_mapping",
                "subject_ids": [actuator["actuator_id"]],
                "candidate_joint_names": ros_by_side[actuator["chirality"]],
                "evidence_paths": [],
                "question": (
                    f"Which reviewed active, passive or coupled graph edge, if any, "
                    f"maps {actuator['canonical_joint_name']} to the five observed "
                    f"{actuator['chirality']} ROS command joints?"
                ),
                "resolved": False,
                "runtime_mapping_id": None,
            }
        )
    for side in ("left", "right"):
        questions.append(
            {
                "question_id": f"cardinality-{side}-six-actuators-five-ros-joints",
                "kind": "cardinality_and_coupling",
                "subject_ids": [
                    actuator["actuator_id"] for actuator in actuators_by_side[side]
                ],
                "candidate_joint_names": ros_by_side[side],
                "evidence_paths": [],
                "question": (
                    f"How do six {side} actuator observations relate to five ROS "
                    f"command joints, including passive, mimic and closed-chain "
                    f"constraints and the owner of every control loop?"
                ),
                "resolved": False,
                "runtime_mapping_id": None,
            }
        )

    paths_by_oid: dict[str, list[str]] = defaultdict(list)
    class_by_path = {item["path"]: item["classification"] for item in files}
    for item in files:
        if class_by_path[item["path"]] not in {
            "build_derivative",
            "install_derivative",
        }:
            paths_by_oid[item["git_object_id"]].append(item["path"])
    ambiguous: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for object_record in objects:
        evidence_paths = paths_by_oid.get(object_record["git_object_id"], [])
        if not evidence_paths:
            continue
        for joint in object_record["observations"]["joints"]:
            if joint["mimic_joint"] is not None:
                key = (
                    "mimic_or_coupling",
                    joint["name"],
                    joint["mimic_joint"],
                    joint["parent"] or "",
                    joint["child"] or "",
                )
                ambiguous.setdefault(
                    key,
                    {
                        "kind": "mimic_or_coupling",
                        "joint": joint["name"],
                        "related": joint["mimic_joint"],
                        "parent": joint["parent"],
                        "child": joint["child"],
                        "paths": set(),
                    },
                )["paths"].update(evidence_paths)
            if " gz" in joint["name"].lower():
                key = (
                    "gazebo_loop_closure_candidate",
                    joint["name"],
                    "",
                    joint["parent"] or "",
                    joint["child"] or "",
                )
                ambiguous.setdefault(
                    key,
                    {
                        "kind": "gazebo_loop_closure_candidate",
                        "joint": joint["name"],
                        "related": "",
                        "parent": joint["parent"],
                        "child": joint["child"],
                        "paths": set(),
                    },
                )["paths"].update(evidence_paths)
    for index, item in enumerate(
        sorted(
            ambiguous.values(),
            key=lambda value: (
                value["kind"],
                value["joint"],
                value["related"],
                value["parent"] or "",
                value["child"] or "",
            ),
        ),
        start=1,
    ):
        related = (
            f" and references {item['related']}"
            if item["related"]
            else ""
        )
        questions.append(
            {
                "question_id": f"graph-edge-{index:03d}",
                "kind": item["kind"],
                "subject_ids": [],
                "candidate_joint_names": [item["joint"]]
                + ([item["related"]] if item["related"] else []),
                "evidence_paths": sorted(item["paths"]),
                "question": (
                    f"Is candidate joint {item['joint']}{related} an active, passive, "
                    f"mimic or simulator-only loop-closure edge, and what reviewed "
                    f"physical constraint and actuator mapping governs it?"
                ),
                "resolved": False,
                "runtime_mapping_id": None,
            }
        )
    return sorted(questions, key=lambda item: item["question_id"])


def build() -> dict[str, Any]:
    files = tree_files()
    reconciliation = load_reconciliation()
    content_by_oid = git_blobs([item["git_object_id"] for item in files])
    kinds_by_oid: dict[str, set[str]] = defaultdict(set)
    paths_by_oid: dict[str, list[str]] = defaultdict(list)
    for item in files:
        oid = item["git_object_id"]
        raw = content_by_oid[oid]
        item["git_reported_size_bytes"] = len(raw)
        item["sha256"] = sha256(raw)
        item["size_bytes"] = len(raw)
        item["classification"] = classification(item["path"])
        item["description_kind"] = description_kind(item["path"])
        item["package_family"] = package_family(item["path"])
        item["logical_key"] = logical_key(item["path"])
        item["authority"] = (
            "derivative_no_authority"
            if item["classification"] in {"build_derivative", "install_derivative"}
            else "candidate_observation_only"
        )
        kinds_by_oid[oid].add(item["description_kind"])
        paths_by_oid[oid].append(item["path"])

    candidate_files = [
        item
        for item in files
        if item["classification"] not in {"build_derivative", "install_derivative"}
    ]
    candidate_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidate_files:
        candidate_by_key[item["logical_key"]].append(item)
    for item in files:
        same_object = sorted(
            path for path in paths_by_oid[item["git_object_id"]] if path != item["path"]
        )
        candidates = candidate_by_key[item["logical_key"]]
        item["exact_copy_paths"] = same_object
        item["exact_candidate_matches"] = sorted(
            candidate["path"]
            for candidate in candidates
            if candidate["git_object_id"] == item["git_object_id"]
            and candidate["path"] != item["path"]
        )
        item["drifted_candidate_paths"] = sorted(
            candidate["path"]
            for candidate in candidates
            if candidate["git_object_id"] != item["git_object_id"]
        )

    objects = []
    for oid in sorted(content_by_oid):
        kinds = sorted(kinds_by_oid[oid])
        objects.append(
            {
                "git_object_id": oid,
                "sha256": sha256(content_by_oid[oid]),
                "size_bytes": len(content_by_oid[oid]),
                "description_kinds": kinds,
                "observations": observations(content_by_oid[oid], kinds),
            }
        )

    exact_groups = [
        {
            "git_object_id": oid,
            "sha256": sha256(content_by_oid[oid]),
            "paths": sorted(paths),
        }
        for oid, paths in sorted(paths_by_oid.items())
        if len(paths) > 1
    ]
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in files:
        by_key[item["logical_key"]].append(item)
    logical_groups = []
    for key, members in sorted(by_key.items()):
        if len(members) < 2:
            continue
        object_ids = sorted({member["git_object_id"] for member in members})
        logical_groups.append(
            {
                "logical_key": key,
                "status": "exact_duplicate" if len(object_ids) == 1 else "divergent",
                "git_object_ids": object_ids,
                "paths": sorted(member["path"] for member in members),
            }
        )

    questions = question_records(files, objects, reconciliation)
    counts = defaultdict(int)
    for item in files:
        counts[item["classification"]] += 1
    parse_counts = defaultdict(int)
    for item in objects:
        parse_counts[item["observations"]["parse_status"]] += 1
    artifact = {
        "schema_version": "dropbear-description-inventory/1",
        "artifact_id": "dropbear-description-candidate-inventory",
        "authority": "observation_only_no_runtime_promotion",
        "repository": {
            "path": "references/Dropbear",
            "commit": PINNED_COMMIT,
            "tree_id": git("rev-parse", f"{PINNED_COMMIT}^{{tree}}")
            .decode("ascii")
            .strip(),
        },
        "reconciliation": {
            "path": RECONCILIATION.relative_to(ROOT).as_posix(),
            "sha256": sha256(RECONCILIATION.read_bytes()),
            "canonical_configuration_digest": reconciliation["generated_from"][
                "canonical_configuration_digest"
            ],
        },
        "scope": {
            "roots": list(DESCRIPTION_ROOTS),
            "extensions": [".urdf", ".xacro", "controller*.yaml", "controller*.yml"],
        },
        "summary": {
            "file_count": len(files),
            "unique_object_count": len(objects),
            "source_candidate_count": counts["source_candidate"],
            "expanded_generated_candidate_count": counts[
                "expanded_generated_candidate"
            ],
            "build_derivative_count": counts["build_derivative"],
            "install_derivative_count": counts["install_derivative"],
            "exact_duplicate_group_count": len(exact_groups),
            "logical_group_count": len(logical_groups),
            "divergent_logical_group_count": sum(
                group["status"] == "divergent" for group in logical_groups
            ),
            "review_question_count": len(questions),
            "regex_fallback_object_count": parse_counts["regex_fallback"],
            "runtime_ros_actuator_mapping_count": 0,
            "authoritative_description_selected": False,
            "motion_enable_allowed": False,
        },
        "files": files,
        "objects": objects,
        "exact_duplicate_groups": exact_groups,
        "logical_groups": logical_groups,
        "review_questions": questions,
        "runtime_ros_actuator_mappings": [],
        "global_blockers": [
            "multiple_description_families_and_derivatives_committed",
            "source_authority_not_reviewed",
            "five_ros_joints_vs_six_actuators_per_leg_unresolved",
            "active_passive_mimic_and_closed_chain_graph_unreviewed",
            "zero_runtime_ros_actuator_mappings",
        ],
    }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(artifact),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise InventoryError(
            f"inventory schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = canonical(build())
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_bytes() != rendered:
            raise InventoryError(f"generated artifact drift: {output}")
        value = json.loads(rendered)
        print(
            "DROPBEAR_DESCRIPTION_INVENTORY_OK "
            f"files={value['summary']['file_count']} "
            f"objects={value['summary']['unique_object_count']} "
            f"questions={value['summary']['review_question_count']} "
            "mappings=0 motion=false "
            f"sha256={sha256(rendered)}"
        )
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    print(
        f"wrote {output.relative_to(ROOT)} "
        f"sha256={sha256(rendered)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (InventoryError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Dropbear description inventory failed: {error}", file=sys.stderr)
        raise SystemExit(1)
