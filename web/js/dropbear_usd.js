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

export function dropbearUsdBinding(canId) {
  return DROPBEAR_USD_BINDINGS.find((binding) => binding.canId === Number(canId));
}
