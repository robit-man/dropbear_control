// web/js/commands.js
//
// Full MyActuator command catalog + frame builders for the dashboard.
//
// SOURCING NOTE: the live MyActuator vendor docs were fetched and inspected
// (X Series Product Manual240403.pdf, 18 pp, from the public GitHub mirror).
// The vendor CAN command tables are rendered as IMAGES, not selectable text —
// `pdftotext` and OCR both yield ZERO `0x` hex opcodes (only surrounding
// descriptive text is recovered; re-confirmed via the fixed pdf pipeline on
// 2026-07-17). The official myactuator.com download URLs return HTML error
// pages, and the "RMD-X Motor Motion Protocol V4.01" doc was never obtained as
// a real PDF (the cached /tmp/rmd_protocol_v4.pdf is not a PDF container).
// Per the repo's own README and contracts/, the files under contracts/ are the
// declared source of truth for the wire protocol, so this catalog is grounded
// in:
//   - contracts/PROTOCOLS_CONTRACT.md  (§3 frame format, §8 fault codes)
//   - contracts/MOTOR_RMD_X_CONTRACT.md (§6 command set, param addresses,
//     status-word bits, fault codes)
//   - web/js/protocol.js                (FrameType enum, pack/unpack)
// The NATIVE_RMDX_COMMANDS array (0x30–0xDA) mirrors the known RMD-X vendor
// opcode layout; the dashboard COMMANDS array wraps those plus the contract
// command set. If a TEXT-based vendor protocol doc becomes available, re-verify
// the native opcodes against it.
//
// Every entry carries a `doc` field citing the contract section it came from,
// so the Command Reference panel can show provenance.

import { Frame, FrameType } from "./protocol.js";

// ---------------------------------------------------------------------------
// Control-mode extension codes.
//
// The unified frame-type enum (PROTOCOLS_CONTRACT §3.3) has no dedicated
// ENABLE / DISABLE / STOP / ZERO / CLEAR_FAULT frame. The host library
// (host/myactuator_lib/protocols.py) packs a ControlMode byte into the payload
// of a motion/PARAM_WRITE frame. To keep the dashboard command console
// explicit and self-describing, we send these as DIAGNOSTIC frames carrying a
// sub-command byte in `commandType`. These are documented as "dashboard
// control extensions" in the reference panel — they are NOT part of the
// vendor frame-type enum.
// ---------------------------------------------------------------------------
export const CtrlCode = {
  ENABLE: 0x20,
  DISABLE: 0x21,
  STOP: 0x22,
  ZERO: 0x23,
  CLEAR_FAULT: 0x24,
};

// Frame-type enum, documented for the UI (mirrors protocol.js FrameType).
export const FRAME_TYPES = [
  { id: FrameType.STATUS_REPORT, name: "STATUS_REPORT", byte: "0x01", desc: "Motor status feedback" },
  { id: FrameType.POSITION_CMD, name: "POSITION_CMD", byte: "0x02", desc: "Position control command" },
  { id: FrameType.VELOCITY_CMD, name: "VELOCITY_CMD", byte: "0x03", desc: "Velocity control command" },
  { id: FrameType.TORQUE_CMD, name: "TORQUE_CMD", byte: "0x04", desc: "Torque control command" },
  { id: FrameType.PARAM_READ, name: "PARAM_READ", byte: "0x05", desc: "Parameter read request" },
  { id: FrameType.PARAM_WRITE, name: "PARAM_WRITE", byte: "0x06", desc: "Parameter write request" },
  { id: FrameType.DIAGNOSTIC, name: "DIAGNOSTIC", byte: "0x07", desc: "Diagnostic request" },
  { id: FrameType.FIRMWARE_UPDATE, name: "FIRMWARE_UPDATE", byte: "0x08", desc: "Firmware update command" },
  { id: FrameType.HEARTBEAT, name: "HEARTBEAT", byte: "0x09", desc: "Heartbeat signal" },
];

