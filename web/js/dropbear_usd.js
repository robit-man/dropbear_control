export const DROPBEAR_USD_SOURCE = Object.freeze({
  repository: "https://github.com/robit-man/dropbear-locomotion",
  commit: "a397be863fed2d328c2e8f62c3db2f1e23575eb1",
  path: "dropbear_walk/isaaclab_asset/dropbear.usd",
  sha256: "45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f",
  license: "CC-BY-NC-SA-4.0",
  attribution: "Hyperspawn Robotics — Priyanshu Pareek and Cole Myers",
});

export const DROPBEAR_MOTOR_PROFILES = Object.freeze({
  x8V17: Object.freeze({
    motor: "RMD-X8",
    variant: "RMD-X8 Pro",
    modelName: "MyActuator RMD-X8 Pro 1:9",
    motorFirmware: "V1.7",
    reductionRatio: 9,
    angleReference: "output shaft",
    anglePayload: "signed 56-bit LE · DATA[1..7] · 0.01°",
    encoderProfile: "motor 0x92 + independent AS5600 boot reference",
  }),
  x10V42: Object.freeze({
    motor: "RMD-X10",
    variant: "RMD-X10 Pro",
    modelName: "MyActuator RMD-X10 Pro 1:7",
    motorFirmware: "V4.2+",
    reductionRatio: 7,
    angleReference: "output shaft",
    anglePayload: "signed 32-bit LE · DATA[4..7] · 0.01°",
    encoderProfile: "motor 0x92 + independent AS5600 where installed",
  }),
});

export const DROPBEAR_USD_BINDINGS = Object.freeze([
  { canId: 0x141, canLabel: "0x141", side: "left", firmwareJoint: "outer_calf", usdJoint: "LL_Revolute81", closure: false, ...DROPBEAR_MOTOR_PROFILES.x8V17 },
  { canId: 0x142, canLabel: "0x142", side: "left", firmwareJoint: "inner_calf", usdJoint: "LL_Revolute67", closure: false, ...DROPBEAR_MOTOR_PROFILES.x8V17 },
  { canId: 0x143, canLabel: "0x143", side: "right", firmwareJoint: "inner_calf", usdJoint: "RL_Revolute67", closure: false, ...DROPBEAR_MOTOR_PROFILES.x8V17 },
  { canId: 0x144, canLabel: "0x144", side: "right", firmwareJoint: "outer_calf", usdJoint: "RL_Revolute81", closure: false, ...DROPBEAR_MOTOR_PROFILES.x8V17 },
  { canId: 0x145, canLabel: "0x145", side: "left", firmwareJoint: "knee", usdJoint: "LL_knee_actuator_joint", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x146, canLabel: "0x146", side: "left", firmwareJoint: "hip_pitch", usdJoint: "LL_hip_joint", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x147, canLabel: "0x147", side: "right", firmwareJoint: "hip_pitch", usdJoint: "RL_hip_joint", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x148, canLabel: "0x148", side: "right", firmwareJoint: "knee", usdJoint: "RL_knee_actuator_joint", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x149, canLabel: "0x149", side: "left", firmwareJoint: "hip_yaw", usdJoint: "PG_left_leg_roll", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42, variant: "RMD-X10 base", modelName: "MyActuator RMD-X10 base 1:7", encoderProfile: "motor 0x92; no AS5600" },
  { canId: 0x14A, canLabel: "0x14A", side: "left", firmwareJoint: "hip_roll", usdJoint: "PG_left_leg_pitch", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x14B, canLabel: "0x14B", side: "right", firmwareJoint: "hip_roll", usdJoint: "PG_right_leg_pitch", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42 },
  { canId: 0x14C, canLabel: "0x14C", side: "right", firmwareJoint: "hip_yaw", usdJoint: "PG_right_leg_roll", closure: false, ...DROPBEAR_MOTOR_PROFILES.x10V42, variant: "RMD-X10 base", modelName: "MyActuator RMD-X10 base 1:7", encoderProfile: "motor 0x92; no AS5600" },
]);

// Arm axes are present in the ground-truth USD but are not assigned CAN IDs by
// the observed two-ESP32 leg firmware. The torso rotor bodies identify the two
// shoulder-pitch drives as RMD-X10; the remaining arm axes use RMD-X8. The USD
// calls those torso-root joints LH_yaw/RH_yaw, so the physical semantic
// correction is kept explicit instead of silently relabeling the source.
export const DROPBEAR_ARM_MOTOR_BINDINGS = Object.freeze([
  { id: "arm-left-shoulder-pitch", side: "left", label: "Left shoulder pitch", semanticJoint: "shoulder_pitch", usdJoint: "LH_yaw", motor: "RMD-X10", mount: "torso", sourceSemantic: "authored as LH_yaw" },
  { id: "arm-left-shoulder-yaw", side: "left", label: "Left shoulder yaw", semanticJoint: "shoulder_yaw", usdJoint: "LH_pitch", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as LH_pitch" },
  { id: "arm-left-shoulder-roll", side: "left", label: "Left shoulder roll", semanticJoint: "shoulder_roll", usdJoint: "LH_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as LH_roll" },
  { id: "arm-left-elbow-pitch", side: "left", label: "Left elbow pitch", semanticJoint: "elbow_pitch", usdJoint: "LH_Revolute41", motor: "RMD-X8", mount: "arm", sourceSemantic: "actuated as LH_Revolute41", closedLoop: true },
  { id: "arm-left-wrist-roll", side: "left", label: "Left wrist roll", semanticJoint: "wrist_roll", usdJoint: "LH_wrist_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as LH_wrist_roll" },
  { id: "arm-right-shoulder-pitch", side: "right", label: "Right shoulder pitch", semanticJoint: "shoulder_pitch", usdJoint: "RH_yaw", motor: "RMD-X10", mount: "torso", sourceSemantic: "authored as RH_yaw" },
  { id: "arm-right-shoulder-yaw", side: "right", label: "Right shoulder yaw", semanticJoint: "shoulder_yaw", usdJoint: "RH_pitch", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_pitch" },
  { id: "arm-right-shoulder-roll", side: "right", label: "Right shoulder roll", semanticJoint: "shoulder_roll", usdJoint: "RH_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_roll" },
  { id: "arm-right-elbow-pitch", side: "right", label: "Right elbow pitch", semanticJoint: "elbow_pitch", usdJoint: "RH_Revolute41", motor: "RMD-X8", mount: "arm", sourceSemantic: "actuated as RH_Revolute41", closedLoop: true },
  { id: "arm-right-wrist-roll", side: "right", label: "Right wrist roll", semanticJoint: "wrist_roll", usdJoint: "RH_wrist_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_wrist_roll" },
]);

export function dropbearUsdBinding(canId) {
  return DROPBEAR_USD_BINDINGS.find((binding) => binding.canId === Number(canId));
}

export function dropbearArmMotorBinding(id) {
  return DROPBEAR_ARM_MOTOR_BINDINGS.find((binding) => binding.id === id);
}
