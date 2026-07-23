#!/usr/bin/env python3
"""Verify the isolated, platform-specific CAD conversion environment."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tools" / "cad-toolchain-lock.json"


class ToolchainError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.count("==") != 1:
            raise ToolchainError(f"unlocked requirement: {value}")
        name, version = value.split("==")
        key = normalized(name)
        if key in result:
            raise ToolchainError(f"duplicate requirement: {name}")
        result[key] = version
    return result


def validate_lock() -> tuple[dict, dict[str, str]]:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if lock.get("schema_version") != "myactuator-cad-toolchain/1":
        raise ToolchainError("toolchain schema version mismatch")
    packages = lock["packages"]
    requirements_path = ROOT / packages["requirements_lock"]
    wheel_path = ROOT / packages["wheel_lock"]
    if sha256(requirements_path) != packages["requirements_lock_sha256"]:
        raise ToolchainError("CAD requirements lock hash mismatch")
    if sha256(wheel_path) != packages["wheel_lock_sha256"]:
        raise ToolchainError("CAD wheel lock hash mismatch")

    required = requirements(requirements_path)
    with wheel_path.open(newline="", encoding="utf-8") as stream:
        wheel_rows = list(csv.DictReader(stream, delimiter="\t"))
    if set(wheel_rows[0]) != {"filename", "sha256", "bytes"}:
        raise ToolchainError("wheel lock columns mismatch")
    if len(wheel_rows) != packages["wheel_count"] or len(wheel_rows) != len(required):
        raise ToolchainError("wheel/requirement count mismatch")
    filenames = [row["filename"] for row in wheel_rows]
    if len(filenames) != len(set(filenames)):
        raise ToolchainError("duplicate wheel filename")
    for row in wheel_rows:
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ToolchainError(f"invalid wheel SHA-256: {row['filename']}")
        if int(row["bytes"]) <= 0:
            raise ToolchainError(f"invalid wheel size: {row['filename']}")
    return lock, required


def validate_environment(lock: dict, required: dict[str, str]) -> None:
    environment = lock["environment"]
    if f"{sys.version_info.major}.{sys.version_info.minor}" != environment["python_major_minor"]:
        raise ToolchainError("Python major/minor differs from CAD lock")
    if platform.system() != environment["operating_system"]:
        raise ToolchainError("operating system differs from CAD lock")
    if platform.machine() != environment["machine"]:
        raise ToolchainError("machine differs from CAD lock")
    installed = {
        normalized(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    mismatches = {
        name: (version, installed.get(name))
        for name, version in required.items()
        if installed.get(name) != version
    }
    if mismatches:
        raise ToolchainError(f"installed CAD packages differ from lock: {mismatches}")

    import cadquery
    import OCP

    if cadquery.__version__ != required["cadquery"]:
        raise ToolchainError("CadQuery runtime version mismatch")
    if OCP.__version__ != lock["kernel"]["occt_version"]:
        raise ToolchainError("OpenCascade runtime version mismatch")


def main() -> int:
    lock, required = validate_lock()
    validate_environment(lock, required)
    print(
        "CAD_TOOLCHAIN_OK "
        f"cadquery={required['cadquery']} occt={lock['kernel']['occt_version']} "
        f"wheels={lock['packages']['wheel_count']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ToolchainError, ValueError) as error:
        print(f"CAD toolchain validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)

