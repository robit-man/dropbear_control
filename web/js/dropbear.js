// Dropbear low-level-control digital twin.
//
// This module is a clean-room browser model grounded in the firmware at:
// https://github.com/Hyperspawn/Dropbear/tree/main/Control%20System/Low%20Level%20Control
// Observed revision: 13cf5ecaa39b8b89c794fe905dcea0490cfa7726
//
// It reproduces task cadence, command semantics, pin use, CAN traffic, sensor
// normalization, joint routing, and simplified actuator dynamics. It does not
// emulate the ESP32 instruction set and is not a validated physical plant.

export const DROPBEAR_SOURCE = Object.freeze({
  repository: "https://github.com/Hyperspawn/Dropbear",
  path: "Control System/Low Level Control",
  commit: "13cf5ecaa39b8b89c794fe905dcea0490cfa7726",
  firmware: "esp32_devkit_v1.ino",
  evidenceClass: "source-grounded synthetic digital twin",
});

export const CONTROLLER_PINS = Object.freeze([
  { gpio: 1, label: "TX0", bus: "UART", role: "Serial TX", color: "#a78bfa" },
  { gpio: 3, label: "RX0", bus: "UART", role: "Serial RX", color: "#a78bfa" },
  { gpio: 4, label: "D4", bus: "HX711", role: "Shared load-cell SCK", optional: true, color: "#fb7185" },
  { gpio: 5, label: "D5", bus: "CAN", role: "MCP2515 chip select", color: "#22d3ee" },
  { gpio: 12, label: "D12", bus: "HX711", role: "Load cell 2 DOUT", optional: true, color: "#fb7185" },
  { gpio: 13, label: "D13", bus: "HX711", role: "Load cell 3 DOUT", optional: true, color: "#fb7185" },
  { gpio: 14, label: "D14", bus: "ADC", role: "Outer calf AS5600", color: "#fbbf24" },
  { gpio: 15, label: "D15", bus: "HX711", role: "Load cell 4 DOUT", optional: true, color: "#fb7185" },
  { gpio: 17, label: "TX2", bus: "CAN", role: "MCP2515 interrupt", color: "#22d3ee" },
  { gpio: 18, label: "D18", bus: "SPI", role: "MCP2515 SCK", inferred: true, color: "#38bdf8" },
  { gpio: 19, label: "D19", bus: "SPI", role: "MCP2515 MISO", inferred: true, color: "#38bdf8" },
  { gpio: 21, label: "D21", bus: "I2C", role: "IMU SDA", color: "#34d399" },
  { gpio: 22, label: "D22", bus: "I2C", role: "IMU SCL", color: "#34d399" },
  { gpio: 23, label: "D23", bus: "SPI", role: "MCP2515 MOSI", inferred: true, color: "#38bdf8" },
  { gpio: 25, label: "D25", bus: "ADC", role: "Knee AS5600", color: "#fbbf24" },
  { gpio: 26, label: "D26", bus: "ADC", role: "Hip pitch AS5600", color: "#fbbf24" },
  { gpio: 27, label: "D27", bus: "ADC", role: "Inner calf AS5600", color: "#fbbf24" },
  { gpio: 32, label: "D32", bus: "HX711", role: "Load cell 1 DOUT", optional: true, color: "#fb7185" },
  { gpio: 33, label: "D33", bus: "ADC", role: "Hip roll / butt AS5600", color: "#fbbf24" },
]);

const joint = (id, side, key, label, sensorPin, torqueIndex) => Object.freeze({
  id,
  canId: `0x${id.toString(16).toUpperCase()}`,
  side,
  key,
  label,
  sensorPin,
  torqueIndex,
  impedanceCapable: key !== "hip_yaw",
});

