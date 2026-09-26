"""Local ESP32 inventory, serial diagnostics, and guarded firmware tooling."""

from __future__ import annotations

import hashlib
import math
import os
import re
import select
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any



FIRMWARE_SCHEMA = "dropbear-esp32-devices-v3"
BOARD_FQBN = "esp32:esp32:esp32:PartitionScheme=huge_app,EraseFlash=none"
REQUIRED_ESP32_CORE_VERSION = "2.0.13"
REQUIRED_ESP32_CORE_PATCH = "uartSetPins-invalid-index-return-false-v1"
RAW_TAIL_LINES = 160
READ_ONLY_SERIAL_COMMANDS = frozenset({
    "version", "/version", "capabilities", "health", "status", "chirality",
    "mac", "saved", "help", "observe on", "observe off", "config show",
    "can bus", "can registers", "can scan",
    "can poll on", "can poll off", "can poll status",
})
REQUIRED_LIBRARY_VERSIONS = {
    "FastAccelStepper": "0.30.15",
    "MCP_CAN_lib": "1.5.1",
}
PARTITION_FILENAME = "partitions.csv"
PARTITION_LAYOUT = "dropbear-preserve-default-spiffs-v1"
APP_OFFSET = 0x10000
APP_SIZE = 0x280000
SPIFFS_OFFSET = 0x290000
SPIFFS_SIZE = 0x160000
PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0x1000
FIRMWARE_SUPPORT_FILES = {
    "firmware_full_libs_neck.ino": ("dropbear_motor_protocol.h",),
}


def _configure_115200(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = termios.IGNBRK
    attrs[1] = 0
    attrs[2] = (
        attrs[2] & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE | termios.HUPCL)
    ) | termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


class _RawSerialReader:
    def __init__(self, device_id: str, path: str) -> None:
        self.device_id = device_id
        self.path = path
        self.lines: deque[dict[str, Any]] = deque(maxlen=RAW_TAIL_LINES)
        self.state = "opening"
        self.error = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                resolved = os.path.realpath(self.path)
                if not stat.S_ISCHR(os.stat(resolved).st_mode):
                    raise OSError("serial path is not a character device")
                fd = os.open(
                    self.path,
                    os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC,
                )
                _configure_115200(fd)
                self.state = "observing"
                self.error = ""
            except (OSError, termios.error) as error:
                self.state = "reconnecting"
                self.error = str(error)
                self._stop.wait(0.5)
                continue
            buffer = bytearray()
            disconnected = False
            try:
                while not self._stop.is_set():
                    readable, _, _ = select.select([fd], [], [], 0.1)
                    if not readable:
                        continue
                    chunk = os.read(fd, 1024)
                    if not chunk:
                        raise OSError("serial device returned EOF")
                    buffer.extend(chunk)
                    if len(buffer) > 8192:
                        buffer.clear()
                        self.error = "serial receive buffer overflow"
                        continue
                    while b"\n" in buffer:
                        raw, _, remainder = buffer.partition(b"\n")
                        buffer = bytearray(remainder)
                        self.lines.append({
                            "receivedMonotonicNs": time.monotonic_ns(),
                            "direction": "rx",
                            "text": raw.rstrip(b"\r").decode("utf-8", errors="replace"),
                        })
            except (OSError, ValueError) as error:
                disconnected = True
                if not self._stop.is_set():
                    self.state = "reconnecting"
                    self.error = str(error)
            finally:
                os.close(fd)
            if disconnected:
                self._stop.wait(0.5)


class FirmwareToolError(ValueError):
    pass


