// web/js/sim.js
//
// Lightweight real-time simulation of a single MyActuator motor. Integrates a
// simple second-order model from commanded setpoints and emits contract-shaped
// STATUS_REPORT frames. This is the "in sim" visualization backend for the
// dashboard; it is NOT a hardware model and the dynamics are intentionally
// simplified (proportional control + thermal load model).

import { Frame, FrameType } from "./protocol.js";
import { CtrlCode } from "./commands.js";
import { assertToySimulationSpec } from "./motors.js";

export const MotorState = {
  IDLE: 0,
  READY: 1,
  ENABLED: 2,
  RUNNING: 3,
  FAULT: 4,
  DISABLED: 5,
  POSITION_CONTROL: 6,
  VELOCITY_CONTROL: 7,
  TORQUE_CONTROL: 8,
};

export const FaultCode = {
  NONE: 0,
  OVERTEMP: 1,
  OVERCURRENT: 2,
  OVERVOLTAGE: 3,
  UNDERVOLTAGE: 4,
  ENCODER: 5,
  COMM_TIMEOUT: 6,
  POSITION_ERR: 7,
  INTERNAL: 8,
};

export class MotorSim {
  constructor(spec) {
    assertToySimulationSpec(spec);
    this.spec = spec; // { id, series, model, maxTorque, maxVelocity, inertia, ... }
    this.backendId = spec.simulationBackendId;
    this.backendKind = spec.simulationBackendKind;
    this.evidenceClass = spec.simulationEvidenceClass;
    this.substitutionScope = spec.simulationSubstitutionScope;
    this.parameterSetId = spec.simulationParameterSetId;
    this.physicalPlantSupported = false;
    this.id = spec.id;
    this.position = 0; // rad
    this.velocity = 0; // rad/s
    this.torque = 0; // N·m
    this.temperature = 25; // °C
    this.status = MotorState.IDLE;
    this.fault = FaultCode.NONE;
    this.mode = "idle"; // idle | position | velocity | torque
    this.target = { position: 0, velocity: 0, torque: 0 };
    this.enabled = false;
    this.uptime = 0; // seconds
    this.params = new Map(); // address(uint16) -> value(uint32) for PARAM_READ/WRITE
    this.backlashComp = 0; // arc-sec, set via SET_BACKLASH_COMP

    // --- encoder / calibration state ---
    // as5600: an AS5600 magnetic encoder has been added to the output shaft
    //   (aftermarket, for absolute angle readout on incremental-only units).
    // calibrated: a zero reference has been captured (CALIBRATE_ENCODER).
    // calibrationOffset: position (rad) captured as the zero reference.
    this.as5600 = false;
    this.calibrated = false;
    this.calibrationOffset = 0; // rad
  }

  // Attach/detach an AS5600 on the output shaft. Incremental-only legacy units
  // gain an absolute reference once this is enabled.
  setAs5600(on) {
    this.as5600 = !!on;
    if (!this.as5600) {
      this.calibrated = false;
      this.calibrationOffset = 0;
    }
  }

  // Capture the current position as the zero reference (contract §8.3
  // CALIBRATE_ENCODER). Only meaningful when an AS5600 is present, but allowed
  // for any unit to set a homing reference.
  calibrate() {
    this.calibrationOffset = this.position;
    this.calibrated = true;
    return this.calibrationOffset;
  }

  // Position relative to the captured zero reference (rad).
  get zeroedPosition() {
    return this.position - this.calibrationOffset;
  }

  enable() {
    this.enabled = true;
    if (this.status !== MotorState.FAULT) this.status = MotorState.ENABLED;
  }

  disable() {
    this.enabled = false;
    this.mode = "idle";
    this.torque = 0;
    this.status = MotorState.DISABLED;
  }

  clearFault() {
    this.fault = FaultCode.NONE;
    if (this.status === MotorState.FAULT) this.status = this.enabled ? MotorState.ENABLED : MotorState.IDLE;
  }

