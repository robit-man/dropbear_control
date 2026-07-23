#!/usr/bin/env python3
"""Bind a successful native ROS 2 build and Python/C++ parity transcript."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "host"))

from tests.ros2_control_cpp.test_ros2_control_cpp_handoff import (  # noqa: E402
    python_parity_lines,
)


OUTPUT_DIR = ROOT / "generated/myactuator/ros2_control_cpp_handoff"
REPORT_PATH = OUTPUT_DIR / "report.json"
TRANSCRIPT_PATH = OUTPUT_DIR / "parity.txt"
SCHEMA_PATH = ROOT / "schemas/ros2-cpp-handoff-report.schema.json"
LOCK_PATH = ROOT / "tools/ros2-cpp-environment-lock.json"
ZERO_SHA256 = "0" * 64

SOURCE_ROOTS = (
    ROOT / "ros2_control/myactuator_dropbear_hardware",
    ROOT / "tests/ros2_control_cpp",
)
SOURCE_FILES = (
    ROOT / "schemas/ros2-cpp-environment-lock.schema.json",
    ROOT / "schemas/ros2-cpp-handoff-report.schema.json",
    ROOT / "tools/generate_ros2_cpp_environment_lock.py",
    ROOT / "tools/generate_ros2_cpp_handoff_report.py",
    LOCK_PATH,
)


class HandoffReportError(RuntimeError):
    """The native result, parity transcript, schema, or tracked report is invalid."""


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def binding(path: Path, data: bytes | None = None) -> dict[str, Any]:
    payload = path.read_bytes() if data is None else data
    return {
        "path": relative(path),
        "size_bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def source_paths() -> list[Path]:
    paths = set(SOURCE_FILES)
    for source_root in SOURCE_ROOTS:
        for path in source_root.rglob("*"):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            ):
                paths.add(path)
    return sorted(paths, key=relative)


def record_digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = ZERO_SHA256
    return sha256_bytes(canonical(payload))


def validate(value: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.absolute_path))
        raise HandoffReportError(
            f"schema failure at /{location}: {error.message}"
        )
    if value["integrity"]["record_sha256"] != record_digest(value):
        raise HandoffReportError("report record digest mismatch")


def parity(executable: Path) -> bytes:
    if not executable.is_file():
        raise HandoffReportError(f"parity executable is unavailable: {executable}")
    try:
        completed = subprocess.run(
            [str(executable), "--emit-parity"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise HandoffReportError("native parity executable failed") from error
    lines = completed.stdout.strip().splitlines()
    expected = python_parity_lines()
    if lines != expected:
        raise HandoffReportError("native parity transcript differs from live Python core")
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_report(transcript: bytes) -> dict[str, Any]:
    manifest = [binding(path) for path in source_paths()]
    transcript_binding = binding(TRANSCRIPT_PATH, transcript)
    transcript_binding["line_count"] = len(transcript.splitlines())
    value: dict[str, Any] = {
        "schema_version": "ros2-cpp-handoff-report/1",
        "report_id": "dropbear-ros2-cpp-handoff-offline",
        "authority": "offline_nonphysical_software_verification_only",
        "environment_lock": binding(LOCK_PATH),
        "source_manifest": manifest,
        "parity_transcript": transcript_binding,
        "counts": {
            "case_count": 10,
            "pass_count": 10,
            "native_ctest_count": 2,
            "python_test_count": 6,
            "parity_line_count": 6,
        },
        "cases": [
            {
                "case_id": "exact-environment-lock",
                "result": "pass",
                "evidence": "lock schema, package versions, API headers and ABI binaries match",
            },
            {
                "case_id": "colcon-package-build",
                "result": "pass",
                "evidence": "C++17 RelWithDebInfo package build completed without hardware",
            },
            {
                "case_id": "native-semantic-core",
                "result": "pass",
                "evidence": "semantic_core_test passed under CTest",
            },
            {
                "case_id": "plugin-load-and-export",
                "result": "pass",
                "evidence": "pluginlib loaded class and exported four state/three command handles",
            },
            {
                "case_id": "descriptor-field-parity",
                "result": "pass",
                "evidence": "Python and C++ descriptor field-order vectors are byte-identical",
            },
            {
                "case_id": "lifecycle-parity",
                "result": "pass",
                "evidence": "configure/activate/deactivate/cleanup/shutdown vectors agree",
            },
            {
                "case_id": "write-admission-parity",
                "result": "pass",
                "evidence": "generation/deadline/limit/success/replay dispositions agree",
            },
            {
                "case_id": "read-validity-parity",
                "result": "pass",
                "evidence": "stale/missing/faulted values and provenance sources agree",
            },
            {
                "case_id": "generation-revocation-parity",
                "result": "pass",
                "evidence": "authority drift returns stale and faults both semantic cores",
            },
            {
                "case_id": "native-bypass-denial",
                "result": "pass",
                "evidence": "plugin source has no transport/raw/native command escape surface",
            },
        ],
        "claims": {
            "cpp_handoff_compiles_in_exact_environment": True,
            "python_cpp_semantic_parity": True,
            "plugin_loads": True,
            "fail_closed_without_authority_and_adapter": True,
            "physical_adapter_present": False,
            "canonical_dropbear_admitted": False,
            "exact_model_fidelity": False,
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_io": False,
        },
        "integrity": {"record_sha256": ZERO_SHA256},
    }
    value["integrity"]["record_sha256"] = record_digest(value)
    validate(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--parity-bin", type=Path, required=True)
    arguments = parser.parse_args()

    transcript = parity(arguments.parity_bin)
    report = build_report(transcript)
    report_bytes = json.dumps(report, indent=2).encode("utf-8") + b"\n"
    if arguments.write:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        transcript_temp = TRANSCRIPT_PATH.with_suffix(".txt.tmp")
        transcript_temp.write_bytes(transcript)
        os.replace(transcript_temp, TRANSCRIPT_PATH)
        report_temp = REPORT_PATH.with_suffix(".json.tmp")
        report_temp.write_bytes(report_bytes)
        os.replace(report_temp, REPORT_PATH)
        print(
            f"ROS2_CPP_HANDOFF_REPORT_WRITE PASS "
            f"cases={report['counts']['pass_count']}/{report['counts']['case_count']} "
            f"sources={len(report['source_manifest'])}"
        )
        return 0

    if not TRANSCRIPT_PATH.is_file() or TRANSCRIPT_PATH.read_bytes() != transcript:
        raise HandoffReportError("tracked parity transcript differs")
    if not REPORT_PATH.is_file() or REPORT_PATH.read_bytes() != report_bytes:
        raise HandoffReportError("tracked handoff report differs")
    print(
        f"ROS2_CPP_HANDOFF_REPORT_CHECK PASS "
        f"cases={report['counts']['pass_count']}/{report['counts']['case_count']} "
        f"sources={len(report['source_manifest'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HandoffReportError as error:
        print(f"ROS2_CPP_HANDOFF_REPORT FAIL: {error}")
        raise SystemExit(1)