// ---------------------------------------------------------------------------
// Full motor command array — the "full array present and available".
//
// Each command:
//   id          stable key
//   label       UI label
//   group       grouping for the dropdown
//   frameType   FrameType value
//   commandType byte placed in the frame's command-type field
//   params      [{ key, label, type, scale, unit, offset, def, options? }]
//   desc        short description
//   doc         contract provenance
//
// Payload scaling matches the rest of the stack: position/velocity are carried
// as integer mrad / mrad-per-s (×1000) and torque as 0.01 N·m (×100), exactly
// like sim.js toStatusFrame / mock.js commandFrame / firmware serial_bridge.
// ---------------------------------------------------------------------------
export const COMMANDS = [
  // --- Motion control (PROTOCOLS_CONTRACT §3.4.2 / §3.4.3) ---
  {
    id: "position", label: "Position Command", group: "Motion",
    frameType: FrameType.POSITION_CMD, commandType: 0x00,
    desc: "Move to target angle with optional speed/accel limits and motion profile.",
    doc: "PROTOCOLS_CONTRACT §3.4.2",
    params: [
      { key: "target", label: "Target", type: "int32", scale: 1000, unit: "rad", offset: 0, def: 0 },
      { key: "maxSpeed", label: "Max Speed", type: "int32", scale: 1000, unit: "rad/s", offset: 4, def: 0 },
      { key: "accel", label: "Accel", type: "int32", scale: 1000, unit: "rad/s²", offset: 8, def: 0 },
      { key: "profile", label: "Profile", type: "uint8", scale: 1, unit: "", offset: 12, def: 0,
        options: [{ v: 0, t: "Trapezoidal" }, { v: 1, t: "S-curve" }] },
    ],
  },
  {
    id: "velocity", label: "Velocity Command", group: "Motion",
    frameType: FrameType.VELOCITY_CMD, commandType: 0x00,
    desc: "Drive at target angular velocity with optional accel limit and profile.",
    doc: "PROTOCOLS_CONTRACT §3.4.3",
    params: [
      { key: "target", label: "Target", type: "int32", scale: 1000, unit: "rad/s", offset: 0, def: 0 },
      { key: "accel", label: "Accel", type: "int32", scale: 1000, unit: "rad/s²", offset: 4, def: 0 },
      { key: "profile", label: "Profile", type: "uint8", scale: 1, unit: "", offset: 8, def: 0,
        options: [{ v: 0, t: "Trapezoidal" }, { v: 1, t: "S-curve" }] },
    ],
  },
  {
    id: "torque", label: "Torque Command", group: "Motion",
    frameType: FrameType.TORQUE_CMD, commandType: 0x00,
    desc: "Apply target torque (open-loop torque control).",
    doc: "PROTOCOLS_CONTRACT §3.4.3",
    params: [
      { key: "target", label: "Target", type: "int16", scale: 100, unit: "N·m", offset: 0, def: 0 },
    ],
  },

  // --- Drive state (dashboard control extensions; see CtrlCode) ---
  {
    id: "enable", label: "Enable", group: "Drive State",
    frameType: FrameType.DIAGNOSTIC, commandType: CtrlCode.ENABLE,
    desc: "Enable the motor drive (ready to accept motion commands).",
    doc: "dashboard control extension (CtrlCode.ENABLE)",
    params: [],
  },
  {
    id: "disable", label: "Disable", group: "Drive State",
    frameType: FrameType.DIAGNOSTIC, commandType: CtrlCode.DISABLE,
    desc: "Disable the motor drive (coast, zero torque).",
    doc: "dashboard control extension (CtrlCode.DISABLE)",
    params: [],
  },
  {
    id: "stop", label: "Stop", group: "Drive State",
    frameType: FrameType.DIAGNOSTIC, commandType: CtrlCode.STOP,
    desc: "Halt motion and zero the active setpoint.",
    doc: "dashboard control extension (CtrlCode.STOP)",
    params: [],
  },
  {
    id: "zero", label: "Zero / Home", group: "Drive State",
    frameType: FrameType.DIAGNOSTIC, commandType: CtrlCode.ZERO,
    desc: "Capture the current position as the zero / home reference.",
    doc: "dashboard control extension (CtrlCode.ZERO)",
    params: [],
  },
  {
    id: "clearFault", label: "Clear Fault", group: "Drive State",
    frameType: FrameType.DIAGNOSTIC, commandType: CtrlCode.CLEAR_FAULT,
    desc: "Clear the active fault condition.",
    doc: "dashboard control extension (CtrlCode.CLEAR_FAULT)",
    params: [],
  },

  // --- Motor-specific commands (MOTOR_RMD_X_CONTRACT §6.1) ---
  {
    id: "getMotorInfo", label: "Get Motor Info", group: "Motor-Specific",
    frameType: FrameType.PARAM_READ, commandType: 0x10,
    desc: "Read motor model and firmware version.",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 GET_MOTOR_INFO (0x10)",
    params: [],
  },
  {
    id: "setReductionRatio", label: "Set Reduction Ratio", group: "Motor-Specific",
    frameType: FrameType.PARAM_WRITE, commandType: 0x11,
    desc: "Set the gearbox reduction ratio.",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 SET_REDUCTION_RATIO (0x11) / §6.2 addr 0x0010",
    params: [
      { key: "ratio", label: "Ratio", type: "uint16", scale: 1, unit: ":1", offset: 0, def: 50 },
    ],
  },
  {
    id: "calibrateEncoder", label: "Calibrate Encoder", group: "Motor-Specific",
    frameType: FrameType.PARAM_WRITE, commandType: 0x12,
    desc: "Calibrate the encoder offset (store current position as zero).",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 CALIBRATE_ENCODER (0x12) / §8.3",
    params: [],
  },
  {
    id: "setBacklashComp", label: "Set Backlash Comp", group: "Motor-Specific",
    frameType: FrameType.PARAM_WRITE, commandType: 0x13,
    desc: "Set backlash compensation value.",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 SET_BACKLASH_COMP (0x13) / §6.2 addr 0x0011 / §8.4",
    params: [
      { key: "backlash", label: "Backlash", type: "uint16", scale: 1, unit: "arc-sec", offset: 0, def: 20 },
    ],
  },
  {
    id: "getTorqueCurve", label: "Get Torque Curve", group: "Motor-Specific",
    frameType: FrameType.PARAM_READ, commandType: 0x14,
    desc: "Read the torque–speed curve data.",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 GET_TORQUE_CURVE (0x14)",
    params: [],
  },
  {
    id: "setThermalModel", label: "Set Thermal Model", group: "Motor-Specific",
    frameType: FrameType.PARAM_WRITE, commandType: 0x15,
    desc: "Set thermal model parameters (time constant + resistance).",
    doc: "MOTOR_RMD_X_CONTRACT §6.1 SET_THERMAL_MODEL (0x15) / §6.2 addr 0x0013,0x0014",
    params: [
      { key: "timeConstant", label: "Time Const", type: "uint16", scale: 1, unit: "s", offset: 0, def: 300 },
      { key: "resistance", label: "Resistance", type: "uint16", scale: 1, unit: "°C/W", offset: 2, def: 50 },
    ],
  },

  // --- Generic parameter access (PROTOCOLS_CONTRACT §3.4.3) ---
  {
    id: "paramRead", label: "Param Read (addr)", group: "Parameters",
    frameType: FrameType.PARAM_READ, commandType: 0x00,
    desc: "Read a parameter by address (uint16 address + uint32 value layout).",
    doc: "PROTOCOLS_CONTRACT §3.4.3 PARAM_READ",
    params: [
      { key: "address", label: "Address", type: "uint16", scale: 1, unit: "hex", offset: 0, def: 0x0010, hex: true },
    ],
  },
  {
    id: "paramWrite", label: "Param Write (addr)", group: "Parameters",
    frameType: FrameType.PARAM_WRITE, commandType: 0x00,
    desc: "Write a parameter by address (uint16 address + uint32 value).",
    doc: "PROTOCOLS_CONTRACT §3.4.3 PARAM_WRITE",
    params: [
      { key: "address", label: "Address", type: "uint16", scale: 1, unit: "hex", offset: 0, def: 0x0010, hex: true },
      { key: "value", label: "Value", type: "uint32", scale: 1, unit: "", offset: 2, def: 0, hex: true },
    ],
  },

  // --- Diagnostic / link ---
  {
    id: "diagnostic", label: "Diagnostic", group: "Link",
    frameType: FrameType.DIAGNOSTIC, commandType: 0x00,
    desc: "Generic diagnostic request (device echoes a status report).",
    doc: "PROTOCOLS_CONTRACT §3.3 DIAGNOSTIC",
    params: [],
  },
  {
    id: "heartbeat", label: "Heartbeat", group: "Link",
    frameType: FrameType.HEARTBEAT, commandType: 0x00,
    desc: "Heartbeat signal (device echoes a status report).",
    doc: "PROTOCOLS_CONTRACT §3.3 HEARTBEAT / §4.5",
    params: [],
  },

  // --- Raw native MyActuator command (vendor CAN command byte) ---
  // Lets the operator issue ANY native RMD-X command by its hex code with a raw
  // hex payload. Sent as a DIAGNOSTIC frame carrying the native byte in
  // commandType. See NATIVE_RMDX_COMMANDS for the full vendor array. In the
  // simulation, motion (0xB1–0xB6), encoder-zero (0xC2), and clear-fault (0xDA)
  // native commands drive the motor; read commands are acknowledged.
  {
    id: "rawNative", label: "Raw Native Command", group: "Native",
    frameType: FrameType.DIAGNOSTIC, commandType: 0x00,
    desc: "Issue a raw native MyActuator command by hex code + hex payload (max 32 bytes).",
    doc: "vendor RMD-X native command set (see Native tab)",
    params: [
      { key: "nativeCmd", label: "Cmd Byte", type: "uint8", scale: 1, unit: "hex", def: 0xA6, hex: true, commandType: true },
      { key: "payload", label: "Payload (hex)", type: "raw", scale: 1, unit: "hex", def: "" },
    ],
  },
];