class DeviceFirmwareManager:
    """Bounded local-only firmware compiler/uploader and passive serial inventory."""

    def __init__(self, project_root: Path, observation_manager: Any) -> None:
        self.project_root = project_root.resolve()
        self.observation_manager = observation_manager
        default_source = self.project_root.parent / "Dropbear" / "Control System" / "Low Level Control"
        self.source_root = Path(os.environ.get("DROPBEAR_FIRMWARE_ROOT", default_source)).resolve()
        self.arduino = Path(os.environ.get(
            "DROPBEAR_ARDUINO",
            "/home/robit/Downloads/arduino-1.8.19/arduino",
        )).resolve()
        self.sketchbook = Path(os.environ.get(
            "DROPBEAR_ARDUINO_SKETCHBOOK",
            self.project_root / ".cache" / "arduino-sketchbook",
        )).resolve()
        self.esp32_core_root = Path(os.environ.get(
            "DROPBEAR_ESP32_CORE_ROOT",
            Path.home() / ".arduino15" / "packages" / "esp32" / "hardware" / "esp32",
        )).resolve()
        default_esptool = next(iter(sorted(
            (Path.home() / ".arduino15" / "packages" / "esp32" / "tools" / "esptool_py").glob("*/esptool.py"),
            reverse=True,
        )), Path("/nonexistent/esptool.py"))
        self.esptool = Path(os.environ.get("DROPBEAR_ESPTOOL", default_esptool)).resolve()
        self.build_root = Path(tempfile.gettempdir()) / "dropbear-firmware-builds"
        self._lock = threading.RLock()
        self._aux_readers: dict[str, _RawSerialReader] = {}
        self._builds: dict[str, dict[str, Any]] = {}
        self.tx_bytes = 0

    @staticmethod
    def _device_id(path: Path) -> str:
        return hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]

    def _devices(self) -> list[dict[str, Any]]:
        observation = self.observation_manager.snapshot()
        role_by_resolved = {
            os.path.realpath(side["configuredPath"]): name
            for name, side in observation.get("sides", {}).items()
            if side.get("configuredPath")
        }
        devices = []
        root = Path("/dev/serial/by-path")
        for path in sorted(root.glob("*")) if root.exists() else []:
            resolved = os.path.realpath(path)
            role = role_by_resolved.get(resolved, "")
            if not role and "usb-0:1.4:" in path.name:
                role = "neck_candidate"
            devices.append({
                "id": self._device_id(path),
                "stablePath": str(path),
                "pathLabel": path.name,
                "resolvedPath": resolved,
                "tty": Path(resolved).name,
                "role": role or "unassigned",
                "connected": Path(resolved).exists(),
            })
        return devices

    def start(self) -> None:
        self._refresh_aux_readers()

    def stop(self) -> None:
        with self._lock:
            readers = list(self._aux_readers.values())
            self._aux_readers.clear()
        for reader in readers:
            reader.stop()

    def _refresh_aux_readers(self) -> None:
        for device in self._devices():
            if device["role"] in {"left", "right"} or not device["connected"]:
                continue
            with self._lock:
                if device["id"] in self._aux_readers:
                    continue
                reader = _RawSerialReader(device["id"], device["stablePath"])
                self._aux_readers[device["id"]] = reader
                reader.start()

    def _sources(self) -> list[dict[str, Any]]:
        if not self.source_root.is_dir():
            return []
        sources = []
        for path in sorted(self.source_root.glob("*.ino")):
            resolved = path.resolve()
            if resolved.parent != self.source_root:
                continue
            name = path.name
            bundle = self._source_bundle(path)
            digest = self._source_bundle_sha256(bundle)
            family = (
                "universal-behemoth"
                if name == "firmware_full_libs_neck.ino"
                else "hybrid-leg-pwm"
                if name == "esp32_devkitc_v4_hybrid.ino"
                else "observation-safe-migration"
                if name == "esp32_devkit_v1_observation_safe.ino"
                else "legacy-or-development"
            )
            interface = (
                "db3 + DB1 + guarded captive portal"
                if name == "firmware_full_libs_neck.ino"
                else "db2 observation only"
                if name == "esp32_devkit_v1_observation_safe.ino"
                else "db3 + legacy captive portal"
            )
            sources.append({
                "id": digest[:16],
                "filename": name,
                "family": family,
                "interface": interface,
                "bytes": sum(item.stat().st_size for item in bundle),
                "sha256": digest,
                "path": str(path.relative_to(self.source_root)),
                "supportFiles": [item.name for item in bundle[1:]],
            })
        return sources

    def _source_bundle(self, source_path: Path) -> list[Path]:
        files = [source_path]
        for filename in FIRMWARE_SUPPORT_FILES.get(source_path.name, ()):
            support = (self.source_root / filename).resolve()
            if support.parent != self.source_root or not support.is_file():
                raise FirmwareToolError(
                    f"required firmware support file is missing: {filename}"
                )
            files.append(support)
        return files

    @staticmethod
    def _source_bundle_sha256(files: list[Path]) -> str:
        digest = hashlib.sha256()
        for path in files:
            data = path.read_bytes()
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(len(data)).encode("ascii"))
            digest.update(b"\0")
            digest.update(data)
            digest.update(b"\0")
        return digest.hexdigest()

    def _library_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for name in REQUIRED_LIBRARY_VERSIONS:
            properties = self.sketchbook / "libraries" / name / "library.properties"
            if not properties.is_file():
                versions[name] = "missing"
                continue
            version = "unknown"
            for line in properties.read_text(errors="replace").splitlines():
                if line.startswith("version="):
                    version = line.partition("=")[2].strip()
                    break
            versions[name] = version
        return versions

    def _esp32_core_versions(self) -> list[str]:
        if not self.esp32_core_root.is_dir():
            return []
        return sorted(
            path.name
            for path in self.esp32_core_root.iterdir()
            if path.is_dir() and (path / "platform.txt").is_file()
        )

    @staticmethod
    def _toolchain_issues(versions: dict[str, str], core_versions: list[str]) -> list[str]:
        issues = [
            f"{name} requires {required}; found {versions.get(name, 'missing')}"
            for name, required in REQUIRED_LIBRARY_VERSIONS.items()
            if versions.get(name) != required
        ]
        if core_versions != [REQUIRED_ESP32_CORE_VERSION]:
            found = ", ".join(core_versions) if core_versions else "missing"
            issues.append(
                f"ESP32 Arduino core requires {REQUIRED_ESP32_CORE_VERSION} exclusively; found {found}"
            )
        return issues

    def _esp32_core_patch_issue(self) -> str:
        uart_source = (
            self.esp32_core_root / REQUIRED_ESP32_CORE_VERSION /
            "cores" / "esp32" / "esp32-hal-uart.c"
        )
        if not uart_source.is_file():
            return f"ESP32 core patch source is missing: {uart_source}"
        source = uart_source.read_text(errors="replace")
        start = source.find("bool uartSetPins(")
        end = source.find("bool uartSetHwFlowCtrlMode(", start)
        body = source[start:end] if start >= 0 and end > start else ""
        if "return false;" not in body or "return;" in body:
            return (
                f"ESP32 core {REQUIRED_ESP32_CORE_VERSION} requires patch "
                f"{REQUIRED_ESP32_CORE_PATCH}; run "
                "python3 tools/patch_esp32_core_2_0_13.py"
            )
        return ""

    def _partition_path(self) -> Path:
        return self.source_root / PARTITION_FILENAME

    @staticmethod
    def _partition_rows(path: Path) -> dict[str, tuple[int, int]]:
        if not path.is_file():
            raise FirmwareToolError(
                f"required {PARTITION_FILENAME} is missing from the trusted firmware directory"
            )
        rows: dict[str, tuple[int, int]] = {}
        for raw_line in path.read_text(errors="strict").splitlines():
            line = raw_line.partition("#")[0].strip()
            if not line:
                continue
            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 5:
                raise FirmwareToolError(f"invalid partition row: {raw_line}")
            try:
                rows[fields[0]] = (int(fields[3], 0), int(fields[4], 0))
            except ValueError as error:
                raise FirmwareToolError(f"invalid partition address in row: {raw_line}") from error
        return rows

    def _validated_partition(self) -> tuple[Path, str]:
        path = self._partition_path()
        rows = self._partition_rows(path)
        if rows.get("app0") != (APP_OFFSET, APP_SIZE):
            raise FirmwareToolError(
                "Dropbear application partition must be 0x10000 + 0x280000"
            )
        if rows.get("spiffs") != (SPIFFS_OFFSET, SPIFFS_SIZE):
            raise FirmwareToolError(
                "Dropbear SPIFFS partition must remain at 0x290000 + 0x160000"
            )
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _spiffs_from_partition_binary(data: bytes) -> tuple[int, int] | None:
        """Return the SPIFFS offset/size from an ESP-IDF binary partition table."""
        for cursor in range(0, len(data) - 31, 32):
            entry = data[cursor:cursor + 32]
            magic = struct.unpack_from("<H", entry)[0]
            if magic == 0xFFFF:
                break
            if magic != 0x50AA:
                continue
            _, partition_type, subtype, offset, size, raw_label, _ = struct.unpack(
                "<HBBII16sI", entry
            )
            label = raw_label.partition(b"\0")[0].decode("ascii", errors="replace")
            if partition_type == 0x01 and (subtype == 0x82 or label == "spiffs"):
                return offset, size
        return None

    def _verify_device_spiffs_layout(self, device: dict[str, Any]) -> dict[str, Any]:
        """Read only the target partition table and block an unsafe layout migration."""
        if not self.esptool.is_file():
            raise FirmwareToolError(
                "esptool is unavailable; refusing upload because SPIFFS preservation cannot be verified"
            )
        with tempfile.TemporaryDirectory(prefix="dropbear-partition-check-") as temporary:
            dump_path = Path(temporary) / "partition-table.bin"
            command = [
                sys.executable, str(self.esptool), "--chip", "esp32",
                "--port", device["stablePath"], "--baud", "115200",
                "read_flash", hex(PARTITION_TABLE_OFFSET), hex(PARTITION_TABLE_SIZE),
                str(dump_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            if result.returncode != 0 or not dump_path.is_file():
                output = (result.stdout + "\n" + result.stderr).strip()[-4000:]
                raise FirmwareToolError(
                    "could not read the ESP32 partition table; upload held to protect SPIFFS: " + output
                )
            discovered = self._spiffs_from_partition_binary(dump_path.read_bytes())
        if discovered is None:
            raise FirmwareToolError("target partition table has no SPIFFS entry; upload held")
        if discovered != (SPIFFS_OFFSET, SPIFFS_SIZE):
            raise FirmwareToolError(
                "target SPIFFS is "
                f"{hex(discovered[0])} + {hex(discovered[1])}; expected "
                f"{hex(SPIFFS_OFFSET)} + {hex(SPIFFS_SIZE)}. Upload held so saved settings are not stranded"
            )
        return {
            "layout": PARTITION_LAYOUT,
            "spiffsOffset": hex(discovered[0]),
            "spiffsSize": hex(discovered[1]),
            "verifiedReadOnly": True,
        }

    def snapshot(self) -> dict[str, Any]:
        self._refresh_aux_readers()
        observation = self.observation_manager.snapshot()
        sides = observation.get("sides", {})
        devices = self._devices()
        for device in devices:
            if device["role"] in sides:
                side = sides[device["role"]]
                device.update({
                    "serialState": side.get("state", "unknown"),
                    "rawTail": side.get("rawTail", []),
                    "firmware": side.get("firmware", {}),
                    "health": side.get("health", {}),
                    "fresh": side.get("fresh", False),
                    "ageMs": side.get("ageMs"),
                    "joints": side.get("joints", {}),
                    "motorJoints": side.get("motorJoints", {}),
                    "configuration": side.get("configuration", {}),
                    "calibration": side.get("calibration", {}),
                    "observationStreaming": side.get("observationStreaming", False),
                    "telemetryFormat": side.get("telemetryFormat", ""),
                    "decodedLines": side.get("decodedLines", 0),
                    "rejectedLines": side.get("rejectedLines", 0),
                })
            else:
                reader = self._aux_readers.get(device["id"])
                device.update({
                    "serialState": reader.state if reader else "not-monitored",
                    "rawTail": list(reader.lines) if reader else [],
                    "firmware": {"family": "unknown", "version": "", "detection": "passive-serial"},
                    "telemetryFormat": "",
                    "decodedLines": 0,
                    "rejectedLines": 0,
                    "error": reader.error if reader else "",
                })
        library_versions = self._library_versions()
        core_versions = self._esp32_core_versions()
        executable_available = self.arduino.is_file() and os.access(self.arduino, os.X_OK)
        dependency_issues = self._toolchain_issues(library_versions, core_versions)
        core_patch_issue = self._esp32_core_patch_issue()
        if core_patch_issue:
            dependency_issues.append(core_patch_issue)
        try:
            _, partition_sha256 = self._validated_partition()
            partition_issue = ""
        except FirmwareToolError as error:
            partition_sha256 = ""
            partition_issue = str(error)
            dependency_issues.append(partition_issue)
        return {
            "schema": FIRMWARE_SCHEMA,
            "baudrate": 115200,
            "devices": devices,
            "sources": self._sources(),
            "toolchain": {
                "arduino": str(self.arduino),
                "available": executable_available,
                "ready": executable_available and not dependency_issues,
                "board": BOARD_FQBN,
                "sketchbook": str(self.sketchbook),
                "requiredEsp32Core": REQUIRED_ESP32_CORE_VERSION,
                "requiredEsp32CorePatch": REQUIRED_ESP32_CORE_PATCH,
                "esp32CorePatchReady": not core_patch_issue,
                "esp32CoreVersions": core_versions,
                "requiredLibraries": dict(REQUIRED_LIBRARY_VERSIONS),
                "libraryVersions": library_versions,
                "issues": dependency_issues,
                "partitionLayout": PARTITION_LAYOUT,
                "partitionSha256": partition_sha256,
                "appOffset": hex(APP_OFFSET),
                "appSize": hex(APP_SIZE),
                "spiffsOffset": hex(SPIFFS_OFFSET),
                "spiffsSize": hex(SPIFFS_SIZE),
                "spiffsPreservedInPlace": not partition_issue,
            },
            "builds": list(self._builds.values())[-8:],
            "txBytes": self.tx_bytes,
            "uploadInterlock": "compile + exact device/source review + physical-safety acknowledgement + typed role phrase",
        }

    def _source(self, source_id: str) -> tuple[dict[str, Any], Path]:
        source = next((item for item in self._sources() if item["id"] == source_id), None)
        if source is None:
            raise FirmwareToolError("selected firmware source is not in the trusted source directory")
        path = (self.source_root / source["path"]).resolve()
        if path.parent != self.source_root or path.suffix.lower() != ".ino":
            raise FirmwareToolError("firmware source path escaped the trusted source directory")
        return source, path

    def _device(self, device_id: str) -> dict[str, Any]:
        device = next((item for item in self._devices() if item["id"] == device_id), None)
        if device is None or not device["connected"]:
            raise FirmwareToolError("selected stable serial device is not connected")
        return device

    def compile(self, source_id: str) -> dict[str, Any]:
        source, source_path = self._source(str(source_id))
        if not self.arduino.is_file():
            raise FirmwareToolError("Arduino 1.8.19 executable was not found")
        versions = self._library_versions()
        mismatches = self._toolchain_issues(versions, self._esp32_core_versions())
        core_patch_issue = self._esp32_core_patch_issue()
        if core_patch_issue:
            mismatches.append(core_patch_issue)
        if mismatches:
            raise FirmwareToolError("firmware toolchain dependency mismatch: " + "; ".join(mismatches))
        partition_path, partition_sha256 = self._validated_partition()
        build_id = uuid.uuid4().hex
        job_root = self.build_root / build_id
        sketch_dir = job_root / source_path.stem
        build_dir = job_root / "build"
        sketch_dir.mkdir(parents=True)
        build_dir.mkdir(parents=True)
        sketch_path = sketch_dir / f"{source_path.stem}.ino"
        shutil.copy2(source_path, sketch_path)
        support_files = self._source_bundle(source_path)[1:]
        for support_path in support_files:
            shutil.copy2(support_path, sketch_dir / support_path.name)
        build_partition_path = sketch_dir / PARTITION_FILENAME
        shutil.copy2(partition_path, build_partition_path)
        self.sketchbook.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.arduino), "--verify", "--board", BOARD_FQBN,
            "--pref", f"sketchbook.path={self.sketchbook}",
            "--pref", f"build.path={build_dir}",
            str(sketch_path),
        ]
        started = time.time()
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        output = (result.stdout + "\n" + result.stderr).strip()[-24000:]
        application_binary = build_dir / f"{source_path.stem}.ino.bin"
        binary_bytes = application_binary.stat().st_size if application_binary.is_file() else 0
        if result.returncode == 0 and not binary_bytes:
            result = subprocess.CompletedProcess(command, 1, result.stdout, result.stderr + "\napplication binary was not produced")
            output = (result.stdout + "\n" + result.stderr).strip()[-24000:]
        if result.returncode == 0 and binary_bytes > APP_SIZE:
            result = subprocess.CompletedProcess(
                command, 1, result.stdout,
                result.stderr + f"\napplication binary exceeds custom {hex(APP_SIZE)} partition",
            )
            output = (result.stdout + "\n" + result.stderr).strip()[-24000:]
        record = {
            "id": build_id,
            "sourceId": source["id"],
            "filename": source["filename"],
            "family": source["family"],
            "sha256": source["sha256"],
            "board": BOARD_FQBN,
            "partitionLayout": PARTITION_LAYOUT,
            "partitionSha256": partition_sha256,
            "spiffsOffset": hex(SPIFFS_OFFSET),
            "spiffsSize": hex(SPIFFS_SIZE),
            "spiffsPreservedInPlace": True,
            "binaryBytes": binary_bytes,
            "binarySha256": hashlib.sha256(application_binary.read_bytes()).hexdigest()
                if binary_bytes else "",
            "state": "passed" if result.returncode == 0 else "failed",
            "returnCode": result.returncode,
            "durationSeconds": round(time.time() - started, 2),
            "output": output,
            "buildPath": str(build_dir),
            "sketchPath": str(sketch_path),
            "supportFiles": [path.name for path in support_files],
        }
        with self._lock:
            self._builds[build_id] = record
        return record

    def query(self, device_id: str, command: str) -> dict[str, Any]:
        device = self._device(device_id)
        cleaned = str(command).strip()
        payload = cleaned
        if cleaned.startswith("<DB1:") and ">" in cleaned:
            target = cleaned[5:cleaned.index(">")].strip().upper()
            expected = {
                "left": "LEFTLEG",
                "right": "RIGHTLEG",
            }.get(device["role"])
            if expected and target != expected:
                raise FirmwareToolError(
                    f"diagnostic target {target} does not match device role {expected}"
                )
            payload = cleaned.split(">", 1)[1].strip()
        lowered = payload.lower()
        can_info = re.fullmatch(r"can info (0x[0-9a-f]{3}|[0-9]{3,4})", lowered)
        if lowered not in READ_ONLY_SERIAL_COMMANDS and not can_info:
            raise FirmwareToolError(
                "serial diagnostics permit version/capabilities/health/observe and passive status queries only"
            )
        if device["role"] in {"left", "right"}:
            result = self.observation_manager.send_diagnostic(
                device["role"], lowered
            )
            self.tx_bytes += result["bytes"]
            return {**result, "device": device}
        fd = os.open(
            device["stablePath"],
            os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC,
        )
        try:
            _configure_115200(fd)
            encoded = (cleaned + "\n").encode("ascii", errors="strict")
            written = os.write(fd, encoded)
            termios.tcdrain(fd)
        finally:
            os.close(fd)
        self.tx_bytes += written
        return {"sent": True, "bytes": written, "device": device, "command": cleaned}

    def _latest_side(self, side: str) -> dict[str, Any]:
        return self.observation_manager.snapshot().get("sides", {}).get(side, {})

    def _require_capability(self, side: str, capability: str) -> None:
        capabilities = self._latest_side(side).get("firmware", {}).get("capabilities", [])
        if capability not in capabilities:
            raise FirmwareToolError(
                f"{side} firmware does not advertise {capability}; update and verify firmware before this operation"
            )

    def inspect_configuration(self, device_id: str) -> dict[str, Any]:
        device = self._device(device_id)
        if device["role"] not in {"left", "right"}:
            raise FirmwareToolError("configuration inspection requires a mapped left or right leg controller")
        side = device["role"]
        self._require_capability(side, "config-records-v1")
        before = int(self._latest_side(side).get("configuration", {}).get("completeMonotonicNs", 0))
        sent = self.observation_manager.send_diagnostic(side, "config show")
        deadline = time.monotonic() + 1.25
        configuration: dict[str, Any] = {}
        while time.monotonic() < deadline:
            configuration = self._latest_side(side).get("configuration", {})
            if int(configuration.get("completeMonotonicNs", 0)) > before and len(configuration.get("constraints", {})) >= 6:
                break
            time.sleep(0.025)
        if int(configuration.get("completeMonotonicNs", 0)) <= before:
            raise RuntimeError("controller did not return DBCFG1 configuration records")
        return {
            "schema": "dropbear-leg-configuration-v1",
            "device": device,
            "configuration": configuration,
            "sent": sent,
        }

    @staticmethod
    def _require_interlock(payload: dict[str, Any], expected: str, acknowledgements: tuple[str, ...]) -> None:
        if str(payload.get("confirmation", "")) != expected:
            raise FirmwareToolError(f"type {expected} exactly to release this interlock")
        if not all(payload.get(name) is True for name in acknowledgements):
            raise FirmwareToolError("all physical-safety acknowledgements are required")

    def calibrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = self._device(str(payload.get("deviceId", "")))
        if device["role"] not in {"left", "right"}:
            raise FirmwareToolError("AS5600 calibration requires a mapped left or right leg controller")
        side = device["role"]
        self._require_capability(side, "calibration-result-v1")
        self._require_interlock(
            payload,
            f"CALIBRATE {side.upper()}",
            ("robotSupported", "areaClear", "estopReady"),
        )
        health = self._latest_side(side).get("health", {})
        if not health.get("runtimeReady"):
            raise FirmwareToolError(f"{side} leg runtime is not ready; calibration held")
        before = int(self._latest_side(side).get("calibration", {}).get("updatedMonotonicNs", 0))
        sent = self.observation_manager.send_guarded_command(side, "calibrate save")
        deadline = time.monotonic() + 1.75
        calibration: dict[str, Any] = {}
        while time.monotonic() < deadline:
            calibration = self._latest_side(side).get("calibration", {})
            if int(calibration.get("updatedMonotonicNs", 0)) > before:
                break
            time.sleep(0.025)
        if int(calibration.get("updatedMonotonicNs", 0)) <= before:
            raise RuntimeError("controller did not return a DBCAL1 calibration result")
        # Refresh the persisted offsets after either success or a sensor-count failure.
        configuration = None
        if calibration.get("status") == "ok":
            configuration = self.inspect_configuration(device["id"])["configuration"]
        return {
            "schema": "dropbear-leg-calibration-v1",
            "device": device,
            "sent": sent,
            "calibration": calibration,
            "configuration": configuration,
            "saved": calibration.get("status") == "ok",
        }

    def configure(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = self._device(str(payload.get("deviceId", "")))
        if device["role"] not in {"left", "right"}:
            raise FirmwareToolError("configuration changes require a mapped left or right leg controller")
        side = device["role"]
        self._require_capability(side, "config-records-v1")
        self._require_interlock(
            payload,
            f"APPLY {side.upper()} CONFIG",
            ("robotSupported", "estopReady", "limitsReviewed"),
        )
        setting = str(payload.get("setting", ""))
        joint = str(payload.get("joint", "")).lower()
        value = payload.get("value")
        allowed_sensor_joints = {"outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"}
        allowed_constraints = allowed_sensor_joints | {"hip_yaw"}
        def finite_number(candidate: Any, label: str) -> float:
            try:
                number = float(candidate)
            except (TypeError, ValueError) as error:
                raise FirmwareToolError(f"{label} must be numeric") from error
            if not math.isfinite(number):
                raise FirmwareToolError(f"{label} must be finite")
            return number

        def integer_number(candidate: Any, label: str) -> int:
            number = finite_number(candidate, label)
            if isinstance(candidate, bool) or not number.is_integer():
                raise FirmwareToolError(f"{label} must be an integer")
            return int(number)

        if setting == "maxTorque":
            number = finite_number(value, "max torque")
            if not 0.0 < number <= 100.0:
                raise FirmwareToolError("max torque must be >0 and <=100")
            command = f"config set max_torque {number:.3f}"
        elif setting == "offset":
            if joint not in allowed_sensor_joints:
                raise FirmwareToolError("offset requires a valid AS5600 joint")
            number = integer_number(value, "offset")
            if not -720 <= number <= 720:
                raise FirmwareToolError("offset must be from -720 through 720")
            command = f"config set offset {joint} {number}"
        elif setting == "direction":
            if joint not in allowed_sensor_joints or value not in {"+", "-"}:
                raise FirmwareToolError("direction requires a valid joint and + or -")
            command = f"direction {side}_{joint} {value}"
        elif setting == "constraint":
            if joint not in allowed_constraints or not isinstance(value, dict):
                raise FirmwareToolError("constraint requires a valid joint and min/max object")
            minimum = integer_number(value.get("min"), "constraint min")
            maximum = integer_number(value.get("max"), "constraint max")
            if minimum > maximum or minimum < -720 or maximum > 720:
                raise FirmwareToolError("constraint must satisfy -720 <= min <= max <= 720")
            command = f"constrain {joint}_{side} {minimum} {maximum}"
        elif setting == "operatingMode" and value in {"standalone", "hyperspawn"}:
            command = f"mode {value}"
        elif setting == "rawMode" and isinstance(value, bool):
            command = f"raw {'on' if value else 'off'}"
        elif setting == "hyperspawnTimeout":
            number = integer_number(value, "hyperspawn timeout")
            if not 50 <= number <= 10000:
                raise FirmwareToolError("hyperspawn timeout must be 50..10000 ms")
            command = f"hyperspawn timeout {number}"
        elif setting == "hyperspawnScale":
            number = finite_number(value, "hyperspawn scale")
            if not 0.0001 < number <= 1000.0:
                raise FirmwareToolError("hyperspawn scale must be >0.0001 and <=1000")
            command = f"hyperspawn scale {number:.6f}"
        elif setting in {"hyperspawnLegacy", "hyperspawnAutoArm"} and isinstance(value, bool):
            name = "legacy" if setting == "hyperspawnLegacy" else "autoarm"
            command = f"hyperspawn {name} {'on' if value else 'off'}"
        else:
            raise FirmwareToolError("unsupported configuration field or value")

        sent = self.observation_manager.send_guarded_command(side, command)
        time.sleep(0.08)
        configuration = self.inspect_configuration(device["id"])["configuration"]
        return {
            "schema": "dropbear-leg-configuration-v1",
            "device": device,
            "sent": sent,
            "configuration": configuration,
            "rebootRequired": bool(configuration.get("meta", {}).get("rebootRequired")),
        }

    def upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        build_id = str(payload.get("buildId", ""))
        build = self._builds.get(build_id)
        if not build or build.get("state") != "passed":
            raise FirmwareToolError("a successful compile from this server session is required")
        device = self._device(str(payload.get("deviceId", "")))
        if str(payload.get("sourceSha256", "")) != build["sha256"]:
            raise FirmwareToolError("firmware checksum acknowledgement does not match the build")
        if not all(payload.get(name) is True for name in (
            "robotSupported", "actuatorPowerSafe", "estopReady",
        )):
            raise FirmwareToolError("all physical-safety acknowledgements are required")
        expected = f"FLASH {device['role'].upper()}"
        if str(payload.get("confirmation", "")) != expected:
            raise FirmwareToolError(f"type {expected} exactly to release the upload interlock")

        self.stop()
        self.observation_manager.stop()
        application_binary = (
            Path(build["buildPath"]) / f"{Path(build['sketchPath']).name}.bin"
        )
        if not application_binary.is_file():
            raise FirmwareToolError("compiled application binary is missing; compile again")
        binary = application_binary.read_bytes()
        if len(binary) != build.get("binaryBytes") or hashlib.sha256(binary).hexdigest() != build.get("binarySha256"):
            raise FirmwareToolError("compiled application binary changed after verification; compile again")
        # The target's existing partition table was read and checked above.
        # Flash only the already-verified factory application region: this
        # avoids Arduino's redundant multi-minute compile during upload and
        # never writes the SPIFFS settings partition.
        command = [
            sys.executable, str(self.esptool), "--chip", "esp32",
            # The long robot harness/USB bridge has been verified end-to-end
            # only at 57600 with compression disabled. Faster or compressed
            # transfers can enter the bootloader but fail during the write.
            "--port", device["stablePath"], "--baud", "57600",
            "--before", "default_reset", "--after", "hard_reset",
            "write_flash", "--no-compress", "--flash_mode", "qio",
            "--flash_freq", "80m", "--flash_size", "4MB",
            hex(APP_OFFSET), str(application_binary),
        ]
        try:
            partition_check = self._verify_device_spiffs_layout(device)
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        finally:
            self.observation_manager.start()
            self.start()
        output = (result.stdout + "\n" + result.stderr).strip()[-24000:]
        if result.returncode != 0:
            raise RuntimeError(f"firmware upload failed ({result.returncode}): {output}")
        return {
            "uploaded": True,
            "device": device,
            "buildId": build_id,
            "sha256": build["sha256"],
            "partition": partition_check,
            "uploadMethod": "verified-app-region-only",
            "output": output,
        }