// CAN IDs and torque-array indices exactly follow esp32_devkit_v1.ino.
export const JOINT_DEFINITIONS = Object.freeze([
  joint(0x141, "left", "outer_calf", "Left outer calf", 14, 1),
  joint(0x142, "left", "inner_calf", "Left inner calf", 27, 3),
  joint(0x143, "right", "inner_calf", "Right inner calf", 27, 2),
  joint(0x144, "right", "outer_calf", "Right outer calf", 14, 0),
  joint(0x145, "left", "knee", "Left knee", 25, 5),
  joint(0x146, "left", "hip_pitch", "Left hip pitch", 26, 7),
  joint(0x147, "right", "hip_pitch", "Right hip pitch", 26, 6),
  joint(0x148, "right", "knee", "Right knee", 25, 4),
  joint(0x149, "left", "hip_yaw", "Left hip yaw", null, 9),
  joint(0x14A, "left", "hip_roll", "Left hip roll", 33, 11),
  joint(0x14B, "right", "hip_roll", "Right hip roll", 33, 10),
  joint(0x14C, "right", "hip_yaw", "Right hip yaw", null, 8),
]);

export const SERIAL_COMMANDS = Object.freeze([
  "play", "stop", "config", "calibrate", "resetOffsets", "raw on",
  "raw off", "save", "saved", "chirality", "mac", "help",
  "torque <left|right> <joint> <-300..300>",
  "impedance <left|right> <joint> <0|1> <position> <velocity>",
  "constrain <joint> <min> <max>", "direction <joint> <+|->",
]);

export const TASKS = Object.freeze([
  { name: "readAndComputeTask", core: 0, periodMs: 1, role: "ADC moving average, normalize, serial CSV" },
  { name: "torqueControlTask", core: 1, periodMs: 10, role: "12 × RMD torque/stop CAN frames" },
  { name: "checkChiralityTask", core: 1, periodMs: 10, role: "Serial command parser" },
  { name: "impedanceControlTask", core: 1, periodMs: 10, role: "Five sensorized joint controllers per leg" },
]);

const DEFAULT_IMPEDANCE = Object.freeze({
  outer_calf: { k: 0.038, d: 0.018 },
  inner_calf: { k: 0.038, d: 0.018 },
  knee: { k: 0.050, d: 0.024 },
  hip_pitch: { k: 0.060, d: 0.030 },
  hip_roll: { k: 0.045, d: 0.022 },
  hip_yaw: { k: 0, d: 0 },
});

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const wrap360 = (value) => ((value % 360) + 360) % 360;
const lerp = (start, end, amount) => start + (end - start) * amount;
const smoothstep = (amount) => amount * amount * (3 - 2 * amount);

export const ALTERNATING_STEP_PERIOD_S = 2.8;

// One leg cycle. The first half is planted and the second half is swing.
// Values are actuator offsets from the calibrated 180° datum. Calf common
// motion drives the paired rods together; calf differential trims foot pitch.
export const ALTERNATING_STEP_KEYFRAMES = Object.freeze([
  Object.freeze({ phase: 0.00, mode: "heel strike", hipPitch: -16, knee: 10, calfCommon: 2, calfDiff: 0.4, hipRoll: 3.0, contact: 1.00 }),
  Object.freeze({ phase: 0.12, mode: "loading", hipPitch: -8, knee: 5, calfCommon: 0, calfDiff: 0.2, hipRoll: 4.0, contact: 1.00 }),
  Object.freeze({ phase: 0.32, mode: "mid stance", hipPitch: 4, knee: 3, calfCommon: 4, calfDiff: 0.0, hipRoll: 4.5, contact: 1.00 }),
  Object.freeze({ phase: 0.48, mode: "toe off", hipPitch: 16, knee: 10, calfCommon: -15, calfDiff: 1.2, hipRoll: 3.0, contact: 0.72 }),
  Object.freeze({ phase: 0.55, mode: "early swing", hipPitch: 7, knee: 28, calfCommon: -8, calfDiff: -0.8, hipRoll: -2.0, contact: 0.00 }),
  Object.freeze({ phase: 0.68, mode: "high knee", hipPitch: -29, knee: 52, calfCommon: 10, calfDiff: -1.6, hipRoll: -3.5, contact: 0.00 }),
  Object.freeze({ phase: 0.82, mode: "swing advance", hipPitch: -33, knee: 36, calfCommon: 14, calfDiff: -1.5, hipRoll: -2.5, contact: 0.00 }),
  Object.freeze({ phase: 0.94, mode: "pre-contact", hipPitch: -21, knee: 14, calfCommon: 3, calfDiff: 0.3, hipRoll: 1.5, contact: 0.08 }),
  Object.freeze({ phase: 1.00, mode: "heel strike", hipPitch: -16, knee: 10, calfCommon: 2, calfDiff: 0.4, hipRoll: 3.0, contact: 1.00 }),
]);

