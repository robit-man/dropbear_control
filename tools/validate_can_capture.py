#!/usr/bin/env python3
"""Validate an append-only, lossless, listen-only CAN JSONL capture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.can_capture import CaptureValidationError, validate_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    try:
        summary = validate_jsonl(args.capture)
    except (CaptureValidationError, OSError) as error:
        print(f"CAN_CAPTURE_INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary.to_dict(), sort_keys=True))
    print("CAN_CAPTURE_VALID_LISTEN_ONLY_NO_APPLICABILITY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