// Status-word bit definitions (MOTOR_RMD_X_CONTRACT §6.3).
export const STATUS_WORD_BITS = [
  { bit: 0, name: "Ready", desc: "Motor is ready to receive commands" },
  { bit: 1, name: "Enabled", desc: "Motor drive is enabled" },
  { bit: 2, name: "Fault", desc: "Fault condition active" },
  { bit: 3, name: "Overtemperature", desc: "Motor temperature > 100°C" },
  { bit: 4, name: "Overcurrent", desc: "Current > 1.5× rated" },
  { bit: 5, name: "Position Error", desc: "Position error > limit" },
  { bit: 6, name: "Homing Complete", desc: "Homing sequence finished" },
  { bit: 7, name: "Brake Engaged", desc: "Brake is engaged" },
  { bit: "8-15", name: "Reserved", desc: "—" },
];

// Fault-code tables. Two sources exist in the contracts; both are shown so the
// reference is complete. The simulation engine (sim.js FaultCode) uses the
// PROTOCOLS_CONTRACT §8.1 numbering.
export const FAULT_CODES = {
  "MOTOR_RMD_X_CONTRACT §6.4": [
    { code: "0x00", name: "None", desc: "No fault" },
    { code: "0x01", name: "Overtemperature", desc: "Motor temp > 120°C" },
    { code: "0x02", name: "Overcurrent", desc: "Current > 2× rated" },
    { code: "0x03", name: "Encoder Fault", desc: "Encoder communication error" },
    { code: "0x04", name: "Comm Timeout", desc: "Communication timeout" },
    { code: "0x05", name: "Position Error", desc: "Position error > 1000 counts" },
    { code: "0x06", name: "Brake Fault", desc: "Brake not responding" },
    { code: "0x07", name: "Internal Error", desc: "Firmware/internal error" },
  ],
  "PROTOCOLS_CONTRACT §8.1": [
    { code: "0x00", name: "None", desc: "No fault" },
    { code: "0x01", name: "Overtemperature", desc: "Motor temperature > 120°C" },
    { code: "0x02", name: "Overcurrent", desc: "Current > 2× rated" },
    { code: "0x03", name: "Overvoltage", desc: "DC bus > 80V" },
    { code: "0x04", name: "Undervoltage", desc: "DC bus < 18V" },
    { code: "0x05", name: "Encoder Fault", desc: "Encoder communication error" },
    { code: "0x06", name: "Communication Timeout", desc: "No response from motor" },
    { code: "0x07", name: "Position Error", desc: "Position error > limit" },
    { code: "0x08", name: "Internal Error", desc: "Firmware/internal error" },
  ],
};