function interpolateStepKeyframes(phase) {
  const wrapped = ((phase % 1) + 1) % 1;
  let upperIndex = ALTERNATING_STEP_KEYFRAMES.findIndex((keyframe) => keyframe.phase >= wrapped);
  if (upperIndex <= 0) upperIndex = 1;
  const lower = ALTERNATING_STEP_KEYFRAMES[upperIndex - 1];
  const upper = ALTERNATING_STEP_KEYFRAMES[upperIndex];
  const span = Math.max(1e-6, upper.phase - lower.phase);
  const amount = smoothstep((wrapped - lower.phase) / span);
  const mode = amount < 0.5 ? lower.mode : upper.mode;
  return {
    phase: wrapped,
    mode,
    swing: wrapped >= 0.5,
    hipPitch: lerp(lower.hipPitch, upper.hipPitch, amount),
    knee: lerp(lower.knee, upper.knee, amount),
    calfCommon: lerp(lower.calfCommon, upper.calfCommon, amount),
    calfDiff: lerp(lower.calfDiff, upper.calfDiff, amount),
    hipRoll: lerp(lower.hipRoll, upper.hipRoll, amount),
    contact: lerp(lower.contact, upper.contact, amount),
  };
}

export function sampleAlternatingStep(timeSeconds, side = "left") {
  const sideOffset = side === "right" ? 0.5 : 0;
  const sample = interpolateStepKeyframes(timeSeconds / ALTERNATING_STEP_PERIOD_S + sideOffset);
  // The mirrored four-bar reverses differential ankle motion. Swapping the
  // right calf differential keeps physical foot-pitch intent symmetric.
  const differential = sample.calfDiff * (side === "right" ? -1 : 1);
  return {
    ...sample,
    targets: {
      hip_pitch: 180 + sample.hipPitch,
      knee: 180 + sample.knee,
      outer_calf: 180 + sample.calfCommon + differential,
      inner_calf: 180 + sample.calfCommon - differential,
      hip_roll: 180 + sample.hipRoll * (side === "left" ? 1 : -1),
    },
  };
}

function makeJoint(definition) {
  const gains = DEFAULT_IMPEDANCE[definition.key];
  return {
    ...definition,
    angle: 180,
    rawAngle: 180,
    velocity: 0,
    torque: 0,
    command: 0,
    desiredPosition: 180,
    desiredVelocity: 0,
    impedanceEnabled: false,
    stiffness: gains.k,
    damping: gains.d,
    // 180° is the mechanical knee lock. Both knees only fold in the
    // positive direction from that datum.
    minAngle: definition.key === "knee" ? 180 : 0,
    maxAngle: 360,
    direction: 1,
    adc: definition.sensorPin == null ? null : 2048,
    temperature: 28,
    sensorStuck: false,
    sensorSnapshot: 180,
    canFrames: 0,
  };
}

function makeController(side) {
  return {
    side,
    chirality: side,
    serialConnected: true,
    canOnline: true,
    i2cOnline: true,
    spiffsMounted: true,
    rawMode: false,
    offsets: [0, 0, 0, 0, 0],
    csv: "180.0,180.0,180.0,180.0,180.0",
    adcReads: 0,
    canFrames: 0,
    canErrors: 0,
    serialLines: 0,
    loopHz: 1000,
    torqueHz: 100,
  };
}

