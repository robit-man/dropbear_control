const RIGHT_DEFAULT_STANCE = Object.freeze({
  outer_calf: Object.freeze({
    rawDatumDeg: 125,
    referenceDeg: 0,
    lowerDeg: -60,
    upperDeg: 50,
    observedRangeDeg: Object.freeze([119, 130]),
  }),
  inner_calf: Object.freeze({
    rawDatumDeg: 188,
    referenceDeg: -11.459156,
    lowerDeg: -50,
    upperDeg: 60,
    observedRangeDeg: Object.freeze([175, 197]),
  }),
  hip_pitch: Object.freeze({
    rawDatumDeg: 89,
    referenceDeg: 0,
    lowerDeg: -50,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([86, 92]),
  }),
  knee: Object.freeze({
    rawDatumDeg: 28,
    referenceDeg: 17.188734,
    lowerDeg: 0,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([0, 359]),
    captureQuality: "unstable_multimodal_wrap_reading",
  }),
  hip_roll: Object.freeze({
    rawDatumDeg: 169,
    referenceDeg: -5.729578,
    lowerDeg: -30,
    upperDeg: 15,
    observedRangeDeg: Object.freeze([164, 173]),
  }),
});

const LEFT_DEFAULT_STANCE = Object.freeze({
  outer_calf: Object.freeze({
    rawDatumDeg: 194,
    referenceDeg: 0,
    lowerDeg: -50,
    upperDeg: 60,
    observedRangeDeg: Object.freeze([192, 197]),
  }),
  inner_calf: Object.freeze({
    rawDatumDeg: 72,
    referenceDeg: -11.459156,
    lowerDeg: -50,
    upperDeg: 60,
    observedRangeDeg: Object.freeze([63, 204]),
    captureQuality: "unstable_bimodal_reading",
  }),
  hip_pitch: Object.freeze({
    rawDatumDeg: 10,
    referenceDeg: 0,
    lowerDeg: -50,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([6, 13]),
  }),
  knee: Object.freeze({
    rawDatumDeg: 213,
    referenceDeg: 17.188734,
    lowerDeg: 0,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([212, 215]),
  }),
  hip_roll: Object.freeze({
    rawDatumDeg: 146,
    referenceDeg: -5.729578,
    lowerDeg: -15,
    upperDeg: 30,
    observedRangeDeg: Object.freeze([143, 150]),
  }),
});

export const HARDWARE_DEFAULT_STANCE_CALIBRATION = Object.freeze({
  schema: "dropbear-default-stance-calibration-v1",
  units: "degrees",
  source: Object.freeze({
    repository: "https://github.com/robit-man/dropbear-locomotion",
    commit: "a397be863fed2d328c2e8f62c3db2f1e23575eb1",
    usdSha256: "45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f",
  }),
  capture: Object.freeze({
    mode: "read_only",
    estimator: "median",
    sides: Object.freeze({
      left: Object.freeze({
        usbPath: "1.2",
        sampleCount: 86,
        durationSeconds: 5,
        capturedAt: "2026-09-14T17:56:00-07:00",
      }),
      right: Object.freeze({
        usbPath: "1.1",
        sampleCount: 190,
        durationSeconds: 5,
        capturedAt: "2026-09-15T00:24:00-07:00",
      }),
    }),
  }),
  sides: Object.freeze({
    left: RIGHT_DEFAULT_STANCE,
    right: LEFT_DEFAULT_STANCE,
  }),
  directionEvidence: "provisional_positive_until_read_only_motion_validation",
});

export const SOFTWARE_ZERO_SCHEMA = "dropbear-browser-software-zero-v4";
const SENSOR_JOINTS = Object.freeze(["outer_calf", "inner_calf", "hip_pitch", "knee", "hip_roll"]);
const MOTOR_JOINTS = Object.freeze([...SENSOR_JOINTS, "hip_yaw"]);
const ALL_SENSOR_MASK = (1 << SENSOR_JOINTS.length) - 1;
const HIP_YAW_CALIBRATION = Object.freeze({
  referenceDeg: 0,
  lowerDeg: -30,
  upperDeg: 30,
  observedRangeDeg: Object.freeze([]),
  captureQuality: "motor_zero_required",
});