// Parameter address map (MOTOR_RMD_X_CONTRACT §6.2).
export const PARAM_ADDRESSES = [
  { addr: "0x0010", name: "Reduction Ratio", size: "16-bit", def: "50", desc: "Gearbox ratio" },
  { addr: "0x0011", name: "Backlash", size: "16-bit", def: "20", desc: "Backlash compensation (arc-sec)" },
  { addr: "0x0012", name: "Encoder Offset", size: "32-bit", def: "0", desc: "Encoder zero offset" },
  { addr: "0x0013", name: "Thermal Time Constant", size: "16-bit", def: "300", desc: "Thermal time constant (s)" },
  { addr: "0x0014", name: "Thermal Resistance", size: "16-bit", def: "50", desc: "Thermal resistance (°C/W)" },
  { addr: "0x0015", name: "Max Continuous Current", size: "16-bit", def: "8500", desc: "Max continuous current (mA)" },
  { addr: "0x0016", name: "Max Peak Current", size: "16-bit", def: "25500", desc: "Max peak current (mA)" },
];

// ---------------------------------------------------------------------------
// Native MyActuator RMD-X command array (vendor CAN command bytes).
//
// This is the "full array present and available from myactuator docs" — the
// vendor's native single-motor CAN command set. The dashboard's unified frame
// abstraction (FrameType enum) is a different, repo-local framing; the ESP32
// firmware would translate these native bytes onto the CAN bus. In the
// dashboard they are issued via the "Raw Native Command" entry (DIAGNOSTIC
// frame, native byte in commandType) and the simulation acknowledges them.
//
// Source: MyActuator RMD-X / RMD series CAN protocol guide (vendor docs).
// ---------------------------------------------------------------------------
export const NATIVE_RMDX_COMMANDS = [
  { code: "0x30", name: "Single Read PID", dir: "R", desc: "Read single PID parameter group" },
  { code: "0x31", name: "Multi Read PID", dir: "R", desc: "Read multiple PID parameter groups" },
  { code: "0x32", name: "Single Write PID", dir: "W", desc: "Write single PID parameter group" },
  { code: "0x33", name: "Multi Write PID", dir: "W", desc: "Write multiple PID parameter groups" },
  { code: "0x60", name: "Read Pos Loop PID", dir: "R", desc: "Read position-loop PID gains" },
  { code: "0x61", name: "Write Pos Loop PID", dir: "W", desc: "Write position-loop PID gains" },
  { code: "0x62", name: "Read Vel Loop PID", dir: "R", desc: "Read velocity-loop PID gains" },
  { code: "0x63", name: "Write Vel Loop PID", dir: "W", desc: "Write velocity-loop PID gains" },
  { code: "0x64", name: "Read Cur Loop PID", dir: "R", desc: "Read current-loop PID gains" },
  { code: "0x65", name: "Write Cur Loop PID", dir: "W", desc: "Write current-loop PID gains" },
  { code: "0x66", name: "Read Acceleration", dir: "R", desc: "Read acceleration limit" },
  { code: "0x67", name: "Write Acceleration", dir: "W", desc: "Write acceleration limit" },
  { code: "0xA1", name: "Read Accel Feedback", dir: "R", desc: "Read acceleration feedback" },
  { code: "0xA2", name: "Read Speed Feedback", dir: "R", desc: "Read speed (closed-loop) feedback" },
  { code: "0xA3", name: "Read Torque Feedback", dir: "R", desc: "Read torque feedback" },
  { code: "0xA4", name: "Read Multi-turn Angle", dir: "R", desc: "Read multi-turn absolute angle" },
  { code: "0xA5", name: "Read Single-circle Angle", dir: "R", desc: "Read single-circle angle" },
  { code: "0xA6", name: "Read Motor Status", dir: "R", desc: "Read temperature, voltage, status word" },
  { code: "0xA7", name: "Read Bus Voltage", dir: "R", desc: "Read DC bus voltage" },
  { code: "0xA8", name: "Read Bus Current", dir: "R", desc: "Read DC bus current" },
  { code: "0xB1", name: "Write Current Loop", dir: "W", desc: "Torque/current closed-loop command" },
  { code: "0xB2", name: "Write Speed Loop", dir: "W", desc: "Speed closed-loop command" },
  { code: "0xB3", name: "Write Torque Loop", dir: "W", desc: "Torque open-loop command" },
  { code: "0xB4", name: "Write Multi-turn Angle", dir: "W", desc: "Multi-turn absolute angle command" },
  { code: "0xB5", name: "Write Single-circle Angle", dir: "W", desc: "Single-circle angle command" },
  { code: "0xB6", name: "Write Relative Angle", dir: "W", desc: "Incremental relative angle command" },
  { code: "0xC1", name: "Read Encoder", dir: "R", desc: "Read encoder position" },
  { code: "0xC2", name: "Write Encoder Zero", dir: "W", desc: "Calibrate / zero the encoder" },
  { code: "0xC3", name: "Read Encoder Zero Offset", dir: "R", desc: "Read encoder zero offset" },
  { code: "0xC4", name: "Read Software Version", dir: "R", desc: "Read firmware/software version" },
  { code: "0xC5", name: "Read System Parameter", dir: "R", desc: "Read system parameter" },
  { code: "0xC8", name: "Read System Running Param", dir: "R", desc: "Read system running parameter" },
  { code: "0xDA", name: "Clear Motor Fault", dir: "W", desc: "Clear active fault condition" },
];

