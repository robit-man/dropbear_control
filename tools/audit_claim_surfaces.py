#!/usr/bin/env python3
"""Deterministically reject unsupported authority promotions on public surfaces."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tools/claim-surface-policy.json"
DEFAULT_OUTPUT = ROOT / "generated/myactuator/claim_surface/report.json"
SCHEMA = ROOT / "schemas/myactuator-claim-surface-report.schema.json"
GENERATOR = Path(__file__).resolve()
VERSION = "myactuator-claim-surface-report/1"

EXPECTED_ROOTS = (
    (".aiwg/architecture", "controlled_documentation"),
    (".aiwg/gates", "controlled_documentation"),
    (".aiwg/intake", "controlled_documentation"),
    (".aiwg/iterations", "controlled_documentation"),
    (".aiwg/planning", "controlled_documentation"),
    (".aiwg/reports", "controlled_documentation"),
    (".aiwg/requirements", "controlled_documentation"),
    (".aiwg/risks", "controlled_documentation"),
    (".aiwg/security", "controlled_documentation"),
    (".aiwg/testing", "controlled_documentation"),
    ("README.md", "public_documentation"),
    ("contracts", "public_documentation"),
    ("docs", "public_documentation"),
    ("firmware", "embedded_api"),
    ("generated", "generated_consumer"),
    ("host", "host_api"),
    ("ros2_control", "ros_api"),
    ("schemas", "machine_contract"),
    ("tools", "tool_api"),
    ("web", "web_ui"),
)
EXPECTED_EXCLUDED_PATHS = {
    "generated/myactuator/claim_surface",
    "generated/verification/offline_gate_report.json",
    "tools/audit_claim_surfaces.py",
    "tools/claim-surface-policy.json",
}
EXPECTED_EXCLUDED_DIRECTORIES = {
    ".mypy_cache",
    ".pio",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
EXPECTED_BINARY_SUFFIXES = {".glb", ".png", ".step"}

AUTHORITY_WORD = (
    r"(?:support(?:ed)?|compatib(?:le|ility)|validat(?:ed|ion)|"
    r"qualif(?:ied|ication)|certif(?:ied|ication)|ready|readiness)"
)
SUBJECT_WORD = (
    r"(?:myactuator|rmd(?:[-_ ]?[a-z0-9]+)?|motors?|actuators?|"
    r"models?|famil(?:y|ies)|series)"
)
CAUSAL_WORD = (
    r"(?:therefore|thus|hence|means?|proves?|establish(?:es|ed)?|"
    r"confirms?|demonstrates?|so)"
)
CLAUSE_64 = r"[^.!?;|]{0,64}?"
CLAUSE_72 = r"[^.!?;|]{0,72}?"
CLAUSE_96 = r"[^.!?;|]{0,96}?"
CLAUSE_120 = r"[^.!?;|]{0,120}?"
CLAUSE_180 = r"[^.!?;|]{0,180}?"


class ClaimSurfaceError(ValueError):
    """The policy, scoped input, report, or checked output is invalid."""


@dataclass(frozen=True)
class LexicalRule:
    rule_id: str
    description: str
    expression: re.Pattern[str]


def compile_rule(rule_id: str, description: str, pattern: str) -> LexicalRule:
    return LexicalRule(
        rule_id,
        description,
        re.compile(pattern, re.IGNORECASE | re.DOTALL),
    )


LEXICAL_RULES = (
    compile_rule(
        "CLM-FAMILY-UNIVERSAL",
        "A family, series, wildcard, or universal motor scope is promoted.",
        rf"(?:\b(?:all|every|entire|whole|complete)\s+(?:the\s+)?"
        rf"{SUBJECT_WORD}\b{CLAUSE_64}\b(?:is|are|has|have|now)\b"
        rf"{CLAUSE_64}\b{AUTHORITY_WORD}\b|"
        rf"\b(?:supports?|validates?|qualifies?|certifies?)\s+"
        rf"(?:all|every|the\s+(?:entire|whole|complete))\s+"
        rf"{SUBJECT_WORD}\b)",
    ),
    compile_rule(
        "CLM-FAMILY-WIDE",
        "A family-wide or series-wide authority claim is made.",
        rf"(?:\b(?:family|series)[ -]wide\s+{AUTHORITY_WORD}\b|"
        rf"\b(?:supports?|validates?|qualifies?|certifies?)\s+"
        rf"(?:the\s+)?[a-z0-9_-]+\s+(?:family|series)\b)",
    ),
    compile_rule(
        "CLM-ACQUISITION-CAUSAL",
        "Acquisition or local availability is asserted to establish authority.",
        rf"\b(?:download(?:ed|ing)?|acquir(?:ed|ing)|cached|extracted|"
        rf"unpacked|imported|catalog(?:ed|ued)?|source[- ]present|"
        rf"step[- ]present)\b{CLAUSE_180}\b{CAUSAL_WORD}\b"
        rf"{CLAUSE_120}\b(?:motor|actuator|model|family|series|hardware|"
        rf"robot|cad|asset|firmware|protocol)\b{CLAUSE_64}"
        rf"\b{AUTHORITY_WORD}\b",
    ),
    compile_rule(
        "CLM-ACQUISITION-DIRECT",
        "An acquired artifact is directly labeled authoritative.",
        rf"\b(?:downloaded|acquired|cached|extracted|unpacked|imported|"
        rf"catalog(?:ed|ued)?|available)\s+(?:cad|step|model|motor|"
        rf"actuator|artifact|file|package|manual|documentation)s?\b"
        rf"{CLAUSE_96}\b(?:is|are|makes?|renders?)\b"
        rf"{CLAUSE_64}\b{AUTHORITY_WORD}\b",
    ),
    compile_rule(
        "CLM-BUILD-CAUSAL",
        "A build, compile, unit, CI, or offline-gate result is promoted.",
        rf"\b(?:build|built|compile[sd]?|compilation|unit tests?|"
        rf"offline gate|ci|test suite|tests? pass(?:ed|ing)?)\b"
        rf"{CLAUSE_180}\b{CAUSAL_WORD}\b{CLAUSE_120}"
        rf"\b(?:hardware|motor|actuator|robot|production|physical(?:ly)?)"
        rf"\s+(?:(?:is|are)\s+)?{AUTHORITY_WORD}\b",
    ),
    compile_rule(
        "CLM-SIMULATION-CAUSAL",
        "SIL, emulation, replay, or simulation is promoted to physical authority.",
        rf"\b(?:sil|simulation|simulator|simulated|emulation|emulator|"
        rf"replay)\b{CLAUSE_180}\b{CAUSAL_WORD}\b{CLAUSE_120}"
        rf"\b(?:hardware|motor|actuator|robot|production|physical(?:ly)?)"
        rf"\s+(?:(?:is|are)\s+)?{AUTHORITY_WORD}\b",
    ),
    compile_rule(
        "CLM-BUILD-DIRECT",
        "A successful offline result directly labels a physical target authoritative.",
        rf"\b(?:successful|passing|passed)?\s*(?:build|compile|compilation|"
        rf"unit tests?|offline gate|ci|test suite|sil|simulation|emulator)"
        rf"\b{CLAUSE_120}\b(?:makes?|renders?|is|are)\b{CLAUSE_72}"
        rf"\b(?:hardware|motor|actuator|robot|production|physical(?:ly)?)"
        rf"\s*{AUTHORITY_WORD}\b",
    ),
    compile_rule(
        "CLM-PHYSICAL-AUTHORITY",
        "A direct production, hardware, HIL, robot, or motion authority claim is made.",
        rf"(?:\b(?:dropbear|robot|motor|actuator|controller|hardware|"
        rf"system|project|firmware|model)\b{CLAUSE_64}"
        rf"\b(?:is|are|becomes?|became)\b{CLAUSE_64}"
        rf"\b(?:production|hardware|physical(?:ly)?|bench|hil|robot|"
        rf"motion)[- ]+(?:ready|validated|qualified|certified|"
        rf"supported|safe)\b|\b(?:dropbear|robot|motor|actuator|"
        rf"controller|hardware|system|project|firmware|model)\b"
        rf"{CLAUSE_64}\b(?:is|are|becomes?|became)\b{CLAUSE_64}"
        rf"\b(?:ready|validated|qualified|certified|supported|safe)"
        rf"\s+for\s+(?:production|hardware|powered|physical|motion|"
        rf"robot)\b)",
    ),
    compile_rule(
        "CLM-UNCONDITIONAL-AUTHORITY",
        "A full, complete, or unconditional authority claim is made.",
        rf"\b(?:full|complete|unconditional)\s+"
        rf"(?:motor|actuator|model|hardware|firmware|protocol|cad|"
        rf"simulation|robot)?\s*(?:support|compatibility|validation|"
        rf"qualification|certification|readiness)\b",
    ),
)

FORBIDDEN_TRUE_KEYS = {
    "bench_or_hil_performed",
    "exact_model_simulation_ready",
    "hardware_can_capture_performed",
    "motion_enable_allowed",
    "physical_action_permitted",
    "physical_can_adapter_factory_enabled",
    "physical_motion_authority",
    "physical_work_performed",
    "release_authorized",
    "robot_motion_performed",
    "support_granted",
    "unpowered_discovery_ready_for_execution",
    "whole_robot_runtime_ready",
}
FORBIDDEN_NONZERO_KEYS = {
    "accepted_cad_configuration_count",
    "accepted_measured_limit_record_count",
    "accepted_physical_calibration_count",
    "accepted_protocol_applicability_count",
    "authorized_physical_action_count",
    "dropbear_canonical_graph_count",
    "dropbear_motion_ready_count",
    "dropbear_runtime_route_count",
    "exact_model_simulation_ready_count",
    "physically_validated_plant_parameter_set_count",
    "selected_can_adapter_manifest_count",
    "selected_can_controller_count",
    "supported_catalog_model_count",
}
FORBIDDEN_STATUS_VALUES = {
    "bench_validated",
    "certified",
    "hardware_validated",
    "hil_validated",
    "motion_ready",
    "physically_validated",
    "production_ready",
    "robot_ready",
    "supported",
}
STRUCTURED_RULE_COUNT = 3
NEGATION = re.compile(
    r"\b(?:no|never|cannot|can't|does\s+not|do\s+not|is\s+not|are\s+not|"
    r"not(?!\s+only\b)|without|zero|false|denied|blocked|missing|"
    r"unverified|unsupported|unvalidated|unaccepted|unavailable|"
    r"unqualified)\b",
    re.IGNORECASE,
)
CONTRAST = re.compile(r"\b(?:but|however|nevertheless|nonetheless)\b", re.IGNORECASE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClaimSurfaceError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    try:
        return sha_bytes(path.read_bytes())
    except OSError as error:
        raise ClaimSurfaceError(f"cannot hash {path}: {error}") from error


def relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as error:
        raise ClaimSurfaceError(f"path escapes audit root: {path}") from error


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ClaimSurfaceError(f"cannot read JSON {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def validate_policy(value: dict[str, Any]) -> None:
    require(
        set(value) == {
            "schema_version",
            "authority",
            "roots",
            "excluded_paths",
            "excluded_directory_names",
            "binary_suffixes",
        },
        "claim-surface policy fields are not exact",
    )
    require(
        value["schema_version"] == "myactuator-claim-surface-policy/1",
        "claim-surface policy version drift",
    )
    require(
        value["authority"] == "static_claim_surface_scope_only",
        "claim-surface policy authority drift",
    )
    roots = value["roots"]
    require(isinstance(roots, list), "policy roots must be an array")
    require(
        tuple((item.get("path"), item.get("surface")) for item in roots)
        == EXPECTED_ROOTS
        and all(set(item) == {"path", "surface"} for item in roots),
        "claim-surface roots or classifications drift",
    )
    exclusions = value["excluded_paths"]
    require(isinstance(exclusions, list), "excluded_paths must be an array")
    require(
        {item.get("path") for item in exclusions} == EXPECTED_EXCLUDED_PATHS
        and len(exclusions) == len(EXPECTED_EXCLUDED_PATHS)
        and all(
            set(item) == {"path", "reason"}
            and isinstance(item["reason"], str)
            and len(item["reason"]) >= 24
            for item in exclusions
        ),
        "claim-surface exact exclusions drift",
    )
    require(
        set(value["excluded_directory_names"]) == EXPECTED_EXCLUDED_DIRECTORIES
        and len(value["excluded_directory_names"])
        == len(EXPECTED_EXCLUDED_DIRECTORIES),
        "claim-surface excluded directory set drift",
    )
    require(
        set(value["binary_suffixes"]) == EXPECTED_BINARY_SUFFIXES
        and len(value["binary_suffixes"]) == len(EXPECTED_BINARY_SUFFIXES),
        "claim-surface binary suffix set drift",
    )


def policy_for_root(root: Path, policy_path: Path) -> tuple[dict[str, Any], Path]:
    path = policy_path if policy_path.is_absolute() else root / policy_path
    value = load_json(path)
    validate_policy(value)
    return value, path


def is_excluded(relative_path: str, exclusions: set[str]) -> bool:
    return any(
        relative_path == item or relative_path.startswith(item + "/")
        for item in exclusions
    )


def scoped_files(
    root: Path, policy: dict[str, Any]
) -> Iterator[tuple[Path, str]]:
    seen: set[str] = set()
    exclusions = {item["path"] for item in policy["excluded_paths"]}
    excluded_directories = set(policy["excluded_directory_names"])
    for item in policy["roots"]:
        scoped_root = root / item["path"]
        require(scoped_root.exists(), f"claim-surface root missing: {item['path']}")
        candidates: Iterable[Path]
        if scoped_root.is_file():
            candidates = (scoped_root,)
        else:
            require(not scoped_root.is_symlink(), f"scoped root is symlink: {item['path']}")
            candidates = sorted(scoped_root.rglob("*"))
        for path in candidates:
            rel = relative(root, path)
            if any(part in excluded_directories for part in path.parts):
                continue
            if is_excluded(rel, exclusions):
                continue
            if path.is_symlink():
                raise ClaimSurfaceError(f"symlink is forbidden in audit scope: {rel}")
            if not path.is_file():
                continue
            require(rel not in seen, f"overlapping claim-surface roots include {rel}")
            seen.add(rel)
            yield path, item["surface"]


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def normalized_excerpt(value: str, limit: int = 240) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def clause_before_and_through(text: str, start: int, end: int) -> str:
    boundary = max(text.rfind(char, 0, start) for char in ".!?;,:|")
    for match in CONTRAST.finditer(text, boundary + 1, start):
        boundary = max(boundary, match.end() - 1)
    return text[boundary + 1 : end]


def is_explicitly_denied(text: str, start: int, end: int) -> bool:
    return NEGATION.search(clause_before_and_through(text, start, end)) is not None


def finding(
    *,
    rule_id: str,
    path: str,
    surface: str,
    location: str,
    excerpt: str,
    finding_kind: str,
) -> dict[str, str]:
    core = {
        "rule_id": rule_id,
        "path": path,
        "surface": surface,
        "location": location,
        "excerpt": normalized_excerpt(excerpt),
        "finding_kind": finding_kind,
    }
    return {
        "finding_id": "claimfinding-" + sha_bytes(canonical_bytes(core))[:20],
        **core,
    }


def lexical_findings(
    text: str,
    path: str,
    surface: str,
    *,
    location_prefix: str = "line",
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[tuple[str, int, int]] = set()
    for rule in LEXICAL_RULES:
        for match in rule.expression.finditer(text):
            key = (rule.rule_id, match.start(), match.end())
            if key in seen or is_explicitly_denied(text, match.start(), match.end()):
                continue
            seen.add(key)
            location = (
                f"{location_prefix}:{line_number(text, match.start())}"
                if location_prefix == "line"
                else location_prefix
            )
            results.append(
                finding(
                    rule_id=rule.rule_id,
                    path=path,
                    surface=surface,
                    location=location,
                    excerpt=match.group(0),
                    finding_kind="lexical",
                )
            )
    return results


def json_nodes(
    value: Any, pointer: str = ""
) -> Iterator[tuple[str, str | None, Any]]:
    if isinstance(value, dict):
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child = f"{pointer}/{escaped}"
            yield child, key, value[key]
            yield from json_nodes(value[key], child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{pointer}/{index}"
            yield child, None, item
            yield from json_nodes(item, child)


def structured_findings(
    value: Any, path: str, surface: str
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for pointer, key, item in json_nodes(value):
        if key in FORBIDDEN_TRUE_KEYS and item is True:
            results.append(
                finding(
                    rule_id="CLM-STRUCTURED-AUTHORITY-TRUE",
                    path=path,
                    surface=surface,
                    location=pointer,
                    excerpt=f"{key}=true",
                    finding_kind="structured",
                )
            )
        if (
            key in FORBIDDEN_NONZERO_KEYS
            and isinstance(item, int)
            and not isinstance(item, bool)
            and item != 0
        ):
            results.append(
                finding(
                    rule_id="CLM-STRUCTURED-AUTHORITY-NONZERO",
                    path=path,
                    surface=surface,
                    location=pointer,
                    excerpt=f"{key}={item}",
                    finding_kind="structured",
                )
            )
        if (
            key is not None
            and (key == "status" or key.endswith("_status"))
            and isinstance(item, str)
            and item.casefold().replace("-", "_").replace(" ", "_")
            in FORBIDDEN_STATUS_VALUES
        ):
            results.append(
                finding(
                    rule_id="CLM-STRUCTURED-AUTHORITY-STATUS",
                    path=path,
                    surface=surface,
                    location=pointer,
                    excerpt=f"{key}={item}",
                    finding_kind="structured",
                )
            )
    return results


def json_string_findings(
    value: Any, path: str, surface: str
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for pointer, _, item in json_nodes(value):
        if isinstance(item, str):
            results.extend(
                lexical_findings(
                    item,
                    path,
                    surface,
                    location_prefix=pointer,
                )
            )
    return results


def strip_implementation_comments(text: str) -> str:
    """Remove C-family implementation comments while preserving locations.

    Header comments remain in scope as API documentation.  Implementation
    comments in C/C++/JavaScript are not an API or UI surface, but runtime
    string literals remain fully scanned.
    """

    result = list(text)
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(text):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            for position in range(index, end):
                result[position] = " "
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ClaimSurfaceError("unterminated implementation block comment")
            end += 2
            for position in range(index, end):
                if result[position] != "\n":
                    result[position] = " "
            index = end
            continue
        index += 1
    return "".join(result)


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def manifest_digest(
    scanned: list[dict[str, Any]], binaries: list[dict[str, Any]]
) -> str:
    records = [
        f"{item['path']}\0{item['sha256']}\0{item['byte_count']}\0"
        f"{item['surface']}\0{item['content_kind']}"
        for item in [*scanned, *binaries]
    ]
    return sha_bytes("\0".join(records).encode("utf-8"))


def audit(
    root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    root = root.resolve()
    policy, resolved_policy_path = policy_for_root(root, policy_path)
    binary_suffixes = set(policy["binary_suffixes"])
    scanned: list[dict[str, Any]] = []
    binaries: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    surface_counts: Counter[str] = Counter()
    content_counts: Counter[str] = Counter()

    for path, surface in scoped_files(root, policy):
        rel = relative(root, path)
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ClaimSurfaceError(f"cannot read scoped file {rel}: {error}") from error
        suffix = path.suffix.casefold()
        base = {
            "path": rel,
            "sha256": sha_bytes(data),
            "byte_count": len(data),
            "surface": surface,
        }
        surface_counts[surface] += 1
        if suffix in binary_suffixes:
            binaries.append({**base, "content_kind": "binary_nonsemantic"})
            content_counts["binary_nonsemantic"] += 1
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeError as error:
            raise ClaimSurfaceError(
                f"non-UTF-8 file is not an allowed binary: {rel}: {error}"
            ) from error
        if suffix == ".json":
            try:
                value = json.loads(text)
            except json.JSONDecodeError as error:
                raise ClaimSurfaceError(f"malformed scoped JSON {rel}: {error}") from error
            content_kind = "structured_json"
            findings.extend(structured_findings(value, rel, surface))
            findings.extend(json_string_findings(value, rel, surface))
        else:
            content_kind = "utf8_text"
            semantic_text = (
                strip_implementation_comments(text)
                if suffix in {".c", ".cc", ".cpp", ".js", ".mjs"}
                else text
            )
            findings.extend(lexical_findings(semantic_text, rel, surface))
        scanned.append({**base, "content_kind": content_kind})
        content_counts[content_kind] += 1

    scanned.sort(key=lambda item: item["path"])
    binaries.sort(key=lambda item: item["path"])
    findings.sort(
        key=lambda item: (
            item["path"],
            item["location"],
            item["rule_id"],
            item["finding_id"],
        )
    )
    source_manifest = manifest_digest(scanned, binaries)
    policy_rel = relative(root, resolved_policy_path)
    generator_rel = relative(root, GENERATOR if root == ROOT.resolve() else root / "tools/audit_claim_surfaces.py")
    schema_path = root / "schemas/myactuator-claim-surface-report.schema.json"
    require(schema_path.is_file(), "claim-surface report schema missing")
    verifier_sources = [
        {"path": generator_rel, "sha256": sha_file(root / generator_rel)},
        {"path": policy_rel, "sha256": sha_file(resolved_policy_path)},
        {
            "path": relative(root, schema_path),
            "sha256": sha_file(schema_path),
        },
    ]
    activity_basis = {
        "source_manifest_sha256": source_manifest,
        "verifier_sources": verifier_sources,
    }
    report: dict[str, Any] = {
        "schema_version": VERSION,
        "audit_id": "claimaudit-" + sha_bytes(canonical_bytes(activity_basis))[:20],
        "authority": "deterministic_static_lint_evidence_only",
        "verifier_sources": verifier_sources,
        "provenance": {
            "entity_ids": [
                "entity:claim-surface-policy",
                "entity:claim-surface-input-manifest",
            ],
            "activity_id": "activity:"
            + sha_bytes(canonical_bytes(activity_basis))[:24],
            "activity_type": "deterministic_static_claim_surface_scan",
            "agent_id": "agent:audit-claim-surfaces-py",
            "was_generated_by": "activity:"
            + sha_bytes(canonical_bytes(activity_basis))[:24],
        },
        "scope": {
            "root_count": len(policy["roots"]),
            "excluded_path_count": len(policy["excluded_paths"]),
            "excluded_directory_name_count": len(
                policy["excluded_directory_names"]
            ),
            "binary_suffix_count": len(policy["binary_suffixes"]),
            "source_manifest_sha256": source_manifest,
            "roots": policy["roots"],
            "excluded_paths": policy["excluded_paths"],
            "excluded_directory_names": policy["excluded_directory_names"],
            "binary_suffixes": policy["binary_suffixes"],
        },
        "scanned_sources": scanned,
        "binary_assets": binaries,
        "findings": findings,
        "summary": {
            "scanned_file_count": len(scanned),
            "scanned_byte_count": sum(item["byte_count"] for item in scanned),
            "binary_asset_count": len(binaries),
            "binary_asset_byte_count": sum(
                item["byte_count"] for item in binaries
            ),
            "surface_file_counts": dict(sorted(surface_counts.items())),
            "content_kind_counts": dict(sorted(content_counts.items())),
            "lexical_rule_count": len(LEXICAL_RULES),
            "structured_rule_count": STRUCTURED_RULE_COUNT,
            "finding_count": len(findings),
            "exception_count": 0,
            "passed": not findings,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_action_permitted": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(report)
    return report


def validator(root: Path = ROOT) -> Draft202012Validator:
    schema_path = root / "schemas/myactuator-claim-surface-report.schema.json"
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(value: dict[str, Any], root: Path = ROOT) -> None:
    errors = sorted(
        validator(root).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise ClaimSurfaceError(
            f"schema failure at /{'/'.join(map(str, error.absolute_path))}: "
            f"{error.message}"
        )
    require(
        value["integrity"]["record_sha256"] == sha_bytes(digest_payload(value)),
        "claim-surface report embedded digest drift",
    )
    scanned = value["scanned_sources"]
    binaries = value["binary_assets"]
    require(
        [item["path"] for item in scanned]
        == sorted(item["path"] for item in scanned)
        and [item["path"] for item in binaries]
        == sorted(item["path"] for item in binaries),
        "claim-surface file records are not path ordered",
    )
    all_paths = [item["path"] for item in [*scanned, *binaries]]
    require(
        len(all_paths) == len(set(all_paths)),
        "claim-surface file records contain duplicate paths",
    )
    require(
        value["scope"]["source_manifest_sha256"]
        == manifest_digest(scanned, binaries),
        "claim-surface source manifest drift",
    )
    require(
        value["summary"]["scanned_file_count"] == len(scanned)
        and value["summary"]["scanned_byte_count"]
        == sum(item["byte_count"] for item in scanned)
        and value["summary"]["binary_asset_count"] == len(binaries)
        and value["summary"]["binary_asset_byte_count"]
        == sum(item["byte_count"] for item in binaries),
        "claim-surface summary file or byte counts drift",
    )
    require(value["summary"]["finding_count"] == len(value["findings"]), "finding count drift")
    require(not value["findings"], "claim-surface audit has findings")
    require(value["summary"]["passed"], "claim-surface audit did not pass")
    require(value["summary"]["exception_count"] == 0, "claim exceptions are forbidden")
    require(
        value["summary"]["lexical_rule_count"] == len(LEXICAL_RULES)
        and value["summary"]["structured_rule_count"] == STRUCTURED_RULE_COUNT,
        "claim rule count drift",
    )


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    validate(value, path.resolve().parents[3] if "generated" in path.parts else ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(canonical_bytes(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def write_for_root(root: Path, output: Path, value: dict[str, Any]) -> None:
    validate(value, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{output.name}.", dir=output.parent, delete=False
    ) as temporary:
        temporary.write(canonical_bytes(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=Path("tools/claim-surface-policy.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated/myactuator/claim_surface/report.json"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        value = audit(root, policy_path)
        validate(value, root)
        encoded = canonical_bytes(value)
        if args.write:
            write_for_root(root, output, value)
            action = "WRITE"
        else:
            try:
                current = output.read_bytes()
            except OSError as error:
                raise ClaimSurfaceError(
                    f"claim-surface report missing; use --write: {error}"
                ) from error
            require(current == encoded, "claim-surface report is stale; use --write")
            action = "CHECK"
    except ClaimSurfaceError as error:
        print(f"CLAIM_SURFACE_AUDIT_FAIL {error}")
        return 1
    print(
        "CLAIM_SURFACE_AUDIT_"
        f"{action} PASS files={value['summary']['scanned_file_count']} "
        f"binaries={value['summary']['binary_asset_count']} "
        f"rules={len(LEXICAL_RULES) + STRUCTURED_RULE_COUNT} "
        "findings=0 exceptions=0 support=false motion=false physical=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
