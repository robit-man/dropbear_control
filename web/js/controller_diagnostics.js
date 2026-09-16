import { HARDWARE_DEFAULT_STANCE_CALIBRATION } from "./hardware_calibration.js";

const SENSOR_KEYS = Object.freeze([
  ["outer_calf", "GPIO14", "OUTER CALF"],
  ["inner_calf", "GPIO27", "INNER CALF"],
  ["hip_pitch", "GPIO26", "HIP PITCH"],
  ["knee", "GPIO25", "KNEE"],
  ["hip_roll", "GPIO33", "HIP ROLL"],
]);

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function classifyControllerSide(side, sample) {
  const calibration = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side];
  const decodedLines = Number(sample?.decodedLines) || 0;
  const rejectedLines = Number(sample?.rejectedLines) || 0;
  const readErrors = Number(sample?.readErrors) || 0;
  const fresh = sample?.fresh === true;
  const unstableCalibration = calibration && Object.values(calibration)
    .some((joint) => String(joint?.captureQuality || "").startsWith("unstable"));
  const readerState = String(sample?.state || "unavailable");
  let transport = "unknown";
  if (readerState === "error" || readErrors > 0) transport = "fail";
  else if (fresh) transport = "success";
  else if (readerState === "observing" && decodedLines === 0) transport = "degraded";
  else if (["disabled", "stopped"].includes(readerState)) transport = "locked";

  return Object.freeze({
    side,
    transport,
    stream: fresh ? "success" : decodedLines > 0 ? "degraded" : "degraded",
    parser: rejectedLines > Math.max(5, decodedLines * 0.001)
      ? "degraded"
      : decodedLines > 0 ? "success" : "unknown",
    calibration: calibration ? unstableCalibration ? "degraded" : "success" : "unknown",
    fresh,
    readerState,
    configuredPath: String(sample?.configuredPath || "not configured"),
    resolvedPath: String(sample?.resolvedPath || "unresolved"),
    decodedLines,
    rejectedLines,
    overflowEvents: Number(sample?.overflowEvents) || 0,
    readErrors,
    ageMs: finite(sample?.ageMs) ? sample.ageMs : null,
    sequence: Number(sample?.sequence) || 0,
    joints: sample?.joints || {},
    motorJoints: sample?.motorJoints || {},
    telemetryFormat: String(sample?.telemetryFormat || "legacy5"),
  });
}

function node(label, detail, state = "unknown", extraClass = "") {
  const element = document.createElement("div");
  element.className = `controller-node ${state} ${extraClass}`.trim();
  const stateLabel = {
    success: "PASS",
    degraded: "DEGRADED",
    fail: "FAIL",
    locked: "LOCKED",
    unknown: "UNKNOWN",
    future: "FUTURE",
  }[state] || String(state).toUpperCase();
  const head = document.createElement("div");
  const title = document.createElement("b");
  const badge = document.createElement("span");
  const body = document.createElement("p");
  title.textContent = label;
  badge.textContent = stateLabel;
  body.textContent = detail;
  head.append(title, badge);
  element.append(head, body);
  return element;
}

function arrow(label = "") {
  const element = document.createElement("div");
  element.className = "controller-arrow";
  element.textContent = label ? `→ ${label} →` : "→";
  return element;
}

