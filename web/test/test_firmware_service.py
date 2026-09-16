from __future__ import annotations

import os
import stat
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
        self.project.mkdir()
        self.source.mkdir()
        self.arduino = root / "arduino"
        self.arduino.write_text("#!/bin/sh\nexit 0\n")
        self.arduino.chmod(self.arduino.stat().st_mode | stat.S_IXUSR)
        for name, version in (("FastAccelStepper", "0.30.15"), ("MCP_CAN_lib", "1.5.1")):
            library = self.sketchbook / "libraries" / name
            library.mkdir(parents=True)
            (library / "library.properties").write_text(f"name={name}\nversion={version}\n")
        self.environment = mock.patch.dict(os.environ, {
            "DROPBEAR_FIRMWARE_ROOT": str(self.source),
            "DROPBEAR_ARDUINO": str(self.arduino),
            "DROPBEAR_ARDUINO_SKETCHBOOK": str(self.sketchbook),
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

    def test_compile_uses_argument_list_and_session_bound_build(self):
        sketch = self.source / "esp32_devkitc_v4_hybrid.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        source_id = self.manager.snapshot()["sources"][0]["id"]
        completed = subprocess.CompletedProcess([], 0, "Sketch uses 100 bytes", "")
        with mock.patch("firmware_service.subprocess.run", return_value=completed) as run:
            result = self.manager.compile(source_id)
        self.assertEqual(result["state"], "passed")
        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertIn("--verify", command)
        self.assertIn("esp32:esp32:esp32", command)
        self.assertEqual(result["sourceId"], source_id)
        self.assertEqual(len(result["sha256"]), 64)

    def test_unknown_source_is_rejected_before_tool_execution(self):
        with self.assertRaises(FirmwareToolError):
            self.manager.compile("../../outside")

    def test_compile_rejects_unpinned_fast_accel_stepper(self):
        sketch = self.source / "firmware_full_libs_neck.ino"
        sketch.write_text("void setup() {}\nvoid loop() {}\n")
        source_id = self.manager.snapshot()["sources"][0]["id"]
        properties = self.sketchbook / "libraries" / "FastAccelStepper" / "library.properties"
        properties.write_text("name=FastAccelStepper\nversion=1.3.0\n")
        with self.assertRaisesRegex(FirmwareToolError, "FastAccelStepper 0.30.15 required"):
            self.manager.compile(source_id)


if __name__ == "__main__":
    unittest.main()
