// web/test/harness.test.mjs
//
// End-to-end harness for the dashboard's protocol + simulation stack, driven by
// the in-memory MockTransport / MockDevice (no hardware, no browser). It loads
// a given set of motors, "connects" them over the mock link, sends command
// frames, runs the simulated device, and verifies the full frame exchange:
//   host command -> device applies it -> device emits STATUS_REPORT -> host
//   decodes it back into motor state.
//
// Run: node web/test/harness.test.mjs

import { Frame, FrameType } from "../js/protocol.js";
import { defaultFleet, MOTOR_SERIES } from "../js/motors.js";
import { MotorState, FaultCode } from "../js/sim.js";
import { MockDevice, MockTransport, commandFrame } from "../js/mock.js";
import { COMMANDS, buildCommand, commandGroups, describeFrame, NATIVE_RMDX_COMMANDS } from "../js/commands.js";

let failures = 0;
function check(name, cond) {
  if (cond) console.log(`  ok  ${name}`);
  else { console.error(`  FAIL ${name}`); failures++; }
}

// ---------------------------------------------------------------------------
// 1. Load the given motors (the default fleet: one per series, ids 1..6).
// ---------------------------------------------------------------------------
const specs = defaultFleet();
check("loaded 6 motors (one per series)", specs.length === 6);
check("motor ids are 1..6", specs.every((s, i) => s.id === i + 1));
check("all series present",
  ["RMD-X", "RH", "CEM", "RMD-H", "RMD-L", "FL"].every((s) =>
    specs.some((m) => m.series === s)));

// ---------------------------------------------------------------------------
// 2. Connect them in a mock run (MockTransport <-> MockDevice).
// ---------------------------------------------------------------------------
const device = new MockDevice(specs);
const transport = new MockTransport(device);

// Host-side state mirror, keyed by motor id, populated from received frames.
const hostState = new Map();
for (const s of specs) hostState.set(s.id, { pos: 0, vel: 0, torq: 0, temp: 25, status: 0, fault: 0 });

transport.onFrame = (f) => {
  if (f.frameType !== FrameType.STATUS_REPORT) return;
  const dv = new DataView(f.payload.buffer, f.payload.byteOffset, f.payload.byteLength);
  const st = hostState.get(f.motorId);
  if (!st) return;
  st.pos = dv.getInt32(0, true) / 1000;
  st.vel = dv.getInt32(4, true) / 1000;
  st.torq = dv.getInt16(8, true) / 100;
  st.temp = f.payload[10];
  st.status = dv.getUint16(11, true);
  st.fault = f.payload[13];
};

await transport.connect(115200);
check("transport reports connected", transport.connected === true);

// ---------------------------------------------------------------------------
// 3. Send a velocity command to motor 1 and verify the device applies it and
//    echoes a status frame the host can decode.
// ---------------------------------------------------------------------------
const targetVel = 5; // rad/s
await transport.send(commandFrame(FrameType.VELOCITY_CMD, 1, targetVel, 1));
check("device received 1 command frame", device.rxCount === 1);
check("device emitted a status frame in reply", device.txCount >= 1);
check("host decoded a status frame for motor 1", hostState.get(1).status !== 0);

// Run the device a few steps so velocity integrates into position.
for (let i = 0; i < 60; i++) device.tick(0.02);
check("motor 1 velocity converged near target", Math.abs(hostState.get(1).vel - targetVel) < 1.0);
check("motor 1 position advanced", hostState.get(1).pos > 0.5);
check("motor 1 status is VELOCITY_CONTROL", hostState.get(1).status === MotorState.VELOCITY_CONTROL);

// ---------------------------------------------------------------------------
// 4. Send a position command to motor 2 and verify convergence.
// ---------------------------------------------------------------------------
const targetPos = 10; // rad
await transport.send(commandFrame(FrameType.POSITION_CMD, 2, targetPos, 2));
for (let i = 0; i < 250; i++) device.tick(0.02);
check("motor 2 position converged to target", Math.abs(hostState.get(2).pos - targetPos) < 0.5);
check("motor 2 status is POSITION_CONTROL", hostState.get(2).status === MotorState.POSITION_CONTROL);

// ---------------------------------------------------------------------------
// 5. Torque command + overheat fault path through the mock link.
// ---------------------------------------------------------------------------
await transport.send(commandFrame(FrameType.TORQUE_CMD, 3, 8, 3));
for (let i = 0; i < 30; i++) device.tick(0.02);
check("motor 3 torque applied", Math.abs(hostState.get(3).torq - 8) < 1.0);

