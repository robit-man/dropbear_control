// web/js/webserial.js
//
// WebSerial transport for talking to the ESP32 over its USB CDC serial port.
// Frames are the 64-byte unified protocol frames (see protocol.js), which the
// firmware's SerialBridge (src/serial_bridge.cpp) parses and dispatches to the
// MotorController. The firmware also emits STATUS_REPORT frames back so this
// transport can visualize live state via onFrame().
//
// NOTE: Logger also writes human-readable text to the same Serial stream. The
// transport resyncs on 64-byte boundaries and ignores non-frame bytes, so
// interleaved log lines are tolerated. For a clean machine-only link, point
// the dashboard at a separate UART (Serial1/Serial2) on the ESP32.
//
// The dashboard's simulation mode is fully functional without hardware.

import { Frame } from "./protocol.js";

export class WebSerialTransport {
  constructor() {
    this.port = null;
    this.reader = null;
    this.writer = null;
    this.connected = false;
    this._buf = new Uint8Array(0);
    this.onFrame = null; // callback(Frame)
  }

  static isSupported() {
    return typeof navigator !== "undefined" && "serial" in navigator;
  }

  async connect(baudRate = 115200) {
    if (!WebSerialTransport.isSupported()) {
      throw new Error("WebSerial is not supported in this browser (use Chrome/Edge over HTTPS or localhost).");
    }
    this.port = await navigator.serial.requestPort();
    await this.port.open({ baudRate });
    this.connected = true;
    this.writer = this.port.writable.getWriter();
    this._readLoop();
  }

  async _readLoop() {
    this.reader = this.port.readable.getReader();
    try {
      while (true) {
        const { value, done } = await this.reader.read();
        if (done) break;
        if (value) this._ingest(value);
      }
    } catch (_e) {
      // reader cancelled or port closed; ignore.
    }
  }

  _ingest(chunk) {
    const merged = new Uint8Array(this._buf.length + chunk.length);
    merged.set(this._buf);
    merged.set(chunk, this._buf.length);
    this._buf = merged;
    // Extract as many complete 64-byte frames as are buffered.
    while (this._buf.length >= 64) {
      const frameBytes = this._buf.subarray(0, 64);
      try {
        const f = Frame.unpack(frameBytes);
        if (this.onFrame) this.onFrame(f);
      } catch (_e) {
        // Skip malformed/non-frame bytes; resync on next 64-byte boundary.
      }
      this._buf = this._buf.subarray(64);
    }
  }

  async send(frame) {
    if (!this.writer) throw new Error("not connected");
    await this.writer.write(frame.pack());
  }

  async disconnect() {
    this.connected = false;
    try {
      if (this.reader) await this.reader.cancel();
    } catch (_e) {}
    try {
      if (this.writer) this.writer.releaseLock();
    } catch (_e) {}
    try {
      if (this.port) await this.port.close();
    } catch (_e) {}
    this.reader = null;
    this.writer = null;
    this.port = null;
  }
}
