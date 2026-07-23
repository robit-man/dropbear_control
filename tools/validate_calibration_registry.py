#!/usr/bin/env python3
"""Validate an exact-subject calibration registry without changing it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.calibration import (  # noqa: E402
    CalibrationRegistryError,
    registry_digest,
    validate_registry,
)


DEFAULT_REGISTRY = ROOT / "assets/myactuator/calibration_registry.json"
DEFAULT_SCHEMA = ROOT / "schemas/myactuator-calibration-registry.schema.json"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CalibrationRegistryError(f"JSON root must be an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", nargs="?", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--print-computed-digest",
        action="store_true",
        help="print the canonical registry digest (validation still runs)",
    )
    arguments = parser.parse_args()
    registry = _load(arguments.registry)
    schema = _load(arguments.schema)
    validate_registry(registry, schema)
    if arguments.print_computed_digest:
        print(registry_digest(registry))
    else:
        print(
            "CALIBRATION_REGISTRY_OK "
            f"records={len(registry['records'])} "
            f"accepted_physical={registry['physical_admission']['accepted_physical_record_count']} "
            "motion=false"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, CalibrationRegistryError) as error:
        print(f"calibration registry validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