// Force an overheat on motor 3 and confirm the fault surfaces in the frame.
device.byId.get(3).temperature = 130;
device.tick(0.02);
check("motor 3 overheat -> FAULT", hostState.get(3).status === MotorState.FAULT);
check("motor 3 fault code OVERTEMP", hostState.get(3).fault === FaultCode.OVERTEMP);

// ---------------------------------------------------------------------------
// 6. Every status frame the device emits must be a valid 64-byte frame that
//    round-trips through Frame.pack/unpack (protocol integrity under load).
// ---------------------------------------------------------------------------
let allFramesValid = true;
const probe = new MockDevice(specs);
const probeTransport = new MockTransport(probe);
// The MockTransport wires device.onFrame -> transport.onFrame, so the validator
// must live on the transport (not be aliased to the device's own onFrame, which
// would recurse).
probeTransport.onFrame = (f) => {
  try {
    const raw = f.pack();
    if (raw.length !== 64) allFramesValid = false;
    Frame.unpack(raw); // throws on CRC/sync error
  } catch (_e) {
    allFramesValid = false;
  }
};
await probeTransport.connect(115200);
await probeTransport.send(commandFrame(FrameType.VELOCITY_CMD, 4, 3, 1));
for (let i = 0; i < 20; i++) probe.tick(0.02);
check("all emitted status frames are valid 64-byte frames", allFramesValid);

// ---------------------------------------------------------------------------
// 7. Disconnect cleans up state.
// ---------------------------------------------------------------------------
await transport.disconnect();
check("transport reports disconnected", transport.connected === false);
let threw = false;
try { await transport.send(commandFrame(FrameType.VELOCITY_CMD, 1, 1, 1)); } catch (_e) { threw = true; }
check("send after disconnect throws", threw);

// ---------------------------------------------------------------------------
// 8. Command console: buildCommand + applyFrame round-trip through the full
//    command array (motion, drive-state, motor-specific, params).
// ---------------------------------------------------------------------------
check("command catalog has the full array (>=15)", COMMANDS.length >= 15);
check("command groups present", Object.keys(commandGroups()).length >= 4);

// Position via the catalog builder (not the legacy helper) -> motor applies it.
const posCmd = COMMANDS.find((c) => c.id === "position");
const posFrame = buildCommand(posCmd, 1, { target: 2.5, maxSpeed: 1.0, accel: 0.5, profile: 0 }, 9);
check("buildCommand produced a POSITION_CMD frame", posFrame.frameType === FrameType.POSITION_CMD);
device.byId.get(1).applyFrame(posFrame);
for (let i = 0; i < 120; i++) device.tick(0.02);
check("catalog position command applied (converged)", Math.abs(hostState.get(1).pos - 2.5) < 0.3);

// Drive-state extension: STOP then ENABLE round-trips.
const stopCmd = COMMANDS.find((c) => c.id === "stop");
device.byId.get(1).applyFrame(buildCommand(stopCmd, 1, {}, 10));
check("STOP cleared active setpoint", device.byId.get(1).mode === "idle");

// Motor-specific: SET_BACKLASH_COMP writes into the param map + live state.
const blCmd = COMMANDS.find((c) => c.id === "setBacklashComp");
device.byId.get(1).applyFrame(buildCommand(blCmd, 1, { backlash: 35 }, 11));
check("SET_BACKLASH_COMP stored in param map", device.byId.get(1).params.get(0x0011) === 35);
check("SET_BACKLASH_COMP reflected in sim state", device.byId.get(1).backlashComp === 35);

// Generic PARAM_WRITE/READ round-trip.
const pwCmd = COMMANDS.find((c) => c.id === "paramWrite");
device.byId.get(2).applyFrame(buildCommand(pwCmd, 2, { address: 0x0010, value: 100 }, 12));
check("PARAM_WRITE stored reduction ratio", device.byId.get(2).params.get(0x0010) === 100);
const prCmd = COMMANDS.find((c) => c.id === "paramRead");
device.byId.get(2).applyFrame(buildCommand(prCmd, 2, { address: 0x0010 }, 13));
check("PARAM_READ stashed last read", device.byId.get(2)._lastParamRead &&
  device.byId.get(2)._lastParamRead.addr === 0x0010 &&
  device.byId.get(2)._lastParamRead.val === 100);

// describeFrame yields a human-readable summary.
check("describeFrame returns a string", typeof describeFrame(posFrame) === "string");