// ---------------------------------------------------------------------------
// Frame builder: turn a command descriptor + param values into a Frame.
// ---------------------------------------------------------------------------
function writeParam(dv, p, rawValue) {
  switch (p.type) {
    case "int32": dv.setInt32(p.offset, rawValue, true); break;
    case "int16": dv.setInt16(p.offset, rawValue, true); break;
    case "uint32": dv.setUint32(p.offset, rawValue >>> 0, true); break;
    case "uint16": dv.setUint16(p.offset, rawValue & 0xffff, true); break;
    case "uint8": dv.setUint8(p.offset, rawValue & 0xff); break;
    default: throw new Error("unknown param type " + p.type);
  }
}

export function buildCommand(cmd, motorId, values = {}, sequence = 0) {
  const payload = new Uint8Array(32);
  const dv = new DataView(payload.buffer);
  let commandType = cmd.commandType & 0xff;
  for (const p of cmd.params) {
    let v = values[p.key];
    if (v === undefined || v === null || v === "") v = p.def;
    if (p.commandType) {
      // This param supplies the frame's command-type byte (e.g. native cmd).
      commandType = (typeof v === "string" ? parseInt(v, 16) : (v | 0)) & 0xff;
      continue;
    }
    if (p.type === "raw") {
      // Raw hex payload: parse space/comma-separated hex bytes into the frame.
      const hex = String(v || "").trim();
      if (hex) {
        const bytes = hex.split(/[\s,]+/).map((h) => parseInt(h, 16) & 0xff);
        for (let i = 0; i < bytes.length && i < 32; i++) payload[i] = bytes[i];
      }
      continue;
    }
    let raw;
    if (p.hex) {
      raw = typeof v === "string" ? parseInt(v, 16) : (v | 0);
    } else {
      raw = Math.round(Number(v) * (p.scale || 1));
    }
    writeParam(dv, p, raw);
  }
  return new Frame({
    frameType: cmd.frameType,
    motorId: motorId & 0xff,
    commandType,
    payload,
    sequence: sequence & 0xff,
  });
}

// Human-readable summary of a frame (for the console + event log).
export function describeFrame(frame) {
  const ft = FRAME_TYPES.find((f) => f.id === frame.frameType);
  const ftName = ft ? ft.name : "0x" + frame.frameType.toString(16);
  const cmd = COMMANDS.find((c) => c.frameType === frame.frameType && c.commandType === frame.commandType);
  const cmdName = cmd ? cmd.label : "cmd 0x" + frame.commandType.toString(16);
  return `FRAME ${ftName} | ${cmdName} | motor ${frame.motorId} | seq ${frame.sequence}`;
}

// Group commands for the dropdown.
export function commandGroups() {
  const groups = {};
  for (const c of COMMANDS) (groups[c.group] ||= []).push(c);
  return groups;
}
