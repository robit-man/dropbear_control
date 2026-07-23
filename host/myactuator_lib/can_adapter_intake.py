"""Exact CAN adapter manifest intake with a fail-closed physical factory."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS = ROOT / "generated/can_adapter_intake/status.json"
DEFAULT_STATUS_SCHEMA = ROOT / "schemas/can-adapter-intake-status.schema.json"
DEFAULT_MANIFEST_SCHEMA = ROOT / "schemas/can-adapter-manifest.schema.json"


class AdapterAdmissionError(ValueError):
    pass


class PhysicalAdapterFactoryDisabled(AdapterAdmissionError):
    pass


class AdapterPurpose(str, Enum):
    LISTEN_ONLY_CAPTURE = "listen_only_capture"
    RUNTIME_GATEWAY = "runtime_gateway"


class ControllerKind(str, Enum):
    ESP32_TWAI = "esp32_twai"
    MCP2515 = "mcp2515"


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_bytes(value: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterAdmissionError(f"cannot decode {label}: {error}") from error
    if not isinstance(parsed, dict):
        raise AdapterAdmissionError(f"{label} root must be an object")
    return parsed


def _load(path: Path) -> dict[str, Any]:
    try:
        return _load_bytes(path.read_bytes(), str(path))
    except OSError as error:
        raise AdapterAdmissionError(f"cannot read {path}: {error}") from error


def _schema(
    value: dict[str, Any], schema: dict[str, Any], label: str
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise AdapterAdmissionError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def _digest(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return _sha(_canonical(payload))


def _manifest_id(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("manifest_id", None)
    payload.pop("integrity", None)
    return "canadapter-" + _sha(_canonical(payload))[:20]


def _resolve(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise AdapterAdmissionError("CAN adapter evidence path escapes root") from error
    return path


def _validate_manifest_semantics(
    manifest: dict[str, Any], canonical_configuration_digest: str
) -> None:
    if (
        manifest["subject"]["canonical_configuration_digest"]
        != canonical_configuration_digest
    ):
        raise AdapterAdmissionError("adapter manifest configuration drift")
    hardware = manifest["hardware"]
    pins = hardware["pins"]
    used = [pin for pin in pins.values() if pin is not None]
    if len(used) != len(set(used)):
        raise AdapterAdmissionError("adapter manifest GPIO overlap")
    if hardware["controller_kind"] == "esp32_twai":
        valid_tuple = (
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
            and manifest["firmware"]["driver_id"] == "esp-idf-twai"
        )
    else:
        valid_tuple = (
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
            and manifest["firmware"]["driver_id"] == "autowp-mcp2515"
        )
    if not valid_tuple:
        raise AdapterAdmissionError("adapter controller/connection/driver tuple drift")
    timing = manifest["timing"]
    quanta = (
        timing["sync_segment_tq"]
        + timing["time_segment_1_tq"]
        + timing["time_segment_2_tq"]
    )
    bitrate = timing["controller_clock_hz"] / (
        timing["clock_divider"] * quanta
    )
    sample = (
        100.0
        * (timing["sync_segment_tq"] + timing["time_segment_1_tq"])
        / quanta
    )
    error_ppm = (
        1_000_000.0
        * abs(bitrate - timing["target_bitrate_hz"])
        / timing["target_bitrate_hz"]
    )
    if not (
        timing["controller_clock_hz"] == hardware["controller_clock_hz"]
        and timing["total_time_quanta"] == quanta
        and math.isclose(
            timing["calculated_bitrate_hz"], bitrate, rel_tol=0, abs_tol=1e-9
        )
        and math.isclose(
            timing["sample_point_percent"], sample, rel_tol=0, abs_tol=1e-9
        )
        and math.isclose(
            timing["bitrate_error_ppm"], error_ppm, rel_tol=0, abs_tol=1e-9
        )
        and timing["sjw_tq"] <= timing["time_segment_2_tq"]
    ):
        raise AdapterAdmissionError("adapter timing calculation drift")
    disable = manifest["tx_disable"]
    if disable["independent_disable_mechanism"] == "transceiver_standby":
        disable_valid = (
            pins["transceiver_standby_gpio"] is not None
            and disable["independent_disable_control_gpio"]
            == pins["transceiver_standby_gpio"]
        )
    else:
        disable_valid = disable["independent_disable_control_gpio"] is None
    queues = manifest["queues_and_time"]
    if manifest["purpose"] == "listen_only_capture":
        purpose_valid = (
            disable["controller_operating_mode"] == "listen_only"
            and disable["controller_enforced_listen_only"] is True
            and queues["tx_queue_depth"] == 0
        )
    else:
        purpose_valid = (
            disable["controller_operating_mode"] == "normal"
            and disable["controller_enforced_listen_only"] is False
            and queues["tx_queue_depth"] > 0
        )
    error_policy = manifest["error_state_policy"]
    if not (
        disable_valid
        and purpose_valid
        and error_policy["warning_threshold"]
        < error_policy["passive_threshold"]
        < error_policy["bus_off_threshold"]
    ):
        raise AdapterAdmissionError(
            "adapter purpose/TX-disable/error policy drift"
        )


@dataclass(frozen=True)
class NoIoAdapterDescriptor:
    manifest_id: str
    purpose: AdapterPurpose
    controller_kind: ControllerKind
    controller_part_number: str
    board_model: str
    transceiver_part_number: str
    target_bitrate_hz: int
    sample_point_percent: float
    independent_tx_disable: str
    physical_io: bool = False
    support_granted: bool = False
    physical_motion_authority: bool = False


class CanAdapterIntakeRegistry:
    """Reviewed manifest inventory; it never selects or instantiates I/O."""

    def __init__(
        self,
        status: dict[str, Any],
        status_schema: dict[str, Any],
        manifest_schema: dict[str, Any],
        manifest_bytes_by_path: Mapping[str, bytes],
        manifest_schema_bytes: bytes,
    ):
        _schema(status, status_schema, "CAN adapter intake status")
        if (
            status["integrity"]["record_sha256"] != _digest(status)
            or status["source"]["manifest_schema_sha256"]
            != _sha(manifest_schema_bytes)
            or status["selected_listen_only_manifest_id"] is not None
            or status["selected_runtime_manifest_id"] is not None
            or status["support_granted"]
            or status["physical_motion_authority"]
            or status["physical_factory_enabled"]
        ):
            raise AdapterAdmissionError(
                "CAN adapter intake source/digest/selection/authority drift"
            )
        manifests: dict[str, dict[str, Any]] = {}
        for entry in status["manifests"]:
            path = entry["path"]
            if path not in manifest_bytes_by_path:
                raise AdapterAdmissionError(
                    f"missing CAN adapter manifest evidence: {path}"
                )
            manifest = _load_bytes(
                manifest_bytes_by_path[path], f"CAN adapter manifest {path}"
            )
            _schema(manifest, manifest_schema, "CAN adapter manifest")
            _validate_manifest_semantics(
                manifest, status["source"]["canonical_configuration_digest"]
            )
            manifest_id = manifest["manifest_id"]
            if (
                manifest_id in manifests
                or manifest_id != entry["manifest_id"]
                or manifest_id != _manifest_id(manifest)
                or manifest["integrity"]["record_sha256"] != _digest(manifest)
                or _sha(_canonical(manifest)) != entry["sha256"]
                or manifest["purpose"] != entry["purpose"]
                or manifest["hardware"]["controller_kind"]
                != entry["controller_kind"]
                or manifest["subject"]["installed_inventory_submission_id"]
                != entry["installed_inventory_submission_id"]
                or entry["selected"]
                or manifest["support_granted"]
                or manifest["physical_motion_authority"]
                or manifest["physical_io_enabled"]
            ):
                raise AdapterAdmissionError(
                    "CAN adapter manifest/status identity drift"
                )
            manifests[manifest_id] = manifest
        entries = status["manifests"]
        expected_summary = {
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
        if status["summary"] != expected_summary:
            raise AdapterAdmissionError("CAN adapter intake summary drift")
        self._status = copy.deepcopy(status)
        self._manifests = manifests

    @classmethod
    def load(
        cls,
        status_path: Path = DEFAULT_STATUS,
        status_schema_path: Path = DEFAULT_STATUS_SCHEMA,
        manifest_schema_path: Path = DEFAULT_MANIFEST_SCHEMA,
        root: Path = ROOT,
    ) -> "CanAdapterIntakeRegistry":
        status = _load(status_path)
        try:
            schema_bytes = manifest_schema_path.read_bytes()
            manifest_bytes = {
                entry["path"]: _resolve(root, entry["path"]).read_bytes()
                for entry in status.get("manifests", [])
            }
        except OSError as error:
            raise AdapterAdmissionError(
                f"cannot read CAN adapter intake evidence: {error}"
            ) from error
        return cls(
            status,
            _load(status_schema_path),
            _load_bytes(schema_bytes, "CAN adapter manifest schema"),
            manifest_bytes,
            schema_bytes,
        )

    @property
    def reviewed_manifest_count(self) -> int:
        return len(self._manifests)

    @property
    def physical_factory_enabled(self) -> bool:
        return False

    @property
    def support_granted(self) -> bool:
        return False

    @property
    def physical_motion_authority(self) -> bool:
        return False

    def describe_no_io(
        self, manifest_id: str, purpose: AdapterPurpose
    ) -> NoIoAdapterDescriptor:
        if not isinstance(purpose, AdapterPurpose):
            raise AdapterAdmissionError("adapter purpose is not exact")
        try:
            manifest = self._manifests[manifest_id]
        except KeyError as error:
            raise AdapterAdmissionError(
                f"unknown exact CAN adapter manifest: {manifest_id}"
            ) from error
        if manifest["purpose"] != purpose.value:
            raise AdapterAdmissionError(
                "CAN adapter manifest purpose cannot substitute"
            )
        return NoIoAdapterDescriptor(
            manifest_id=manifest_id,
            purpose=purpose,
            controller_kind=ControllerKind(
                manifest["hardware"]["controller_kind"]
            ),
            controller_part_number=manifest["hardware"][
                "controller_part_number"
            ],
            board_model=manifest["hardware"]["board_model"],
            transceiver_part_number=manifest["hardware"][
                "transceiver_part_number"
            ],
            target_bitrate_hz=manifest["timing"]["target_bitrate_hz"],
            sample_point_percent=manifest["timing"]["sample_point_percent"],
            independent_tx_disable=manifest["tx_disable"][
                "independent_disable_mechanism"
            ],
        )

    def create_physical(
        self, manifest_id: str, purpose: AdapterPurpose
    ) -> None:
        self.describe_no_io(manifest_id, purpose)
        raise PhysicalAdapterFactoryDisabled(
            "physical CAN adapter factory is disabled; reviewed manifest "
            "inventory does not authorize or implement I/O"
        )


__all__ = [
    "AdapterAdmissionError",
    "AdapterPurpose",
    "CanAdapterIntakeRegistry",
    "ControllerKind",
    "NoIoAdapterDescriptor",
    "PhysicalAdapterFactoryDisabled",
]
