import { projectHardwareDegrees } from "./hardware_calibration.js";

export const ANGLE_RECORDING_SCHEMA = "dropbear-browser-angle-recording-v3";

const SENSOR_JOINTS = Object.freeze([
  "outer_calf",
  "inner_calf",
  "hip_pitch",
  "knee",
  "hip_roll",
]);

const JOINTS = Object.freeze([
  ...SENSOR_JOINTS,
  "hip_yaw",
]);

export const ANGLE_RECORDING_COLUMNS = Object.freeze([
  "schema",
  "host_time_iso",
  "host_monotonic_ms",
  "side",
  "usb_path",
  "sequence",
  "controller_millis",
  "sample_age_ms",
  "joint",
  "can_id",
  "external_raw_deg",
  "external_available",
  "external_status",
  "external_zeroed_deg",
  "model_joint_deg",
  "motor_native_deg",
  "motor_native_zeroed_deg",
  "motor_native_available",
  "motor_native_status",
  "motor_control_deg",
  "motor_control_model_deg",
  "motor_control_available",
  "motor_alignment_fault",
]);

export function observationRecordingRows(
  payload,
  softwareZero = null,
  hostMonotonicMs = performance.now(),
  hostTimeIso = new Date().toISOString(),
) {
  if (payload?.mode !== "read_only_with_diagnostic_queries"
      || payload?.writeCapable !== false
      || payload?.motionWriteCapable !== false) {
    throw new Error("angle recording requires a motion-locked observation snapshot");
  }
  const rows = [];
  for (const side of ["left", "right"]) {
    const sample = payload.sides?.[side];
    if (!sample?.fresh) continue;
    const healthKnown = sample.health?.schema === "DBH1";
    const sensorMask = Number(sample.health?.sensorFreshMask) || 0;
    for (const joint of JOINTS) {
      const name = `${side}_${joint}`;
      const external = sample.joints?.[name];
      const motor = sample.motorJoints?.[name];
      const raw = Number(external?.positionDeg);
      const sensorIndex = SENSOR_JOINTS.indexOf(joint);
      const externalAvailable = sensorIndex >= 0
        && Number.isFinite(raw)
        && (!healthKnown || (sensorMask & (1 << sensorIndex)) !== 0);
      const projection = externalAvailable
        ? projectHardwareDegrees(side, joint, raw, softwareZero)
        : null;
      const motorPosition = typeof motor?.positionDeg === "number" && Number.isFinite(motor.positionDeg)
        ? motor.positionDeg
        : null;
      const motorDatum = softwareZero?.sides?.[side]?.motorJoints?.[joint]?.motorPositionDeg;
      const motorZeroed = motorPosition !== null
        && typeof motorDatum === "number"
        && Number.isFinite(motorDatum)
        ? ((motorPosition - motorDatum + 540) % 360) - 180
        : null;
      const motorControlPosition = typeof motor?.controlPositionDeg === "number"
        && Number.isFinite(motor.controlPositionDeg)
        ? motor.controlPositionDeg : null;
      const motorControlProjection = motorControlPosition !== null
        ? projectHardwareDegrees(side, joint, motorControlPosition, softwareZero, "motor_control_aligned")
        : null;
      rows.push(Object.freeze({
        schema: ANGLE_RECORDING_SCHEMA,
        host_time_iso: hostTimeIso,
        host_monotonic_ms: Number(hostMonotonicMs),
        side,
        usb_path: String(sample.configuredPath || sample.resolvedPath || ""),
        sequence: Number(sample.sequence) || 0,
        controller_millis: Number.isInteger(sample.controllerMillis) ? sample.controllerMillis : null,
        sample_age_ms: Number.isFinite(sample.ageMs) ? Number(sample.ageMs) : null,
        joint,
        can_id: String(external?.canId || motor?.canId || ""),
        external_raw_deg: Number.isFinite(raw) ? raw : null,
        external_available: externalAvailable,
        external_status: sensorIndex < 0
          ? "no_dedicated_as5600"
          : externalAvailable ? "fresh" : healthKnown ? "firmware_marked_stale" : "missing",
        external_zeroed_deg: projection?.calibrated ? projection.zeroedDegrees : null,
        model_joint_deg: projection?.calibrated ? projection.mechanismDegrees : null,
        motor_native_deg: motorPosition,
        motor_native_zeroed_deg: motorZeroed,
        motor_native_available: motorPosition !== null,
        motor_native_status: motorPosition !== null
          ? "measured"
          : String(motor?.status || "not_emitted_by_deployed_firmware"),
        motor_control_deg: motorControlPosition,
        motor_control_model_deg: motorControlProjection?.calibrated
          ? motorControlProjection.mechanismDegrees : null,
        motor_control_available: motor?.controlAvailable === true && motorControlPosition !== null,
        motor_alignment_fault: motor?.alignmentFault === true,
      }));
    }
  }
  return rows;
}

function csvCell(value) {
  if (value == null) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function angleRecordingCsv(rows) {
  const body = rows.map((row) => ANGLE_RECORDING_COLUMNS.map((column) => csvCell(row[column])).join(","));
  return `${ANGLE_RECORDING_COLUMNS.join(",")}\n${body.join("\n")}${body.length ? "\n" : ""}`;
}
