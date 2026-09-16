from __future__ import annotations

import os
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


WEB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_ROOT))

from firmware_service import DeviceFirmwareManager, FirmwareToolError  # noqa: E402


class _Observation:
    def snapshot(self):
        return {"sides": {}}

    def start(self):
        pass

    def stop(self):
        pass


class FirmwareServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.project = root / "control"
        self.source = root / "firmware"
        self.sketchbook = root / "sketchbook"
        self.core_root = root / "esp32-core"
        self.project.mkdir()
        self.source.mkdir()
        (self.source / "partitions.csv").write_text(
            "nvs,data,nvs,0x9000,0x5000,\n"
            "otadata,data,ota,0xe000,0x2000,\n"
            "app0,app,factory,0x10000,0x280000,\n"
            "spiffs,data,spiffs,0x290000,0x160000,\n"
            "coredump,data,coredump,0x3F0000,0x10000,\n"
        )
        self.arduino = root / "arduino"
        self.arduino.write_text("#!/bin/sh\nexit 0\n")
        self.arduino.chmod(self.arduino.stat().st_mode | stat.S_IXUSR)
        self.esptool = root / "esptool.py"
        self.esptool.write_text("# test fixture\n")
        for name, version in (("FastAccelStepper", "0.30.15"), ("MCP_CAN_lib", "1.5.1")):
            library = self.sketchbook / "libraries" / name
            library.mkdir(parents=True)
            (library / "library.properties").write_text(f"name={name}\nversion={version}\n")
        core = self.core_root / "2.0.13"
        core.mkdir(parents=True)
        (core / "platform.txt").write_text("name=ESP32 Arduino\nversion=2.0.13\n")
        self.environment = mock.patch.dict(os.environ, {
            "DROPBEAR_FIRMWARE_ROOT": str(self.source),
            "DROPBEAR_ARDUINO": str(self.arduino),
            "DROPBEAR_ARDUINO_SKETCHBOOK": str(self.sketchbook),
            "DROPBEAR_ESP32_CORE_ROOT": str(self.core_root),
            "DROPBEAR_ESPTOOL": str(self.esptool),
        })
        self.environment.start()
        self.manager = DeviceFirmwareManager(self.project, _Observation())
        self.manager._devices = lambda: []

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_inventory_names_behemoth_source_without_claiming_installed_version(self):
        sketch = self.source / "firmware_full_libs_neck.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        snapshot = self.manager.snapshot()
        self.assertEqual(snapshot["sources"][0]["family"], "universal-behemoth")
        self.assertEqual(snapshot["sources"][0]["filename"], sketch.name)
        self.assertTrue(snapshot["toolchain"]["available"])
        self.assertTrue(snapshot["toolchain"]["ready"])
        self.assertEqual(snapshot["toolchain"]["libraryVersions"]["FastAccelStepper"], "0.30.15")
        self.assertEqual(snapshot["toolchain"]["esp32CoreVersions"], ["2.0.13"])
        self.assertTrue(snapshot["toolchain"]["spiffsPreservedInPlace"])
        self.assertEqual(snapshot["toolchain"]["spiffsOffset"], "0x290000")

    def test_compile_uses_argument_list_and_session_bound_build(self):
        sketch = self.source / "esp32_devkitc_v4_hybrid.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        source_id = self.manager.snapshot()["sources"][0]["id"]
        def successful_compile(command, **_kwargs):
            build_path = Path(next(
                item.partition("=")[2] for item in command if item.startswith("build.path=")
            ))
            build_path.mkdir(parents=True, exist_ok=True)
            (build_path / "esp32_devkitc_v4_hybrid.ino.bin").write_bytes(b"firmware")
            return subprocess.CompletedProcess(command, 0, "Sketch uses 100 bytes", "")

        with mock.patch("firmware_service.subprocess.run", side_effect=successful_compile) as run:
            result = self.manager.compile(source_id)
        self.assertEqual(result["state"], "passed")
        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertIn("--verify", command)
        self.assertIn("esp32:esp32:esp32:PartitionScheme=huge_app,EraseFlash=none", command)
        self.assertEqual(result["sourceId"], source_id)
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(result["binaryBytes"], 8)
        self.assertEqual(result["spiffsOffset"], "0x290000")
        copied_partition = Path(result["sketchPath"]).parent / "partitions.csv"
        self.assertEqual(copied_partition.read_bytes(), (self.source / "partitions.csv").read_bytes())

    def test_binary_partition_parser_finds_spiffs(self):
        entry = struct.pack(
            "<HBBII16sI", 0x50AA, 0x01, 0x82, 0x290000, 0x160000,
            b"spiffs\0".ljust(16, b"\0"), 0,
        )
        table = entry + (b"\xff" * (0x1000 - len(entry)))
        self.assertEqual(
            self.manager._spiffs_from_partition_binary(table),
            (0x290000, 0x160000),
        )

    def test_compile_rejects_partition_that_moves_spiffs(self):
        sketch = self.source / "firmware_full_libs_neck.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        partition = self.source / "partitions.csv"
        partition.write_text(partition.read_text().replace("0x290000,0x160000", "0x310000,0xE0000"))
        source_id = self.manager.snapshot()["sources"][0]["id"]
        with self.assertRaisesRegex(FirmwareToolError, "must remain at 0x290000"):
            self.manager.compile(source_id)

    def test_unknown_source_is_rejected_before_tool_execution(self):
        with self.assertRaises(FirmwareToolError):
            self.manager.compile("../../outside")

    def test_compile_rejects_unpinned_fast_accel_stepper(self):
        sketch = self.source / "firmware_full_libs_neck.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        source_id = self.manager.snapshot()["sources"][0]["id"]
        properties = self.sketchbook / "libraries" / "FastAccelStepper" / "library.properties"
        properties.write_text("name=FastAccelStepper\nversion=1.3.0\n")
        with self.assertRaisesRegex(FirmwareToolError, "FastAccelStepper requires 0.30.15"):
            self.manager.compile(source_id)

    def test_compile_rejects_incompatible_esp32_core(self):
        sketch = self.source / "firmware_full_libs_neck.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        source_id = self.manager.snapshot()["sources"][0]["id"]
        (self.core_root / "3.0.3").mkdir()
        (self.core_root / "3.0.3" / "platform.txt").write_text("version=3.0.3\n")
        with self.assertRaisesRegex(FirmwareToolError, "ESP32 Arduino core requires 2.0.13 exclusively"):
            self.manager.compile(source_id)


if __name__ == "__main__":
    unittest.main()