  // Apply an incoming command frame from the host (dashboard / WebSerial).
  // Handles the full command array: motion commands, drive-state control
  // extensions (CtrlCode), and PARAM_READ/PARAM_WRITE. Returns true if the
  // frame was an actionable command (so the caller can echo a status report).
  applyFrame(frame) {
    const dv = new DataView(frame.payload.buffer, frame.payload.byteOffset, frame.payload.byteLength);
    switch (frame.frameType) {
      case FrameType.POSITION_CMD:
        this.enable();
        this.setPosition(dv.getInt32(0, true) / 1000); // mrad -> rad
        return true;
      case FrameType.VELOCITY_CMD:
        this.enable();
        this.setVelocity(dv.getInt32(0, true) / 1000); // mrad/s -> rad/s
        return true;
      case FrameType.TORQUE_CMD:
        this.enable();
        this.setTorque(dv.getInt16(0, true) / 100); // 0.01 N·m -> N·m
        return true;
      case FrameType.PARAM_READ: {
        const addr = dv.getUint16(0, true);
        const val = this.params.has(addr) ? this.params.get(addr) : 0;
        // The fixed STATUS_REPORT layout has no param-echo field, so stash the
        // read result for the dashboard to surface via the param map.
        this._lastParamRead = { addr, val };
        return true;
      }
      case FrameType.PARAM_WRITE: {
        // Two layouts share PARAM_WRITE:
        //  - generic param access (commandType 0x00): addr(2) + value(4)
        //  - motor-specific sub-commands (0x11/0x13/0x15): value at offset 0
        if (frame.commandType === 0x00) {
          const addr = dv.getUint16(0, true);
          const val = dv.getUint32(2, true);
          this.params.set(addr, val >>> 0);
          if (addr === 0x0010) this.spec.reductionRatio = val; // reduction ratio
          if (addr === 0x0011) this.backlashComp = val; // backlash (arc-sec)
        } else if (frame.commandType === 0x11) {
          const val = dv.getUint16(0, true);
          this.params.set(0x0010, val); this.spec.reductionRatio = val;
        } else if (frame.commandType === 0x13) {
          const val = dv.getUint16(0, true);
          this.params.set(0x0011, val); this.backlashComp = val; // backlash (arc-sec)
        } else if (frame.commandType === 0x15) {
          // SET_THERMAL_MODEL: time constant (offset 0) + resistance (offset 2)
          this.params.set(0x0013, dv.getUint16(0, true));
          this.params.set(0x0014, dv.getUint16(2, true));
        }
        return true;
      }
      case FrameType.DIAGNOSTIC:
        switch (frame.commandType) {
          case CtrlCode.ENABLE: this.enable(); return true;
          case CtrlCode.DISABLE: this.disable(); return true;
          case CtrlCode.STOP:
            this.mode = "idle"; this.target.position = this.position;
            this.target.velocity = 0; this.target.torque = 0;
            this.torque = 0; return true;
          case CtrlCode.ZERO: this.calibrate(); return true;
          case CtrlCode.CLEAR_FAULT: this.clearFault(); return true;
          default: return this._applyNative(frame); // native RMD-X command or generic diagnostic
        }
      case FrameType.HEARTBEAT:
        return true; // acknowledge with a status report
      default:
        return false; // not an actionable command
    }
  }

  // Apply a native RMD-X CAN command (issued via the "Raw Native Command" entry
  // as a DIAGNOSTIC frame with the vendor byte in commandType). Reads are
  // acknowledged; motion / calibration / fault commands drive the simulation.
  // Payload units follow the vendor RMD-X motion protocol (degrees, 0.01 N·m).
  _applyNative(frame) {
    const dv = new DataView(frame.payload.buffer, frame.payload.byteOffset, frame.payload.byteLength);
    const DEG = Math.PI / 180;
    switch (frame.commandType) {
      // --- write (motion) commands ---
      case 0xB1: // torque closed-loop
      case 0xB3: { // torque open-loop
        const t = dv.getInt16(0, true) / 100; // 0.01 N·m -> N·m
        this.enable(); this.setTorque(t); return true;
      }
      case 0xB2: { // speed closed-loop (0.01 deg/s -> rad/s)
        const v = dv.getInt32(0, true) * 0.01 * DEG;
        this.enable(); this.setVelocity(v); return true;
      }
      case 0xB4: // multi-turn absolute angle
      case 0xB5: { // single-circle angle (0.01 deg -> rad)
        const p = dv.getInt32(0, true) * 0.01 * DEG;
        this.enable(); this.setPosition(p); return true;
      }
      case 0xB6: { // relative angle (incremental, 0.01 deg -> rad)
        const d = dv.getInt32(0, true) * 0.01 * DEG;
        this.enable(); this.setPosition(this.position + d); return true;
      }
      case 0xC2: // write encoder zero (calibrate)
        this.calibrate(); return true;
      case 0xDA: // clear motor fault
        this.clearFault(); return true;
      default:
        // Read commands (0x30..0x67, 0xA1..0xA8, 0xC1, 0xC3..0xC8) and any
        // unimplemented write: acknowledge so the host sees a status report.
        this._lastNativeCmd = frame.commandType;
        return true;
    }
  }