function shortestDegreeDelta(next, previous) {
  return ((next - previous + 540) % 360) - 180;
}

export function softwareZeroReadiness(payload) {
  const reasons = [];
  if (payload?.mode !== "read_only_with_diagnostic_queries"
      || payload?.writeCapable !== false
      || payload?.motionWriteCapable !== false) {
    reasons.push("motion-locked observation snapshot required");
  }
  for (const side of ["left", "right"]) {
    const sample = payload?.sides?.[side];
    if (!sample?.fresh) {
      reasons.push(`${side} leg stream is stale`);
      continue;
    }
    const healthKnown = sample.health?.schema === "DBH1";
    if (!healthKnown) continue;
    const sensorMask = Number(sample.health.sensorFreshMask) || 0;
    const missingSensors = SENSOR_JOINTS.filter((_, index) => (sensorMask & (1 << index)) === 0);
    if (missingSensors.length) {
      reasons.push(`${side} AS5600 stale: ${missingSensors.join(", ")}`);
    }
    const yaw = sample.motorJoints?.[`${side}_hip_yaw`];
    const yawAvailable = (
      yaw?.controlAvailable === true
      && yaw?.alignmentFault !== true
      && Number.isFinite(yaw?.controlPositionDeg)
    ) || (yaw?.available === true && Number.isFinite(yaw?.positionDeg));
    if (!yawAvailable) reasons.push(`${side} hip yaw CAN angle unavailable`);
  }
  return Object.freeze({
    ready: reasons.length === 0,
    reasons: Object.freeze(reasons),
    requiredSensorMask: ALL_SENSOR_MASK,
  });
}

export function captureSoftwareZero(payload, torsoForwardDeg = 7, capturedAt = new Date().toISOString()) {
  if (payload?.mode !== "read_only_with_diagnostic_queries"
      || payload?.writeCapable !== false
      || payload?.motionWriteCapable !== false) {
    throw new Error("software zero requires a motion-locked observation snapshot");
  }
  const readiness = softwareZeroReadiness(payload);
  if (!readiness.ready) {
    throw new Error(`software zero blocked: ${readiness.reasons.join("; ")}`);
  }
  const sides = {};
  for (const side of ["left", "right"]) {
    const sample = payload?.sides?.[side];
    if (!sample?.fresh) throw new Error(`software zero requires a fresh ${side} leg sample`);
    const joints = {};
    for (const firmwareJoint of SENSOR_JOINTS) {
      const observation = sample.joints?.[`${side}_${firmwareJoint}`];
      const externalPositionDeg = Number(observation?.positionDeg);
      if (!Number.isFinite(externalPositionDeg)) {
        throw new Error(`software zero is missing ${side}_${firmwareJoint}`);
      }
      joints[firmwareJoint] = Object.freeze({ externalPositionDeg });
    }
    const motorJoints = Object.fromEntries(MOTOR_JOINTS.map((joint) => {
      const motor = sample.motorJoints?.[`${side}_${joint}`];
      const position = motor?.positionDeg;
      const controlPosition = motor?.controlPositionDeg;
      return [joint, Object.freeze({
        motorPositionDeg: typeof position === "number" && Number.isFinite(position) ? position : null,
        motorControlPositionDeg: typeof controlPosition === "number" && Number.isFinite(controlPosition)
          ? controlPosition : null,
      })];
    }));
    sides[side] = Object.freeze({
      sequence: Number(sample.sequence) || 0,
      configuredPath: String(sample.configuredPath || ""),
      resolvedPath: String(sample.resolvedPath || ""),
      joints: Object.freeze(joints),
      motorJoints: Object.freeze(motorJoints),
    });
  }
  const forward = Number(torsoForwardDeg);
  if (!Number.isFinite(forward) || forward < -45 || forward > 45) {
    throw new Error("torso forward angle must be within -45..45 degrees");
  }
  return Object.freeze({
    schema: SOFTWARE_ZERO_SCHEMA,
    units: "degrees",
    capturedAt: String(capturedAt),
    torsoForwardDeg: forward,
    sides: Object.freeze(sides),
  });
}

