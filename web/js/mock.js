// web/js/mock.js
//
// In-memory mock of the ESP32 WebSerial link. Provides two pieces:
//
//   MockDevice  — simulates the firmware side: holds a fleet of MotorSim
//                 motors, accepts command frames, applies them, and emits
//                 STATUS_REPORT frames back to the host.
//   MockTransport — drop-in replacement for WebSerialTransport that wires to a
//                 MockDevice instead of a real serial port. Same public surface
//                 (connect / send / onFrame / connected / disconnect) so the
//                 dashboard harness can exercise the full protocol + sim stack
//                 without hardware.
//
// This is the "connecting them in a mock run" backend used by test/harness.test.mjs.

import { Frame, FrameType } from "./protocol.js";
import { MotorSim } from "./sim.js";

// ---------------------------------------------------------------------------
// MockDevice: the simulated ESP32 motor controller.
// ---------------------------------------------------------------------------
export class MockDevice {
  constructor(specs) {
    // specs: array of motor spec objects ({ id, series, model, maxTorque, ... })
    this.fleet = specs.map((s) => new MotorSim(s));
    this.byId = new Map(this.fleet.map((m) => [m.id, m]));
    this.onFrame = null; // callback(Frame) -> frames emitted back to the host
    this.seq = 0;
    this.rxCount = 0; // command frames received
    this.txCount = 0; // status frames emitted
  }

  // Apply an incoming command frame from the host (dashboard) to the right motor.
  handle(frame) {
    const m = this.byId.get(frame.motorId);
    if (!m) return; // unknown motor id -> ignore, like a real bus drop
    this.rxCount++;
    // Delegate to the motor's full command array handler (motion, drive-state,
    // PARAM_READ/WRITE, diagnostic, heartbeat). It returns true if the frame
    // was actionable.
    if (typeof m.applyFrame === "function") m.applyFrame(frame);
    // Echo a status report for the affected motor so the host sees the result.
    this._emit(m.toStatusFrame(this.seq++));
  }

  // Advance the simulated device one step and emit a status frame per motor.
  tick(dt) {
    for (const m of this.fleet) {
      m.step(dt);
      this._emit(m.toStatusFrame(this.seq++));
    }
  }

  _emit(frame) {
    this.txCount++;
    if (this.onFrame) this.onFrame(frame);
  }
}

// ---------------------------------------------------------------------------
// MockTransport: WebSerialTransport-compatible in-memory transport.
// ---------------------------------------------------------------------------
export class MockTransport {
  constructor(device) {
    this.device = device || new MockDevice([]);
    this.connected = false;
    this.onFrame = null; // callback(Frame) from the device
    this.sent = []; // frames we forwarded to the device (for assertions)
    // Wire device emissions back to the host's onFrame callback.
    this.device.onFrame = (f) => {
      if (this.onFrame) this.onFrame(f);
    };
  }

  static isSupported() {
    return true; // always available in tests / headless
  }

  async connect(_baudRate = 115200) {
    this.connected = true;
  }

  async send(frame) {
    if (!this.connected) throw new Error("not connected");
    this.sent.push(frame);
    this.device.handle(frame);
  }

  async disconnect() {
    this.connected = false;
  }
}

// Helper: build a command frame for a given motor (used by the harness/tests).
export function commandFrame(frameType, motorId, value, sequence = 0) {
  const payload = new Uint8Array(32);
  const dv = new DataView(payload.buffer);
  if (frameType === FrameType.TORQUE_CMD) {
    dv.setInt16(0, Math.round(value * 100), true); // N·m -> 0.01 N·m
  } else {
    dv.setInt32(0, Math.round(value * 1000), true); // rad/rad/s -> mrad
  }
  return new Frame({
    frameType,
    motorId,
    commandType: 0x00,
    payload,
    sequence: sequence & 0xff,
  });
}