function renderSide(side, sample) {
  const status = classifyControllerSide(side, sample);
  const column = document.createElement("section");
  column.className = `controller-side-flow ${side}`;
  const heading = document.createElement("header");
  const title = document.createElement("div");
  const state = document.createElement("span");
  title.innerHTML = `<b>${side.toUpperCase()} ESP32</b><small>115200 8N1 · PASSIVE RX</small>`;
  state.className = `controller-side-state ${status.transport}`;
  state.textContent = status.fresh ? "LIVE" : status.transport === "fail" ? "ERROR" : "SILENT";
  heading.append(title, state);
  column.append(heading);

  column.append(node(
    "USB SERIAL",
    `${status.resolvedPath} · reader ${status.readerState} · read errors ${status.readErrors}`,
    status.transport,
  ));
  column.append(arrow("O_RDONLY"));
  column.append(node(
    "CSV FRAME READER",
    status.ageMs == null
      ? `${status.decodedLines.toLocaleString()} decoded · no sample received`
      : `${status.decodedLines.toLocaleString()} decoded · seq ${status.sequence.toLocaleString()} · ${status.ageMs.toFixed(0)} ms old`,
    status.stream,
  ));
  column.append(node(
    "FIRMWARE STARTUP GATE",
    status.decodedLines > 0
      ? "Sensor task reached its playMode && !isCenter publish loop."
      : status.readerState === "observing"
        ? "USB UART is open without errors but the ESP emits no bytes. Source-level candidates are the leg-side prompt, saved center mode, or the blocking CAN-init failure loop."
        : "Reader state must recover before firmware progress can be inferred.",
    status.decodedLines > 0 ? "success" : status.transport,
  ));
  const db2 = status.telemetryFormat === "DB2";
  column.append(arrow(db2 ? "5 external + 6 motor degrees" : "5 external degrees"));
  column.append(node(
    "STRICT PARSER",
    `${status.rejectedLines.toLocaleString()} rejected · ${status.overflowEvents.toLocaleString()} overflows · ${db2 ? "DB2 dual-angle frames" : "legacy five-value frames"}`,
    status.parser,
  ));

  const sensors = document.createElement("div");
  sensors.className = "controller-sensor-grid";
  for (const [key, gpio, label] of SENSOR_KEYS) {
    const observation = status.joints?.[`${side}_${key}`];
    const calibration = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side]?.[key];
    const unstable = String(calibration?.captureQuality || "").startsWith("unstable");
    const value = finite(observation?.positionDeg)
      ? `${observation.positionDeg.toFixed(1)}° raw${unstable ? " · known bimodal channel; model held" : ""}`
      : "no fresh value";
    sensors.append(node(
      `${gpio} · ${label}`,
      value,
      unstable && observation && status.fresh ? "degraded" : observation && status.fresh ? "success" : "unknown",
      "sensor",
    ));
  }
  column.append(sensors);
  column.append(arrow("datum + limits"));
  column.append(node(
    "DEFAULT-STANCE MAP",
    status.calibration === "success"
      ? `${side[0].toUpperCase()}${side.slice(1)} median datum maps measured degrees 1:1 onto actuator-shaft joints; linkage closure computes downstream motion.`
      : status.calibration === "degraded"
        ? "Side datum is present, but a known bimodal sensor remains raw-only and cannot move the rendered linkage."
        : "No side-specific datum accepted. Raw readings cannot move the rendered articulation.",
    status.calibration,
  ));
  column.append(arrow("read-only state"));
  const nativeCount = Object.values(status.motorJoints).filter(
    (motor) => motor?.available === true && finite(motor.positionDeg),
  ).length;
  column.append(node(
    "CORRECTED USD TWIN",
    status.fresh
      ? nativeCount
        ? `All five AS5600 fields and ${nativeCount}/6 motor angles are observed. After software zero, verified motor angles drive the model and AS5600 remains an independent check.`
        : "All five AS5600 fields are observed. Admitted calibrated fields drive browser kinematics; hip yaw alone is absent from the legacy packet."
      : "Rendered state is held until a fresh five-field packet is available.",
    status.fresh ? status.calibration : "degraded",
  ));
  return column;
}

export function renderControllerDiagnostics(container, payload) {
  if (!container) return;
  container.replaceChildren();
  const flows = document.createElement("div");
  flows.className = "controller-side-grid";
  flows.append(
    renderSide("left", payload?.sides?.left),
    renderSide("right", payload?.sides?.right),
  );
  const common = document.createElement("section");
  common.className = "controller-common-flow";
  const motorNativeCount = ["left", "right"].reduce((count, side) => count
    + Object.values(payload?.sides?.[side]?.motorJoints || {}).filter(
      (motor) => motor?.available === true
        && typeof motor.positionDeg === "number"
        && Number.isFinite(motor.positionDeg),
    ).length, 0);
  common.append(
    node(
      "MCP2515 / CAN RX",
      motorNativeCount
        ? `${motorNativeCount}/12 verified motor-angle channels present in the admitted ESP telemetry.`
        : "Deployed firmware CSV does not report CAN controller health or actuator replies.",
      motorNativeCount ? "success" : "unknown",
    ),
    node(
      "MOTOR-NATIVE ANGLES",
      motorNativeCount
        ? `${motorNativeCount}/12 independently measured motor positions available; recorder retains them beside external angles.`
        : "All twelve CAN-ID channels are represented in recordings, but remain unavailable until ESP firmware decodes and emits verified motor replies.",
      motorNativeCount === 12 ? "success" : motorNativeCount ? "degraded" : "unknown",
    ),
    node("IMU TASK", "IMU state is not present in the deployed five-value serial frame.", "unknown"),
    node("USB ROLE / CHIRALITY", "Physical motion check: path 1.2 is left and path 1.1 is right. Both legacy builds ignored a chirality query while streaming. Silent path 1.4 remains the neck candidate.", "success"),
    node("FOOT FORCE DISTRIBUTION", "dropbear-foot integration reserved; no sensor transport is wired yet.", "future"),
    node("SERIAL / CAN CONTROL TX", "No write-capable descriptor exists. Frontend acknowledgement cannot unlock physical output.", "locked"),
  );
  container.append(flows, common);
}
