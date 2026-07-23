#!/usr/bin/env python3
"""Fail closed when the pinned offline schema test dependencies drift."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-test.txt"


def pinned_requirements() -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(
        REQUIREMENTS.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise ValueError(
                f"{REQUIREMENTS}:{line_number}: expected one exact name==version pin"
            )
        name, expected = line.split("==", 1)
        if not name or not expected or name in result:
            raise ValueError(
                f"{REQUIREMENTS}:{line_number}: invalid or duplicate requirement"
            )
        result[name] = expected
    if not result:
        raise ValueError(f"{REQUIREMENTS}: no dependencies are pinned")
    return result


def main() -> int:
    failures: list[str] = []
    pins = pinned_requirements()
    for name, expected in sorted(pins.items()):
        try:
            actual = version(name)
        except PackageNotFoundError:
            failures.append(f"{name}: missing (expected {expected})")
            continue
        if actual != expected:
            failures.append(f"{name}: installed {actual}, expected {expected}")
    if failures:
        for failure in failures:
            print(f"TEST_DEPENDENCY_ERROR {failure}")
        return 1
    rendered = " ".join(f"{name}={pins[name]}" for name in sorted(pins))
    print(f"TEST_DEPENDENCIES_OK {rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
