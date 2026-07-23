// web/test/sim.test.mjs
// Sanity-checks the simulation engine dynamics and fault injection.
// Run: node web/test/sim.test.mjs
import { MotorSim, MotorState, FaultCode } from "../js/sim.js";
import { MOTOR_SERIES } from "../js/motors.js";

let failures = 0;
function check(name, cond) {
  if (cond) console.log(`  ok  ${name}`);
  else { console.error(`  FAIL ${name}`); failures++; }
}

const spec = { id: 1, series: "RMD-X", model: "EPS-RMD-X-3-100-0-M-C-17", ...MOTOR_SERIES["RMD-X"] };
const m = new MotorSim(spec);

// Idle: stepping does not move much, stays idle.
m.step(0.1);
check("idle stays IDLE", m.status === MotorState.IDLE);
check("idle position ~0", Math.abs(m.position) < 1e-6);

// Enable + velocity command -> moves.
m.enable();
m.setVelocity(5);
for (let i = 0; i < 50; i++) m.step(0.02);
check("velocity command -> RUNNING/VELOCITY", m.status === MotorState.VELOCITY_CONTROL);
check("position advanced", m.position > 0.5);
check("velocity near target", Math.abs(m.velocity - 5) < 1.0);

// Position command -> converges.
m.setPosition(10);
for (let i = 0; i < 200; i++) m.step(0.02);
check("position converges to target", Math.abs(m.position - 10) < 0.5);

// Overheat fault injection.
m.temperature = 130;
m.step(0.02);
check("overheat -> FAULT", m.status === MotorState.FAULT);
check("fault code OVERTEMP", m.fault === FaultCode.OVERTEMP);

// Clear fault.
m.clearFault();
check("clearFault -> no fault", m.fault === FaultCode.NONE);

// Status frame is a valid 64-byte frame.
const fr = m.toStatusFrame(1);
check("status frame 64 bytes", fr.pack().length === 64);

console.log(failures === 0 ? "\nSIM TESTS PASSED" : `\nSIM TESTS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
