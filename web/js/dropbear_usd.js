export const DROPBEAR_USD_SOURCE = Object.freeze({
  repository: "https://github.com/Hyperspawn/dropbear_rl",
  commit: "3c37aedce6d445205671d5714d05ae28b8c90e2c",
  path: "dropbear_model/Dropbear/usd/dropbear.usd",
  sha256: "ef4434e0adb5a74cb0fe8e779c49aac4ebdcba48998ed519cf17ab16d822e073",
  license: "CC-BY-NC-SA-4.0",
  attribution: "Hyperspawn Robotics — Priyanshu Pareek and Cole Myers",
});

export const DROPBEAR_USD_BINDINGS = Object.freeze([
  { canId: 0x141, canLabel: "0x141", side: "left", firmwareJoint: "outer_calf", usdJoint: "LL_Revolute81", closure: false, motor: "RMD-X8" },
  { canId: 0x142, canLabel: "0x142", side: "left", firmwareJoint: "inner_calf", usdJoint: "LL_Revolute67", closure: false, motor: "RMD-X8" },
  { canId: 0x143, canLabel: "0x143", side: "right", firmwareJoint: "inner_calf", usdJoint: "RL_Revolute67", closure: false, motor: "RMD-X8" },
  { canId: 0x144, canLabel: "0x144", side: "right", firmwareJoint: "outer_calf", usdJoint: "RL_Revolute81", closure: false, motor: "RMD-X8" },
  { canId: 0x145, canLabel: "0x145", side: "left", firmwareJoint: "knee", usdJoint: "LL_knee_actuator_joint", closure: false },
  { canId: 0x146, canLabel: "0x146", side: "left", firmwareJoint: "hip_pitch", usdJoint: "LL_hip_joint", closure: false },
  { canId: 0x147, canLabel: "0x147", side: "right", firmwareJoint: "hip_pitch", usdJoint: "RL_hip_joint", closure: false },
  { canId: 0x148, canLabel: "0x148", side: "right", firmwareJoint: "knee", usdJoint: "RL_knee_actuator_joint", closure: false },
  { canId: 0x149, canLabel: "0x149", side: "left", firmwareJoint: "hip_yaw", usdJoint: "PG_left_leg_roll", closure: false },
  { canId: 0x14A, canLabel: "0x14A", side: "left", firmwareJoint: "hip_roll", usdJoint: "PG_left_leg_pitch", closure: false },
  { canId: 0x14B, canLabel: "0x14B", side: "right", firmwareJoint: "hip_roll", usdJoint: "PG_right_leg_pitch", closure: false },
  { canId: 0x14C, canLabel: "0x14C", side: "right", firmwareJoint: "hip_yaw", usdJoint: "PG_right_leg_roll", closure: false },
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
  { id: "arm-left-elbow-pitch", side: "left", label: "Left elbow pitch", semanticJoint: "elbow_pitch", usdJoint: "LH_elbow_joint", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as LH_elbow_joint" },
  { id: "arm-left-wrist-roll", side: "left", label: "Left wrist roll", semanticJoint: "wrist_roll", usdJoint: "LH_wrist_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as LH_wrist_roll" },
  { id: "arm-right-shoulder-pitch", side: "right", label: "Right shoulder pitch", semanticJoint: "shoulder_pitch", usdJoint: "RH_yaw", motor: "RMD-X10", mount: "torso", sourceSemantic: "authored as RH_yaw" },
  { id: "arm-right-shoulder-yaw", side: "right", label: "Right shoulder yaw", semanticJoint: "shoulder_yaw", usdJoint: "RH_pitch", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_pitch" },
  { id: "arm-right-shoulder-roll", side: "right", label: "Right shoulder roll", semanticJoint: "shoulder_roll", usdJoint: "RH_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_roll" },
  { id: "arm-right-elbow-pitch", side: "right", label: "Right elbow pitch", semanticJoint: "elbow_pitch", usdJoint: "RH_elbow_joint", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_elbow_joint" },
  { id: "arm-right-wrist-roll", side: "right", label: "Right wrist roll", semanticJoint: "wrist_roll", usdJoint: "RH_wrist_roll", motor: "RMD-X8", mount: "arm", sourceSemantic: "authored as RH_wrist_roll" },
]);

export function dropbearUsdBinding(canId) {
  return DROPBEAR_USD_BINDINGS.find((binding) => binding.canId === Number(canId));
}

export function dropbearArmMotorBinding(id) {
  return DROPBEAR_ARM_MOTOR_BINDINGS.find((binding) => binding.id === id);
}