export class DropbearSim {
  constructor() {
    this.joints = JOINT_DEFINITIONS.map(makeJoint);
    this.controllers = {
      left: makeController("left"),
      right: makeController("right"),
    };
    this.running = true;
    // Firmware sets playMode=true during setup. The dashboard deliberately
    // guards motion until the operator presses PLAY.
    this.playMode = false;
    this.firmwarePlayDefault = true;
    this.time = 0;
    this.speed = 1;
    this.scenario = "neutral";
    this.scenarioStartedAt = 0;
    this.canBitrate = 1_000_000;
    this.canFramesWindow = 0;
    this.canUtilization = 0;
    this.imu = Array.from({ length: 5 }, (_, i) => ({
      address: 0x68 + i,
      ax: 0,
      ay: 0,
      az: 1,
      gx: 0,
      gy: 0,
      gz: 0,
    }));
    this.loadCells = [0, 0, 0, 0];
    this.loadCellsEnabled = false;
    this.gait = {
      left: { phase: 0, mode: "hold", swing: false, contact: 1 },
      right: { phase: 0.5, mode: "hold", swing: false, contact: 1 },
    };
    this.faults = {
      canDrop: false,
      imuDrift: false,
      serialDrop: false,
      stopIdBugObserved: true,
      impedanceParserHazardObserved: true,
    };
    this.messages = [];
    this._canAccumulator = 0;
    this._sensorAccumulator = 0;
    this._imuAccumulator = 0;
    this._historyAccumulator = 0;
    this._stopFramesPending = 0;
    this.history = [];
    this.log("Simulator booted in guarded PAUSE; firmware source defaults playMode=true.", "warn");
  }

  getJoint(idOrKey, side = null) {
    if (typeof idOrKey === "number") return this.joints.find((j) => j.id === idOrKey) || null;
    return this.joints.find((j) => j.key === idOrKey && (!side || j.side === side)) || null;
  }

  setPlay(on) {
    const wasPlaying = this.playMode;
    this.playMode = Boolean(on);
    if (wasPlaying && !this.playMode) this._stopFramesPending = 12;
    if (this.playMode) this._stopFramesPending = 0;
    this.log(this.playMode ? "Play mode enabled." : "Play mode disabled; stop frames requested.", this.playMode ? "ok" : "warn");
  }

  setScenario(name) {
    this.scenario = name;
    this.scenarioStartedAt = this.time;
    this.loadCellsEnabled = false;
    this.gait.left = { phase: 0, mode: "hold", swing: false, contact: 1 };
    this.gait.right = { phase: 0.5, mode: "hold", swing: false, contact: 1 };
    if (name !== "neutral") this.setPlay(true);
    for (const j of this.joints) {
      j.impedanceEnabled = j.impedanceCapable && name !== "manual";
      j.desiredPosition = 180;
      j.desiredVelocity = 0;
      if (name === "manual") j.command = 0;
    }
    this.log(`Scenario loaded: ${name}.`, "ok");
  }

  reset() {
    const fresh = new DropbearSim();
    const keepSpeed = this.speed;
    Object.assign(this, fresh);
    this.speed = keepSpeed;
    this.log("Simulation state reset.", "ok");
  }

  injectFault(kind, jointId = null) {
    if (kind === "can") {
      this.faults.canDrop = !this.faults.canDrop;
      for (const controller of Object.values(this.controllers)) controller.canOnline = !this.faults.canDrop;
      this.log(`CAN ${this.faults.canDrop ? "disconnected" : "restored"}.`, this.faults.canDrop ? "err" : "ok");
    } else if (kind === "imu") {
      this.faults.imuDrift = !this.faults.imuDrift;
      this.log(`IMU drift ${this.faults.imuDrift ? "injected" : "cleared"}.`, this.faults.imuDrift ? "warn" : "ok");
    } else if (kind === "serial") {
      this.faults.serialDrop = !this.faults.serialDrop;
      for (const controller of Object.values(this.controllers)) controller.serialConnected = !this.faults.serialDrop;
      this.log(`Serial links ${this.faults.serialDrop ? "dropped" : "restored"}.`, this.faults.serialDrop ? "err" : "ok");
    } else if (kind === "sensor") {
      const target = this.getJoint(jointId);
      if (target && target.sensorPin != null) {
        target.sensorStuck = !target.sensorStuck;
        target.sensorSnapshot = target.rawAngle;
        this.log(`${target.label} sensor ${target.sensorStuck ? "frozen" : "released"}.`, target.sensorStuck ? "warn" : "ok");
      }
    } else if (kind === "thermal") {
      const target = this.getJoint(jointId);
      if (target) {
        target.temperature = target.temperature > 80 ? 30 : 96;
        this.log(`${target.label} thermal state set to ${target.temperature.toFixed(0)} °C.`, target.temperature > 80 ? "err" : "ok");
      }
    }
  }