// 9. Raw native command: native byte becomes the frame commandType and the
//    raw hex payload is parsed into the frame bytes.
const rawCmd = COMMANDS.find((c) => c.id === "rawNative");
const rawFrame = buildCommand(rawCmd, 3, { nativeCmd: "0xA6", payload: "01 02 03" }, 20);
check("raw native command sets commandType from native byte", rawFrame.commandType === 0xA6);
check("raw native command is a DIAGNOSTIC frame", rawFrame.frameType === FrameType.DIAGNOSTIC);
check("raw native payload parsed into frame bytes", rawFrame.payload[0] === 0x01 && rawFrame.payload[1] === 0x02 && rawFrame.payload[2] === 0x03);
// The simulation acknowledges any DIAGNOSTIC frame (default branch).
check("raw native frame acknowledged by sim", device.byId.get(3).applyFrame(rawFrame) === true);

// 10. Native RMD-X command array is present and complete (vendor docs).
check("native RMD-X command array present (>=30 entries)", NATIVE_RMDX_COMMANDS.length >= 30);
check("native array includes Read Motor Status (0xA6)", NATIVE_RMDX_COMMANDS.some((c) => c.code === "0xA6"));
check("native array includes Clear Motor Fault (0xDA)", NATIVE_RMDX_COMMANDS.some((c) => c.code === "0xDA"));

// 11. Native RMD-X commands actually drive the simulation (not just acked).
const DEG = Math.PI / 180;
function hexLe32(n) {
  const b = new DataView(new ArrayBuffer(4));
  b.setInt32(0, n, true);
  return [0, 1, 2, 3].map((i) => b.getUint8(i).toString(16).padStart(2, "0")).join(" ");
}
function hexLe16(n) {
  const b = new DataView(new ArrayBuffer(2));
  b.setInt16(0, n, true);
  return [0, 1].map((i) => b.getUint8(i).toString(16).padStart(2, "0")).join(" ");
}
// Speed closed-loop 0xB2: int32 payload (0.01 deg/s) -> rad/s.
const spdRaw = 28648; // ~5 rad/s
const spdFrame = buildCommand(rawCmd, 4, { nativeCmd: "0xB2", payload: hexLe32(spdRaw) }, 30);
device.byId.get(4).applyFrame(spdFrame);
for (let i = 0; i < 150; i++) device.tick(0.02);
const spdTarget = spdRaw * 0.01 * DEG;
check("native 0xB2 speed drives sim velocity", Math.abs(hostState.get(4).vel - spdTarget) < 1.0);
// Torque closed-loop 0xB1: int16 payload (0.01 N·m) -> N·m.
const trqRaw = 300; // 3 N·m
const trqFrame = buildCommand(rawCmd, 5, { nativeCmd: "0xB1", payload: hexLe16(trqRaw) }, 31);
device.byId.get(5).applyFrame(trqFrame);
for (let i = 0; i < 30; i++) device.tick(0.02);
check("native 0xB1 torque drives sim torque", Math.abs(hostState.get(5).torq - trqRaw / 100) < 1.0);
// Multi-turn angle 0xB4: int32 payload (0.01 deg) -> rad.
const posRaw = 28648; // ~5 rad
const natPosFrame = buildCommand(rawCmd, 6, { nativeCmd: "0xB4", payload: hexLe32(posRaw) }, 32);
device.byId.get(6).applyFrame(natPosFrame);
for (let i = 0; i < 250; i++) device.tick(0.02);
const posTarget = posRaw * 0.01 * DEG;
check("native 0xB4 position drives sim position", Math.abs(hostState.get(6).pos - posTarget) < 0.5);
// Clear fault 0xDA: inject overtemp fault, cool, then clear via native command.
device.byId.get(5).temperature = 130; device.tick(0.02);
check("motor 5 overheat -> FAULT", hostState.get(5).status === MotorState.FAULT);
device.byId.get(5).temperature = 25; // cool below the trip threshold
const clrFrame = buildCommand(rawCmd, 5, { nativeCmd: "0xDA", payload: "" }, 33);
device.byId.get(5).applyFrame(clrFrame);
device.tick(0.02); // emit a status frame so hostState reflects the cleared fault
check("native 0xDA clears fault", hostState.get(5).fault === FaultCode.NONE);
// Encoder zero 0xC2: calibrate.
const zeroFrame = buildCommand(rawCmd, 6, { nativeCmd: "0xC2", payload: "" }, 34);
device.byId.get(6).applyFrame(zeroFrame);
check("native 0xC2 calibrates zero", device.byId.get(6).calibrated === true);

console.log(failures === 0 ? "\nHARNESS TESTS PASSED" : `\nHARNESS TESTS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