export function validateSoftwareZero(record) {
  if (!record || record.schema !== SOFTWARE_ZERO_SCHEMA || record.units !== "degrees") return null;
  try {
    return captureSoftwareZero({
      mode: "read_only_with_diagnostic_queries",
      writeCapable: false,
      motionWriteCapable: false,
      sides: Object.fromEntries(["left", "right"].map((side) => [side, {
        fresh: true,
        sequence: record.sides?.[side]?.sequence,
        configuredPath: record.sides?.[side]?.configuredPath,
        resolvedPath: record.sides?.[side]?.resolvedPath,
        joints: Object.fromEntries(SENSOR_JOINTS.map((joint) => [`${side}_${joint}`, {
          positionDeg: record.sides?.[side]?.joints?.[joint]?.externalPositionDeg,
        }])),
        motorJoints: Object.fromEntries(MOTOR_JOINTS.map((joint) => [`${side}_${joint}`, {
          positionDeg: record.sides?.[side]?.motorJoints?.[joint]?.motorPositionDeg,
          controlPositionDeg: record.sides?.[side]?.motorJoints?.[joint]?.motorControlPositionDeg,
        }])),
      }])),
    }, record.torsoForwardDeg, record.capturedAt);
  } catch (_error) {
    return null;
  }
}

export function projectHardwareDegrees(
  side,
  firmwareJoint,
  rawDegrees,
  softwareZero = null,
  positionSource = "external_absolute",
) {
  const baseCalibration = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side]?.[firmwareJoint]
    || (firmwareJoint === "hip_yaw" ? HIP_YAW_CALIBRATION : null);
  const isMotorNative = positionSource === "motor_native";
  const isMotorControl = positionSource === "motor_control_aligned";
  const capturedRawDatum = Number(isMotorNative
    ? softwareZero?.sides?.[side]?.motorJoints?.[firmwareJoint]?.motorPositionDeg
    : isMotorControl
      ? softwareZero?.sides?.[side]?.motorJoints?.[firmwareJoint]?.motorControlPositionDeg
      : softwareZero?.sides?.[side]?.joints?.[firmwareJoint]?.externalPositionDeg);
  const alignedDefaultDatum = firmwareJoint === "hip_yaw" ? 0 : baseCalibration?.rawDatumDeg;
  const rawDatum = Number.isFinite(capturedRawDatum)
    ? capturedRawDatum
    : isMotorControl ? alignedDefaultDatum : null;
  const calibration = baseCalibration && Number.isFinite(rawDatum)
    ? Object.freeze({
      ...baseCalibration,
      rawDatumDeg: rawDatum,
      datumSource: Number.isFinite(capturedRawDatum)
        ? "operator_captured_browser_zero" : "firmware_as5600_boot_alignment",
      capturedAt: Number.isFinite(capturedRawDatum) ? softwareZero.capturedAt : null,
      captureQuality: Number.isFinite(capturedRawDatum)
        ? "operator_captured_current_pose" : "firmware_aligned_motor_feedback",
      positionSource,
    })
    : isMotorNative || firmwareJoint === "hip_yaw"
      ? null
      : baseCalibration;
  if (!calibration || !Number.isFinite(rawDegrees)) {
    return Object.freeze({
      calibrated: false,
      rawDegrees,
      mechanismDegrees: null,
      renderDegrees: null,
      withinUsdLimits: false,
      calibration: calibration || null,
    });
  }
  const zeroedDegrees = shortestDegreeDelta(rawDegrees, calibration.rawDatumDeg);
  const mechanismDegrees = calibration.referenceDeg + zeroedDegrees;
  return Object.freeze({
    calibrated: true,
    rawDegrees,
    zeroedDegrees,
    mechanismDegrees,
    // DropbearSim retains 180 degrees as its internal zero. Robot3D then
    // converts this value back to the signed USD coordinate.
    renderDegrees: 180 + mechanismDegrees,
    withinUsdLimits: mechanismDegrees >= calibration.lowerDeg
      && mechanismDegrees <= calibration.upperDeg,
    calibration,
  });
}