  setJointTarget(id, position, enabled = true) {
    const target = this.getJoint(id);
    if (!target || !target.impedanceCapable) return false;
    target.desiredPosition = clamp(Number(position), target.minAngle, target.maxAngle);
    target.impedanceEnabled = Boolean(enabled);
    return true;
  }

  setJointTorque(id, hundredthNm) {
    const target = this.getJoint(id);
    if (!target) return false;
    target.command = clamp(Number(hundredthNm), -300, 300) / 100;
    return true;
  }

  setConstraint(id, min, max) {
    const target = this.getJoint(id);
    if (!target || Number(min) >= Number(max)) return false;
    const mechanicalMin = target.key === "knee" ? 180 : 0;
    const nextMin = Math.max(mechanicalMin, Number(min));
    const nextMax = Math.min(360, Number(max));
    if (nextMin >= nextMax) return false;
    target.minAngle = nextMin;
    target.maxAngle = nextMax;
    target.desiredPosition = clamp(target.desiredPosition, target.minAngle, target.maxAngle);
    return true;
  }

  command(text, controllerSide = "left") {
    const command = String(text || "").trim();
    const controller = this.controllers[controllerSide] || this.controllers.left;
    if (!command) return { ok: false, output: "Empty command." };
    if (this.faults.serialDrop || !controller.serialConnected) return { ok: false, output: "Serial link unavailable." };
    controller.serialLines += 1;

    if (command === "play") {
      this.setPlay(true);
      return { ok: true, output: "Play mode enabled." };
    }
    if (command === "stop") {
      this.setPlay(false);
      return { ok: true, output: "Play mode disabled. Stopping all actuators." };
    }
    if (["left", "right", "center"].includes(command)) {
      controller.chirality = command;
      this.log(`${controllerSide} controller chirality set to ${command}.`, "ok");
      return { ok: true, output: `Chirality set to: ${command}` };
    }
    if (command === "chirality") return { ok: true, output: `Current chirality: ${controller.chirality}` };
    if (command === "raw on" || command === "raw off") {
      controller.rawMode = command.endsWith("on");
      return { ok: true, output: `Raw mode ${controller.rawMode ? "enabled" : "disabled"}.` };
    }
    if (command === "calibrate") {
      const ordered = ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"];
      controller.offsets = ordered.map((key) => {
        const target = this.getJoint(key, controllerSide);
        return target ? Math.round(180 - target.rawAngle) : 0;
      });
      return { ok: true, output: `Calibration complete: ${controller.offsets.join(",")}` };
    }
    if (command === "save") {
      return { ok: true, output: "Configuration saved to simulated SPIFFS." };
    }
    if (command === "mac") {
      return { ok: true, output: controllerSide === "left" ? "MAC Address: 02:DB:EA:00:00:01" : "MAC Address: 02:DB:EA:00:00:02" };
    }
    if (command === "help") return { ok: true, output: SERIAL_COMMANDS.join("\n") };

    const torque = command.match(/^torque\s+(left|right)\s+([a-z_]+)\s+(-?\d+)$/);
    if (torque) {
      const [, side, key, value] = torque;
      const target = this.getJoint(key, side);
      if (!target) return { ok: false, output: "Invalid appendage specified." };
      this.setJointTorque(target.id, Number(value));
      return { ok: true, output: `Torque for ${side} ${key} set to ${clamp(Number(value), -300, 300)}` };
    }

    // The source firmware's desiredVelocity substring begins one character
    // after the desiredPosition begins. The twin accepts the intended format
    // but surfaces that discrepancy in Diagnostics.
    const impedance = command.match(/^impedance\s+(left|right)\s+([a-z_]+)\s+([01])\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)$/);
    if (impedance) {
      const [, side, key, enabled, position, velocity] = impedance;
      const target = this.getJoint(key, side);
      if (!target || !target.impedanceCapable) return { ok: false, output: "Invalid appendage specified." };
      target.impedanceEnabled = enabled === "1";
      target.desiredPosition = clamp(Number(position), target.minAngle, target.maxAngle);
      target.desiredVelocity = Number(velocity);
      return { ok: true, output: `Impedance for ${side} ${key} set to ${enabled}, position: ${Number(position).toFixed(2)}, velocity: ${Number(velocity).toFixed(2)}` };
    }

