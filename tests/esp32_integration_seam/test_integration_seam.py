from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Esp32IntegrationSeamTests(unittest.TestCase):
    def test_production_runtime_is_not_silently_wired_into_user_main(self) -> None:
        main = (ROOT / "firmware/esp32/src/main.cpp").read_text(encoding="utf-8")
        self.assertIn("pal.processCommands()", main)
        self.assertIn("bridge->update()", main)
        self.assertNotIn("GatewayTransportRuntime", main)
        self.assertNotIn("gateway_transport_runtime.h", main)

    def test_audit_names_every_current_and_target_boundary(self) -> None:
        document = (ROOT / "docs/ESP32_INTEGRATION_SEAM.md").read_text(encoding="utf-8")
        required = (
            "ProtocolAbstractionLayer::processCommands()",
            "SerialBridge::update()",
            "MotorController -> IMotorDriver",
            "MCP2515CAN",
            "hostlink_v1",
            "config_identity_guard",
            "safety_supervisor",
            "gateway_core",
            "gateway_transport_runtime",
            "NoIoCanTransport",
            "M0 — preserved baseline",
            "M7 — Dropbear physical backend",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, document)

    def test_no_loss_mapping_covers_identity_lease_units_and_outcomes(self) -> None:
        document = (ROOT / "docs/ESP32_INTEGRATION_SEAM.md").read_text(encoding="utf-8")
        for value in (
            "canonical actuator ID",
            "config ID/revision/SHA-256",
            "source identity",
            "lease ID/owner/sequence/expiry",
            "mode and presence mask",
            "SI position/velocity",
            "SI effort",
            "q-axis current",
            "absolute command deadline",
            "native bus/node",
            "TX result",
            "RX frame/bus/timestamp",
            "drive sample",
        ):
            with self.subTest(value=value):
                self.assertIn(f"| {value} |", document)

    def test_generated_dropbear_view_remains_motion_denied(self) -> None:
        view = json.loads(
            (ROOT / "generated/dropbear/simulator/dropbear_config.json").read_text()
        )
        self.assertFalse(view["registry"]["safety_admission"]["motion_enable_allowed"])
        header = (ROOT / "generated/dropbear/firmware/dropbear_config.generated.hpp").read_text()
        self.assertIn("kMotionEnableAllowed = false", header)
        self.assertIn("static_assert(!kMotionEnableAllowed", header)

    def test_new_runtime_is_portable_and_legacy_success_stub_is_not_hidden(self) -> None:
        runtime = (ROOT / "firmware/esp32/src/runtime/gateway_transport_runtime.cpp").read_text()
        header = (ROOT / "firmware/esp32/src/runtime/gateway_transport_runtime.h").read_text()
        self.assertNotIn("Arduino.h", runtime + header)
        self.assertNotIn("#include <MCP2515", runtime + header)
        self.assertNotIn("#include \"../drivers/mcp2515", runtime + header)
        self.assertIn("NoIoCanTransport::ready", runtime)
        self.assertIn("return false;", runtime)
        legacy = (ROOT / "firmware/esp32/src/drivers/can_bus.cpp").read_text()
        self.assertIn("// Send CAN frame\n    return true;", legacy)
        document = (ROOT / "docs/ESP32_INTEGRATION_SEAM.md").read_text()
        self.assertIn("legacy `CANBus` success stub", document)


if __name__ == "__main__":
    unittest.main()
