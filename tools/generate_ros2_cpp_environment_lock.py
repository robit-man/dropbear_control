#!/usr/bin/env python3
"""Generate or verify the exact nonphysical ROS 2 C++ build lock."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "tools/ros2-cpp-environment-lock.json"
SCHEMA_PATH = ROOT / "schemas/ros2-cpp-environment-lock.schema.json"
ZERO_SHA256 = "0" * 64

PACKAGE_NAMES = (
    "python3-colcon-core",
    "ros-jazzy-ament-cmake",
    "ros-jazzy-class-loader",
    "ros-jazzy-controller-manager",
    "ros-jazzy-hardware-interface",
    "ros-jazzy-pluginlib",
    "ros-jazzy-rclcpp",
    "ros-jazzy-rclcpp-lifecycle",
    "ros-jazzy-ros2-control",
)
ABI_ARTIFACTS = (
    ("class-loader-abi", Path("/opt/ros/jazzy/lib/libclass_loader.so")),
    ("hardware-interface-abi", Path("/opt/ros/jazzy/lib/libhardware_interface.so")),
    ("rclcpp-abi", Path("/opt/ros/jazzy/lib/librclcpp.so")),
    ("rclcpp-lifecycle-abi", Path("/opt/ros/jazzy/lib/librclcpp_lifecycle.so")),
)
API_HEADERS = (
    (
        "hardware-component-interface-api",
        Path(
            "/opt/ros/jazzy/include/hardware_interface/hardware_interface/"
            "hardware_component_interface.hpp"
        ),
    ),
    (
        "pluginlib-export-api",
        Path("/opt/ros/jazzy/include/pluginlib/pluginlib/class_list_macros.hpp"),
    ),
    (
        "system-interface-api",
        Path(
            "/opt/ros/jazzy/include/hardware_interface/hardware_interface/"
            "system_interface.hpp"
        ),
    ),
)


class EnvironmentLockError(RuntimeError):
    """The exact ROS 2 build environment is unavailable or has drifted."""


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(role: str, path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EnvironmentLockError(f"required artifact is unavailable: {path}")
    return {
        "role": role,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def command(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise EnvironmentLockError(f"command failed: {' '.join(arguments)}") from error
    return completed.stdout.strip()


def package_versions() -> list[dict[str, str]]:
    result = []
    for name in PACKAGE_NAMES:
        version = command("dpkg-query", "-W", "-f=${Version}", name)
        result.append({"name": name, "version": version})
    return result


def tool(path: Path, version: str) -> dict[str, Any]:
    if not path.is_file():
        raise EnvironmentLockError(f"required tool is unavailable: {path}")
    return {
        "path": str(path),
        "version": version,
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip('"')
    return result


def record_digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = ZERO_SHA256
    return hashlib.sha256(canonical(payload)).hexdigest()


def snapshot() -> dict[str, Any]:
    release = os_release()
    libc_name, libc_version = platform.libc_ver()
    compiler = Path("/usr/bin/x86_64-linux-gnu-g++-13")
    cmake = Path("/usr/bin/cmake")
    colcon = Path("/usr/bin/colcon")
    python = Path("/usr/bin/python3.12")
    value: dict[str, Any] = {
        "schema_version": "ros2-cpp-environment-lock/1",
        "lock_id": "dropbear-ros2-jazzy-cpp-linux-x86-64",
        "authority": "offline_nonphysical_build_environment_only",
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "os_id": release.get("ID", ""),
            "os_version_id": release.get("VERSION_ID", ""),
            "libc_name": libc_name,
            "libc_version": libc_version,
        },
        "toolchain": {
            "compiler": tool(
                compiler,
                command(str(compiler), "--version").splitlines()[0],
            ),
            "cmake": tool(
                cmake,
                command(str(cmake), "--version").splitlines()[0],
            ),
            "colcon": tool(
                colcon,
                package_versions()[0]["version"],
            ),
            "python": tool(
                python,
                command(str(python), "--version"),
            ),
        },
        "debian_packages": package_versions(),
        "abi_artifacts": [artifact(role, path) for role, path in ABI_ARTIFACTS],
        "api_headers": [artifact(role, path) for role, path in API_HEADERS],
        "build_profile": {
            "ros_distro": "jazzy",
            "ros_prefix": "/opt/ros/jazzy",
            "cxx_standard": 17,
            "build_type": "RelWithDebInfo",
            "python_executable": "/usr/bin/python3",
            "physical_hardware_required": False,
        },
        "claims": {
            "cpp_handoff_build_environment": True,
            "physical_adapter_present": False,
            "canonical_dropbear_admitted": False,
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_io": False,
        },
        "integrity": {"record_sha256": ZERO_SHA256},
    }
    value["integrity"]["record_sha256"] = record_digest(value)
    return value


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
        raise EnvironmentLockError(
            f"schema failure at /{location}: {error.message}"
        )
    if value["integrity"]["record_sha256"] != record_digest(value):
        raise EnvironmentLockError("environment lock record digest mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()

    current = snapshot()
    validate(current)
    if arguments.write:
        temporary = LOCK_PATH.with_suffix(".json.tmp")
        temporary.write_bytes(json.dumps(current, indent=2).encode("utf-8") + b"\n")
        os.replace(temporary, LOCK_PATH)
        print(
            f"ROS2_CPP_ENVIRONMENT_LOCK_WRITE PASS "
            f"packages={len(current['debian_packages'])} "
            f"abi={len(current['abi_artifacts'])} "
            f"headers={len(current['api_headers'])}"
        )
        return 0

    try:
        tracked = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EnvironmentLockError(f"cannot read tracked lock: {error}") from error
    validate(tracked)
    if tracked != current:
        raise EnvironmentLockError("installed environment differs from exact tracked lock")
    print(
        f"ROS2_CPP_ENVIRONMENT_LOCK_CHECK PASS "
        f"packages={len(current['debian_packages'])} "
        f"abi={len(current['abi_artifacts'])} "
        f"headers={len(current['api_headers'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EnvironmentLockError as error:
        print(f"ROS2_CPP_ENVIRONMENT_LOCK FAIL: {error}")
        raise SystemExit(1)
