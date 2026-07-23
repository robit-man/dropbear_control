// web/test/e2e.test.mjs
//
// End-to-end verification of the dashboard <-> firmware frame contract.
//
// The firmware SerialBridge (src/serial_bridge.cpp) packs a STATUS_REPORT with
// this payload layout (mirrored in web/js/sim.js MotorSim.toStatusFrame):
//   offset 0  int32  position  (mrad)
//   offset 4  int32  velocity  (mrad/s)
//   offset 8  int16  torque    (0.01 N·m)
//   offset 10 uint8  temperature (°C)
//   offset 11 uint16 status word
//   offset 13 uint8  fault code
//
// The dashboard decodes that same layout in onSerialFrame() (app.js). This test
// proves the two stay in lockstep: a MotorSim status frame, when decoded with
// the dashboard's decoder, reconstructs the original telemetry; and the live
// pin view derived from that state marks the correct pins active.
//
// Run: node web/test/e2e.test.mjs

import { MotorSim, MotorState, FaultCode } from "../js/sim.js";
import { MOTOR_SERIES } from "../js/motors.js";
import { Frame, FrameType } from "../js/protocol.js";
import { livePinView, DATA_FLOW } from "../js/pins.js";

let failures = 0;
function check(name, cond) {
  if (cond) console.log(`  ok  ${name}`);
  else { console.error(`  FAIL ${name}`); failures++; }
}

// --- dashboard decoder (copied verbatim from app.js onSerialFrame) ----------
function decodeStatusFrame(f) {
  const dv = new DataView(f.payload.buffer, f.payload.byteOffset, f.payload.byteLength);
  return {
    position: dv.getInt32(0, true) / 1000,
    velocity: dv.getInt32(4, true) / 1000,
    torque: dv.getInt16(8, true) / 100,
    temperature: f.payload[10],
    status: dv.getUint16(11, true),
    fault: f.payload[13],
  };
}

// 1. Build a motor, drive it, emit a status frame, decode it back.
const spec = { id: 1, series: "RMD-X", model: "EPS-RMD-X-3-100-0-M-C-17", ...MOTOR_SERIES["RMD-X"] };
const m = new MotorSim(spec);
m.enable();
m.setVelocity(5);
for (let i = 0; i < 60; i++) m.step(0.02);
m.temperature = 48;

const frame = m.toStatusFrame(7);
check("status frame is 64 bytes", frame.pack().length === 64);

const dec = decodeStatusFrame(frame);
check("decoded position matches sim", Math.abs(dec.position - m.position) < 1e-3);
check("decoded velocity matches sim", Math.abs(dec.velocity - m.velocity) < 1e-3);
check("decoded torque matches sim", Math.abs(dec.torque - m.torque) < 1e-2);
check("decoded temperature matches sim", dec.temperature === Math.round(m.temperature));
check("decoded status word matches sim", dec.status === m.status);
check("decoded fault matches sim", dec.fault === m.fault);

// 2. Live pin view reflects the driven state (PWM + quad active, fault LED off).
const boardPins = {
  PIN_ENCODER_A: 4, PIN_ENCODER_B: 5, PIN_ENCODER_Z: 16,
  PIN_MOTOR_PWM_A: 18, PIN_MOTOR_PWM_B: 19,
  PIN_CURRENT_SENSE: 34, PIN_TEMP_SENSE: 35,
  PIN_CAN_TX: 22, PIN_CAN_RX: 23,
  PIN_RS485_TX: 17, PIN_RS485_RX: 15,
  PIN_STATUS_LED: 2, PIN_FAULT_LED: 25,
};
const view = livePinView(boardPins, m);
const byName = Object.fromEntries(view.map((p) => [p.name, p]));

check("13 pins in view", view.length === 13);
check("PWM_A active while torque > 0", byName.PIN_MOTOR_PWM_A.active === true);
check("PWM_A metric shows torque", byName.PIN_MOTOR_PWM_A.metric.includes("N·m"));
check("ENCODER_A active while moving", byName.PIN_ENCODER_A.active === true);
check("TEMP_SENSE always active (analog)", byName.PIN_TEMP_SENSE.active === true);
check("FAULT_LED inactive (no fault)", byName.PIN_FAULT_LED.active === false);
check("STATUS_LED active (enabled)", byName.PIN_STATUS_LED.active === true);

// 3. Idle motor -> PWM/quad pins go inactive.
const idle = new MotorSim(spec);
const idleView = livePinView(boardPins, idle);
const idleByName = Object.fromEntries(idleView.map((p) => [p.name, p]));
check("idle PWM_A inactive", idleByName.PIN_MOTOR_PWM_A.active === false);
check("idle ENCODER_A inactive", idleByName.PIN_ENCODER_A.active === false);

// 4. Faulted motor -> FAULT_LED active, STATUS_LED off.
const faulted = new MotorSim(spec);
faulted.enable();
faulted.temperature = 130;
faulted.step(0.02);
const fView = livePinView(boardPins, faulted);
const fByName = Object.fromEntries(fView.map((p) => [p.name, p]));
check("faulted FAULT_LED active", fByName.PIN_FAULT_LED.active === true);
check("faulted STATUS_LED inactive", fByName.PIN_STATUS_LED.active === false);

// 5. Data-flow edges present and reference real pins.
check("DATA_FLOW has 9 edges", DATA_FLOW.length === 9);
check("DATA_FLOW references CAN pins", DATA_FLOW.some((e) => e.pin === "PIN_CAN_TX" && e.pin2 === "PIN_CAN_RX"));

console.log(failures === 0 ? "\nE2E TESTS PASSED" : `\nE2E TESTS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
