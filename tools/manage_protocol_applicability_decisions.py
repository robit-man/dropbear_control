#!/usr/bin/env python3
"""Create and validate exact-tuple protocol applicability review records."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.protocol_applicability import (  # noqa: E402
    ProtocolApplicabilityRegistry,
)
from myactuator_lib.protocol_applicability_decision import (  # noqa: E402
    ProtocolApplicabilityDecisionError,
    canonical_bytes,
    load_directory,
    template,
    validate,
)


REGISTRY = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
DECISION_DIRECTORY = (
    ROOT / "assets/myactuator/protocol_applicability/decisions"
)


class ProtocolDecisionManagerError(ValueError):
    """The registry selection or requested manager action is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolDecisionManagerError(message)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def load_registry() -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    ProtocolApplicabilityRegistry.load()
    try:
        value = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolDecisionManagerError(
            f"cannot load applicability registry: {error}"
        ) from error
    return (
        value,
        {item["model_key"]: item for item in value["models"]},
        {
            item["occurrence_id"]: item
            for item in value["document_file_occurrences"]
        },
        {
            item["package_id"]: item
            for item in value["document_packages"]
        },
    )


def selected_records(
    model_key: str,
    occurrence_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _, models, occurrences, packages = load_registry()
    model = models.get(model_key)
    occurrence = occurrences.get(occurrence_id)
    require(model is not None, "exact model key is not registered")
    require(occurrence is not None, "protocol occurrence ID is not registered")
    require(
        occurrence_id in model["candidate_protocol_occurrence_ids"],
        "protocol occurrence is not a candidate for the exact model",
    )
    package = packages[occurrence["package_id"]]
    return model, occurrence, package


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolDecisionManagerError(f"cannot load {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def validate_file(path: Path) -> dict[str, Any]:
    value = load_json(path)
    subject = value.get("subject")
    require(isinstance(subject, dict), "decision subject is missing")
    model, occurrence, package = selected_records(
        subject.get("model_key", ""),
        subject.get("protocol_occurrence_id", ""),
    )
    validate(value, model, occurrence, package)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write-template", type=Path)
    mode.add_argument("--validate", type=Path)
    mode.add_argument("--check-directory", action="store_true")
    parser.add_argument("--model-key")
    parser.add_argument("--protocol-occurrence-id")
    parser.add_argument("--hardware-revision")
    parser.add_argument("--drive-firmware")
    parser.add_argument("--installed-unit-id")
    parser.add_argument(
        "--transport",
        choices=("classic_can", "ethercat", "rs485"),
    )
    parser.add_argument("--control-mode")
    args = parser.parse_args()
    try:
        if args.write_template is not None:
            required = {
                "model_key": args.model_key,
                "protocol_occurrence_id": args.protocol_occurrence_id,
                "hardware_revision": args.hardware_revision,
                "drive_firmware": args.drive_firmware,
                "installed_unit_id": args.installed_unit_id,
                "transport": args.transport,
                "control_mode": args.control_mode,
            }
            missing = sorted(key for key, value in required.items() if not value)
            require(not missing, f"template fields missing: {','.join(missing)}")
            model, occurrence, package = selected_records(
                args.model_key,
                args.protocol_occurrence_id,
            )
            value = template(
                model,
                occurrence,
                package,
                hardware_revision=args.hardware_revision,
                drive_firmware=args.drive_firmware,
                installed_unit_id=args.installed_unit_id,
                transport=args.transport,
                control_mode=args.control_mode,
            )
            atomic_write(args.write_template, canonical_bytes(value))
            print(
                "PROTOCOL_APPLICABILITY_TEMPLATE_OK "
                f"decision={value['decision_id']} "
                f"model={model['series']}/{model['model']} "
                "support=0 physical=0"
            )
            return 0
        if args.validate is not None:
            value = validate_file(args.validate)
            print(
                "PROTOCOL_APPLICABILITY_DECISION_OK "
                f"decision={value['decision_id']} "
                f"state={value['record_state']} "
                f"review={value['review']['status']} "
                f"established={int(value['applicability_established'])} "
                "support=0 physical=0"
            )
            return 0
        _, models, occurrences, packages = load_registry()
        decisions, hashes = load_directory(
            DECISION_DIRECTORY,
            models,
            occurrences,
            packages,
        )
        accepted = sum(
            value["review"]["status"] == "accepted" for value in decisions
        )
        print(
            "PROTOCOL_APPLICABILITY_DECISIONS_OK "
            f"submitted={len(decisions)} accepted={accepted} "
            f"files={len(hashes)} support=0 physical=0"
        )
        return 0
    except (
        ProtocolApplicabilityDecisionError,
        ProtocolDecisionManagerError,
        ValueError,
    ) as error:
        print(f"PROTOCOL_APPLICABILITY_DECISION_ERROR {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
