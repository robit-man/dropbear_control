#!/usr/bin/env python3
"""Validate exact CAN adapter manifests and generate a neutral intake status."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "schemas/examples/dropbear-observed-incomplete.json"
MANIFEST_SCHEMA = ROOT / "schemas/can-adapter-manifest.schema.json"
STATUS_SCHEMA = ROOT / "schemas/can-adapter-intake-status.schema.json"
INTAKE_ROOT = ROOT / "assets/dropbear/can_adapter_manifests"
SUBMISSIONS = INTAKE_ROOT / "submissions"
STATUS = ROOT / "generated/can_adapter_intake/status.json"
AUTOMATION_IDENTIFIERS = (
    "automated",
    "automation",
    "codex",
    "generator",
    "same-agent",
    "self-review",
    "language-model",
    " llm",
)


class AdapterIntakeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdapterIntakeError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterIntakeError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def schema_validate(value: dict[str, Any], path: Path, label: str) -> None:
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise AdapterIntakeError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def identity_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload.pop("manifest_id", None)
    payload.pop("integrity", None)
    return canonical_bytes(payload)


def expected_manifest_id(value: dict[str, Any]) -> str:
    return "canadapter-" + sha_bytes(identity_payload(value))[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def configuration_digest() -> str:
    config = load(CONFIG)
    digest = config["configuration_integrity"]["digest"]
    require(
        config["configuration_id"] == "dropbear-prototype-observation"
        and isinstance(digest, str)
        and len(digest) == 64,
        "adapter intake configuration baseline drift",
    )
    return digest


def validate_manifest(value: dict[str, Any]) -> None:
    schema_validate(value, MANIFEST_SCHEMA, "CAN adapter manifest")
    require(
        value["manifest_id"] == expected_manifest_id(value)
        and value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "CAN adapter manifest ID/digest mismatch",
    )
    require(
        value["subject"]["canonical_configuration_digest"]
        == configuration_digest(),
        "CAN adapter manifest configuration digest drift",
    )
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False
        and value["physical_io_enabled"] is False,
        "CAN adapter manifest grants support/motion/I/O",
    )
    review = value["review"]
    identity = (
        f"{review['reviewer_id']} {review['organization_or_team']}"
    ).casefold()
    require(
        not any(token in identity for token in AUTOMATION_IDENTIFIERS),
        "CAN adapter reviewer cannot be automation/self-review",
    )
    try:
        reviewed = dt.datetime.fromisoformat(
            review["reviewed_at"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise AdapterIntakeError("CAN adapter review time is invalid") from error
    require(
        reviewed.tzinfo is not None
        and reviewed.utcoffset() == dt.timedelta(0),
        "CAN adapter review time is not UTC",
    )

    hardware = value["hardware"]
    pins = hardware["pins"]
    used_pins = [pin for pin in pins.values() if pin is not None]
    require(len(used_pins) == len(set(used_pins)), "CAN adapter GPIOs overlap")
    if hardware["controller_kind"] == "esp32_twai":
        require(
            hardware["connection_kind"] == "integrated_peripheral"
            and pins["can_tx_gpio"] is not None
            and pins["can_rx_gpio"] is not None
            and all(
                pins[name] is None
                for name in (
                    "spi_sck_gpio",
                    "spi_mosi_gpio",
                    "spi_miso_gpio",
                    "spi_chip_select_gpio",
                    "interrupt_gpio",
                )
            )
            and value["firmware"]["driver_id"] == "esp-idf-twai",
            "TWAI manifest connection/pin/driver tuple drift",
        )
    else:
        require(
            hardware["connection_kind"] == "spi"
            and pins["can_tx_gpio"] is None
            and pins["can_rx_gpio"] is None
            and all(
                pins[name] is not None
                for name in (
                    "spi_sck_gpio",
                    "spi_mosi_gpio",
                    "spi_miso_gpio",
                    "spi_chip_select_gpio",
                    "interrupt_gpio",
                )
            )
            and value["firmware"]["driver_id"] == "autowp-mcp2515",
            "MCP2515 manifest connection/pin/driver tuple drift",
        )

    timing = value["timing"]
    require(
        timing["controller_clock_hz"] == hardware["controller_clock_hz"],
        "CAN timing/hardware clock disagreement",
    )
    expected_quanta = (
        timing["sync_segment_tq"]
        + timing["time_segment_1_tq"]
        + timing["time_segment_2_tq"]
    )
    expected_bitrate = timing["controller_clock_hz"] / (
        timing["clock_divider"] * expected_quanta
    )
    expected_sample = (
        100.0
        * (timing["sync_segment_tq"] + timing["time_segment_1_tq"])
        / expected_quanta
    )
    expected_error = (
        1_000_000.0
        * abs(expected_bitrate - timing["target_bitrate_hz"])
        / timing["target_bitrate_hz"]
    )
    require(
        timing["total_time_quanta"] == expected_quanta
        and math.isclose(
            timing["calculated_bitrate_hz"],
            expected_bitrate,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and math.isclose(
            timing["sample_point_percent"],
            expected_sample,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and math.isclose(
            timing["bitrate_error_ppm"],
            expected_error,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and timing["sjw_tq"] <= timing["time_segment_2_tq"]
        and expected_error <= 5000.0,
        "CAN timing calculation/sample/SJW/error drift",
    )

    tx_disable = value["tx_disable"]
    if tx_disable["independent_disable_mechanism"] == "transceiver_standby":
        require(
            pins["transceiver_standby_gpio"] is not None
            and tx_disable["independent_disable_control_gpio"]
            == pins["transceiver_standby_gpio"],
            "transceiver-standby disable GPIO drift",
        )
    else:
        require(
            tx_disable["independent_disable_control_gpio"] is None,
            "non-GPIO independent disable carries control GPIO",
        )
    queues = value["queues_and_time"]
    if value["purpose"] == "listen_only_capture":
        require(
            tx_disable["controller_operating_mode"] == "listen_only"
            and tx_disable["controller_enforced_listen_only"] is True
            and queues["tx_queue_depth"] == 0,
            "listen-only manifest is command/TX capable",
        )
    else:
        require(
            tx_disable["controller_operating_mode"] == "normal"
            and tx_disable["controller_enforced_listen_only"] is False
            and queues["tx_queue_depth"] > 0,
            "runtime manifest does not have exact normal/TX queue purpose",
        )

    error_policy = value["error_state_policy"]
    require(
        error_policy["warning_threshold"]
        < error_policy["passive_threshold"]
        < error_policy["bus_off_threshold"],
        "CAN error warning/passive/bus-off thresholds are not ordered",
    )


def owned_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = sorted(path for path in directory.iterdir() if path.is_file())
    require(
        all(path.suffix == ".json" for path in files),
        "CAN adapter intake contains non-JSON file",
    )
    return files


def path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"synthetic-fixture/submissions/{path.name}"


def status_digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return sha_bytes(canonical_bytes(payload))


def build(submissions: Path = SUBMISSIONS) -> dict[str, Any]:
    manifests: list[tuple[dict[str, Any], Path]] = []
    ids: set[str] = set()
    for path in owned_files(submissions):
        value = load(path)
        validate_manifest(value)
        require(
            path.name == f"{value['manifest_id']}.json",
            "CAN adapter manifest filename/ID mismatch",
        )
        require(
            value["manifest_id"] not in ids,
            "duplicate CAN adapter manifest ID",
        )
        ids.add(value["manifest_id"])
        manifests.append((value, path))
    manifests.sort(key=lambda row: row[0]["manifest_id"])
    entries = [
        {
            "manifest_id": value["manifest_id"],
            "path": path_label(path),
            "sha256": sha_bytes(canonical_bytes(value)),
            "purpose": value["purpose"],
            "controller_kind": value["hardware"]["controller_kind"],
            "installed_inventory_submission_id": value["subject"][
                "installed_inventory_submission_id"
            ],
            "selected": False,
        }
        for value, path in manifests
    ]
    counts = {
        "reviewed_manifest_count": len(entries),
        "twai_manifest_count": sum(
            row["controller_kind"] == "esp32_twai" for row in entries
        ),
        "mcp2515_manifest_count": sum(
            row["controller_kind"] == "mcp2515" for row in entries
        ),
        "listen_only_manifest_count": sum(
            row["purpose"] == "listen_only_capture" for row in entries
        ),
        "runtime_manifest_count": sum(
            row["purpose"] == "runtime_gateway" for row in entries
        ),
        "selected_listen_only_count": 0,
        "selected_runtime_count": 0,
    }
    value = {
        "schema_version": "can-adapter-intake-status/1",
        "artifact_id": "dropbear-can-adapter-intake-status",
        "authority": "reviewed_manifest_inventory_only",
        "source": {
            "canonical_configuration_digest": configuration_digest(),
            "manifest_schema_path": MANIFEST_SCHEMA.relative_to(ROOT).as_posix(),
            "manifest_schema_sha256": sha_bytes(MANIFEST_SCHEMA.read_bytes()),
        },
        "manifests": entries,
        "selected_listen_only_manifest_id": None,
        "selected_runtime_manifest_id": None,
        "summary": counts,
        "blockers": [
            "installed_controller_inventory_not_submitted",
            "listen_only_adapter_selection_decision_missing",
            "runtime_adapter_selection_decision_missing",
            "physical_adapter_factory_disabled",
            "physical_authorization_missing",
        ],
        "support_granted": False,
        "physical_motion_authority": False,
        "physical_factory_enabled": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    value["integrity"]["record_sha256"] = status_digest(value)
    validate_status(value)
    return value


def validate_status(value: dict[str, Any]) -> None:
    schema_validate(value, STATUS_SCHEMA, "CAN adapter intake status")
    require(
        value["source"]
        == {
            "canonical_configuration_digest": configuration_digest(),
            "manifest_schema_path": MANIFEST_SCHEMA.relative_to(ROOT).as_posix(),
            "manifest_schema_sha256": sha_bytes(MANIFEST_SCHEMA.read_bytes()),
        }
        and value["integrity"]["record_sha256"] == status_digest(value),
        "CAN adapter intake source/status digest drift",
    )
    entries = value["manifests"]
    require(
        len({row["manifest_id"] for row in entries}) == len(entries)
        and all(row["selected"] is False for row in entries)
        and value["selected_listen_only_manifest_id"] is None
        and value["selected_runtime_manifest_id"] is None,
        "CAN adapter intake silently selects a manifest",
    )
    expected = {
        "reviewed_manifest_count": len(entries),
        "twai_manifest_count": sum(
            row["controller_kind"] == "esp32_twai" for row in entries
        ),
        "mcp2515_manifest_count": sum(
            row["controller_kind"] == "mcp2515" for row in entries
        ),
        "listen_only_manifest_count": sum(
            row["purpose"] == "listen_only_capture" for row in entries
        ),
        "runtime_manifest_count": sum(
            row["purpose"] == "runtime_gateway" for row in entries
        ),
        "selected_listen_only_count": 0,
        "selected_runtime_count": 0,
    }
    require(value["summary"] == expected, "CAN adapter intake summary drift")
    require(
        value["support_granted"] is False
        and value["physical_motion_authority"] is False
        and value["physical_factory_enabled"] is False,
        "CAN adapter intake grants support/motion/physical factory",
    )


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def generate() -> dict[str, Any]:
    value = build()
    atomic_write(STATUS, value)
    return value


def check() -> dict[str, Any]:
    value = build()
    require(
        STATUS.is_file() and STATUS.read_bytes() == canonical_bytes(value),
        "tracked CAN adapter intake status drift",
    )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--validate-manifest", type=Path)
    args = parser.parse_args()
    if args.validate_manifest:
        validate_manifest(load(args.validate_manifest.resolve()))
        print("CAN_ADAPTER_MANIFEST_OK support=false motion=false io=false")
        return 0
    value = generate() if args.generate else check()
    summary = value["summary"]
    print(
        "CAN_ADAPTER_INTAKE_OK "
        f"reviewed={summary['reviewed_manifest_count']} "
        f"twai={summary['twai_manifest_count']} "
        f"mcp2515={summary['mcp2515_manifest_count']} "
        "selected_listen=0 selected_runtime=0 "
        "support=false motion=false physical_factory=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, AdapterIntakeError, ValueError) as error:
        print(f"CAN adapter intake failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