  setPosition(p) {
    this.mode = "position";
    this.target.position = p;
    if (this.enabled) this.status = MotorState.POSITION_CONTROL;
  }

  setVelocity(v) {
    this.mode = "velocity";
    this.target.velocity = v;
    if (this.enabled) this.status = MotorState.VELOCITY_CONTROL;
  }

  setTorque(t) {
    this.mode = "torque";
    this.target.torque = t;
    if (this.enabled) this.status = MotorState.TORQUE_CONTROL;
  }

  step(dt) {
    this.uptime += dt;
    const maxV = this.spec.maxVelocity;
    const maxT = this.spec.maxTorque;

    if (!this.enabled) {
      this.velocity *= 0.9;
      this.position += this.velocity * dt;
      this.torque = 0;
      this._thermal(dt);
      this._faults();
      return;
    }

    if (this.mode === "position") {
      const err = this.target.position - this.position;
      const v = Math.sign(err) * Math.min(Math.abs(err) * 8, maxV);
      this.velocity = v;
      this.position += v * dt;
      this.torque = clamp(err * 2, -maxT, maxT);
    } else if (this.mode === "velocity") {
      const err = this.target.velocity - this.velocity;
      this.velocity += Math.sign(err) * Math.min(Math.abs(err) * 5, maxV) * dt;
      this.velocity = clamp(this.velocity, -maxV, maxV);
      this.position += this.velocity * dt;
      this.torque = clamp(err * 1.5, -maxT, maxT);
    } else if (this.mode === "torque") {
      this.torque = clamp(this.target.torque, -maxT, maxT);
      const inertia = this.spec.inertia || 0.01;
      this.velocity += (this.torque / inertia) * dt;
      this.velocity = clamp(this.velocity, -maxV, maxV);
      this.position += this.velocity * dt;
    } else {
      this.velocity *= 0.95;
      this.position += this.velocity * dt;
    }

    this._thermal(dt);
    this._faults();
  }

  _thermal(dt) {
    const load = (this.torque * this.torque) / (this.spec.maxTorque * this.spec.maxTorque + 1e-6);
    const heat = load * 30; // °C/s at full load
    const cool = (this.temperature - 25) * 0.05;
    this.temperature += (heat - cool) * dt;
    if (this.temperature < 25) this.temperature = 25;
  }

  _faults() {
    if (this.temperature > 120) {
      this.fault = FaultCode.OVERTEMP;
      this.status = MotorState.FAULT;
    } else if (Math.abs(this.torque) > this.spec.maxTorque * 1.5) {
      this.fault = FaultCode.OVERCURRENT;
      this.status = MotorState.FAULT;
    } else {
      this.fault = FaultCode.NONE;
    }
  }

  // Produce a contract-shaped STATUS_REPORT frame (section 3.4.1).
  // Position/velocity scaled to integer "counts" (mrad) for wire transport.
  toStatusFrame(seq) {
    const payload = new Uint8Array(32);
    const dv = new DataView(payload.buffer);
    dv.setInt32(0, Math.round(this.position * 1000), true); // mrad
    dv.setInt32(4, Math.round(this.velocity * 1000), true); // mrad/s
    dv.setInt16(8, Math.round(this.torque * 100), true); // 0.01 N·m
    payload[10] = Math.round(this.temperature) & 0xff; // °C
    dv.setUint16(11, this.status & 0xffff, true); // status word
    dv.setUint8(13, this.fault & 0xff); // fault code
    return new Frame({
      frameType: FrameType.STATUS_REPORT,
      motorId: this.id,
      commandType: 0x00,
      payload,
      sequence: seq & 0xff,
    });
  }
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
