#!/usr/bin/env python3
"""Validate the exact-subject limit registry without modifying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.limits import LimitRegistryError, validate_registry  # noqa: E402


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LimitRegistryError(f"JSON root must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "registry",
        nargs="?",
        type=Path,
        default=ROOT / "assets/myactuator/limit_registry.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas/myactuator-limit-registry.schema.json",
    )
    args = parser.parse_args()
    registry = load(args.registry)
    validate_registry(registry, load(args.schema))
    print(
        "LIMIT_REGISTRY_OK "
        f"records={len(registry['records'])} "
        f"accepted_measured={registry['physical_admission']['accepted_measured_record_count']} "
        "motion=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, LimitRegistryError) as error:
        print(f"limit registry validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