    const constrain = command.match(/^constrain\s+([a-z_]+)\s+(-?\d+)\s+(-?\d+)$/);
    if (constrain) {
      const [, key, min, max] = constrain;
      const target = this.getJoint(key, controllerSide);
      if (!target || !this.setConstraint(target.id, min, max)) return { ok: false, output: "Invalid constraint." };
      return { ok: true, output: `${target.label} constrained to ${min}…${max}°.` };
    }

    const direction = command.match(/^direction\s+((?:left|right)_[a-z_]+)\s+([+-])$/);
    if (direction) {
      const [, compound, sign] = direction;
      const side = compound.startsWith("left_") ? "left" : "right";
      const key = compound.replace(/^(left|right)_/, "");
      const target = this.getJoint(key, side);
      if (!target || key === "hip_yaw") return { ok: false, output: "Invalid joint name." };
      target.direction = sign === "+" ? 1 : -1;
      return { ok: true, output: `Direction for ${compound} set to ${sign}` };
    }
    return { ok: false, output: `Unknown command: ${command}` };
  }

  step(realDt) {
    if (!this.running) return;
    const dt = clamp(realDt * this.speed, 0, 0.04);
    this.time += dt;
    this._applyScenario();
    this._sensorAccumulator += dt;
    this._canAccumulator += dt;
    this._imuAccumulator += dt;
    this._historyAccumulator += dt;

    const sensorTick = this._sensorAccumulator >= 0.001;
    const canTick = this._canAccumulator >= 0.01;
    const imuTick = this._imuAccumulator >= 0.01;
    if (sensorTick) this._sensorAccumulator %= 0.001;
    if (canTick) this._canAccumulator %= 0.01;
    if (imuTick) this._imuAccumulator %= 0.01;

    let framesThisTick = 0;
    for (const target of this.joints) {
      const controller = this.controllers[target.side];
      const sensed = target.sensorStuck ? target.sensorSnapshot : target.rawAngle;
      if (sensorTick && target.sensorPin != null) {
        target.adc = clamp(Math.round(wrap360(sensed) / 360 * 4096), 0, 4095);
        controller.adcReads += 1;
      }

      let commandedTorque = 0;
      if (this.playMode && !this.faults.canDrop) {
        commandedTorque = target.command;
        if (target.impedanceEnabled && target.sensorPin != null) {
          const positionError = clamp(target.desiredPosition, target.minAngle, target.maxAngle) - sensed;
          const velocityError = target.desiredVelocity - target.velocity;
          commandedTorque = positionError * target.stiffness + velocityError * target.damping;
        }
        commandedTorque = clamp(commandedTorque * target.direction, -3, 3);
      }
      target.torque += (commandedTorque - target.torque) * Math.min(1, dt * 30);

      // A stable, intentionally simplified joint plant in degree units.
      // Knee and calf channels retain enough bandwidth to follow the staged
      // swing trajectory instead of visually averaging it into tiny steps.
      const response = {
        knee: 120,
        outer_calf: 92,
        inner_calf: 92,
        hip_pitch: 96,
        hip_roll: 82,
        hip_yaw: 72,
      }[target.key] || 82;
      const acceleration = target.torque * response - target.velocity * 3.2;
      target.velocity = clamp(target.velocity + acceleration * dt, -180, 180);
      target.angle = clamp(target.angle + target.velocity * dt, target.minAngle, target.maxAngle);
      target.rawAngle = wrap360(target.angle);
      target.temperature += (Math.abs(target.torque) * 2.2 - (target.temperature - 28) * 0.08) * dt;

      if (canTick && (this.playMode || this._stopFramesPending > 0)) {
        // torqueControlTask writes all twelve IDs every 10 ms while playing.
        // The observed stop branch writes indices 0..11 instead of 0x141..14C.
        target.canFrames += 1;
        framesThisTick += 1;
        controller.canFrames += 1;
      }
    }

    if (canTick) {
      if (this.faults.canDrop) {
        for (const controller of Object.values(this.controllers)) controller.canErrors += 12;
      }
      this.canFramesWindow = framesThisTick;
      // Approximate one extended data frame at 128 on-wire bits.
      this.canUtilization = framesThisTick * 100 * 128 / this.canBitrate * 100;
      if (!this.playMode) this._stopFramesPending = 0;
    }

    if (sensorTick) {
      for (const side of ["left", "right"]) {
        const controller = this.controllers[side];
        const order = ["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"];
        const values = order.map((key, i) => {
          const target = this.getJoint(key, side);
          const raw = target?.rawAngle ?? 0;
          return wrap360(raw + (controller.rawMode ? 0 : controller.offsets[i])).toFixed(1);
        });
        controller.csv = values.join(",");
      }
    }

    if (imuTick) {
      const drift = this.faults.imuDrift ? (this.time - this.scenarioStartedAt) * 0.02 : 0;
      for (let i = 0; i < this.imu.length; i += 1) {
        const phase = this.time * 2 + i * 0.31;
        this.imu[i].ax = Math.sin(phase) * 0.025 + drift;
        this.imu[i].ay = Math.cos(phase * 0.8) * 0.018;
        this.imu[i].az = 1 + Math.sin(phase * 0.5) * 0.008;
        this.imu[i].gx = Math.sin(phase) * 1.5;
        this.imu[i].gy = Math.cos(phase) * 1.1;
        this.imu[i].gz = drift * 8;
      }
      const stepPhase = Math.sin(this.time * Math.PI * 2);
      if (this.loadCellsEnabled && this.scenario === "walk") {
        const leftLoad = 42 * this.gait.left.contact;
        const rightLoad = 42 * this.gait.right.contact;
        this.loadCells = [leftLoad * 0.52, leftLoad * 0.48, rightLoad * 0.48, rightLoad * 0.52];
      } else {
        this.loadCells = this.loadCells.map((_, i) => this.loadCellsEnabled
          ? Math.max(0, 18 + 14 * Math.sin(this.time * Math.PI * 2 + i * Math.PI / 2))
          : 0);
      }
      if (Math.abs(stepPhase) < 0.03 && this.scenario === "walk") this.log("Gait phase crossed neutral.", "");
    }

    if (this._historyAccumulator >= 0.04) {
      this._historyAccumulator = 0;
      const selected = this.joints[0];
      this.history.push({
        t: this.time,
        angle: selected.angle,
        desired: selected.desiredPosition,
        torque: selected.torque,
      });
      while (this.history.length > 250) this.history.shift();
    }
  }

  _applyScenario() {
    const t = this.time - this.scenarioStartedAt;
    if (this.scenario === "walk") {
      const samples = {
        left: sampleAlternatingStep(t, "left"),
        right: sampleAlternatingStep(t, "right"),
      };
      const future = {
        left: sampleAlternatingStep(t + 0.01, "left"),
        right: sampleAlternatingStep(t + 0.01, "right"),
      };
      this.gait.left = samples.left;
      this.gait.right = samples.right;
      for (const target of this.joints) {
        if (!target.impedanceCapable) continue;
        const desired = samples[target.side].targets[target.key] ?? 180;
        const nextDesired = future[target.side].targets[target.key] ?? desired;
        target.desiredPosition = clamp(desired, target.minAngle, target.maxAngle);
        target.desiredVelocity = clamp((nextDesired - desired) / 0.01, -140, 140);
      }
      this.loadCellsEnabled = true;
    } else if (this.scenario === "sensor-sweep") {
      for (const target of this.joints) {
        if (!target.impedanceCapable) continue;
        const wave = Math.sin(t * 0.9 + target.torqueIndex * 0.23);
        target.desiredPosition = target.key === "knee"
          ? 180 + (wave + 1) * 22.5
          : 180 + wave * 45;
      }
    } else if (this.scenario === "balance") {
      for (const target of this.joints) {
        if (!target.impedanceCapable) continue;
        const sign = target.side === "left" ? 1 : -1;
        target.desiredPosition = 180 + (target.key === "hip_roll" ? sign * Math.sin(t * 1.2) * 7 : 0);
      }
      this.loadCellsEnabled = true;
    }
  }

  log(message, kind = "") {
    this.messages.unshift({ t: this.time, message, kind });
    if (this.messages.length > 160) this.messages.length = 160;
  }
}
