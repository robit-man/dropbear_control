import { HARDWARE_DEFAULT_STANCE_CALIBRATION } from "./hardware_calibration.js";
import { DROPBEAR_USD_BINDINGS } from "./dropbear_usd.js";

const SENSOR_KEYS = Object.freeze([
  ["outer_calf", "GPIO14", "OUTER CALF", 0],
  ["inner_calf", "GPIO27", "INNER CALF", 1],
  ["hip_pitch", "GPIO26", "HIP PITCH", 2],
  ["knee", "GPIO25", "KNEE", 3],
  ["hip_roll", "GPIO33", "HIP ROLL", 4],
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
    firmware: sample?.firmware || {},
    health: sample?.health || {},
    observationStreaming: sample?.observationStreaming === true,
    diagnosticTxBytes: Number(sample?.diagnosticTxBytes) || 0,
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

function motorFeedbackDiagnosis(status, nativeCount) {
  const health = status.health;
  if (health.schema !== "DBH1") {
    return "No current DBH1 counters are available; request health from the ESP32.";
  }
  const queries = Number(health.motorQueries) || 0;
  const responses = Number(health.motorResponses) || 0;
  const failures = Number(health.motorQueryFailures) || 0;
  const consecutive = Number(health.canConsecutiveFailures) || 0;
  if (queries === 0 && failures > 0) {
    return `0 successful angle requests · ${failures.toLocaleString()} TX failures · ${consecutive.toLocaleString()} consecutive. MCP2515 initialized, but no powered CAN peer is acknowledging frames; check actuator-bus power, transceiver wiring, and termination.`;
  }
  if (nativeCount < 6) {
    const responding = Object.values(status.motorJoints)
      .filter((motor) => motor?.available === true)
      .map((motor) => motor.canId)
      .join(", ") || "none in the current 500 ms window";
    return `${queries.toLocaleString()} requests accepted by MCP2515 · ${responses.toLocaleString()} verified replies · responding IDs ${responding}. Missing IDs are held out of the USD motor-native path.`;
  }
  return `${queries.toLocaleString()} requests · ${responses.toLocaleString()} replies · all six motor IDs fresh.`;
}

function renderSide(side, sample) {
  const status = classifyControllerSide(side, sample);
  const column = document.createElement("section");
  column.className = `controller-side-flow ${side}`;
  const heading = document.createElement("header");
  const title = document.createElement("div");
  const state = document.createElement("span");
  title.innerHTML = `<b>${side.toUpperCase()} ESP32</b><small>115200 8N1 · RX + DIAGNOSTIC QUERY</small>`;
  state.className = `controller-side-state ${status.transport}`;
  state.textContent = status.fresh ? "LIVE" : status.transport === "fail" ? "ERROR" : "SILENT";
  heading.append(title, state);
  column.append(heading);

  column.append(node(
    "USB SERIAL",
    `${status.resolvedPath} · reader ${status.readerState} · read errors ${status.readErrors}`,
    status.transport,
  ));
  column.append(arrow("continuous O_RDONLY"));
  const capabilities = Array.isArray(status.firmware.capabilities)
    ? status.firmware.capabilities : [];
  column.append(node(
    "FIRMWARE CONTRACT",
    `${status.firmware.version || "version not reported"} · command ${status.firmware.commandProtocol || "unknown"} · telemetry ${status.firmware.telemetryProtocol || status.telemetryFormat} · ${capabilities.length} capabilities`,
    capabilities.includes("observe-stream-v1") ? "success" : "degraded",
  ));
  column.append(node(
    "CSV FRAME READER",
    status.ageMs == null
      ? `${status.decodedLines.toLocaleString()} decoded · no sample received`
      : `${status.decodedLines.toLocaleString()} decoded · seq ${status.sequence.toLocaleString()} · ${status.ageMs.toFixed(0)} ms old`,
    status.stream,
  ));
  column.append(node(
    "OBSERVATION STREAM",
    status.decodedLines > 0
      ? `${status.observationStreaming ? "observe on acknowledged" : "telemetry present"} · independent of actuator play · diagnostic tx ${status.diagnosticTxBytes} bytes`
      : status.readerState === "observing"
        ? "USB UART is open but no valid telemetry has arrived. Request observe on or verify the loaded firmware supports observe-stream-v1."
        : "Reader state must recover before firmware progress can be inferred.",
    status.decodedLines > 0 ? "success" : status.transport,
  ));
  const db2 = status.telemetryFormat === "DB2";
  const db3 = status.telemetryFormat === "DB3";
  column.append(arrow(db3 ? "5 external + 6 raw CAN + 6 aligned CAN" : db2 ? "5 external + 6 raw CAN" : "5 external degrees"));
  column.append(node(
    "STRICT PARSER",
    `${status.rejectedLines.toLocaleString()} rejected · ${status.overflowEvents.toLocaleString()} overflows · ${db3 ? "DB3 aligned-CAN frames" : db2 ? "DB2 dual-angle frames" : "legacy five-value frames"}`,
    status.parser,
  ));
  const health = status.health;
  const healthKnown = health.schema === "DBH1";
  const healthState = !healthKnown ? "unknown"
    : health.overall === "ok" ? "success"
      : health.overall === "fault" ? "fail" : "degraded";
  column.append(node(
    "ESP / CAN HEALTH",
    healthKnown
      ? `${String(health.overall).toUpperCase()} · runtime ${health.runtimeReady ? "ready" : "blocked"} · CAN ${health.canReady ? "ready" : "down"} · sensors ${Number(health.sensorFreshMask).toString(2).padStart(5, "0")} · motors ${Number(health.motorFreshMask).toString(2).padStart(6, "0")} · aligned ${Number(health.motorControlMask).toString(2).padStart(6, "0")} · faults ${Number(health.alignmentFaultMask).toString(2).padStart(6, "0")}`
      : "No DBH1 response has arrived. Use Live State or send health from Devices.",
    healthState,
  ));

  const sensors = document.createElement("div");
  sensors.className = "controller-sensor-grid";
  const sensorMask = Number(health.sensorFreshMask) || 0;
  for (const [key, gpio, label, bit] of SENSOR_KEYS) {
    const observation = status.joints?.[`${side}_${key}`];
    const calibration = HARDWARE_DEFAULT_STANCE_CALIBRATION.sides[side]?.[key];
    const unstable = String(calibration?.captureQuality || "").startsWith("unstable");
    const sensorFresh = !healthKnown || (sensorMask & (1 << bit)) !== 0;
    const value = finite(observation?.positionDeg)
      ? `${observation.positionDeg.toFixed(1)}° ${healthKnown ? sensorFresh ? "live" : "cached; firmware marks PWM stale" : "health unverified"}${unstable ? " · known bimodal channel; model held" : ""}`
      : "no fresh value";
    sensors.append(node(
      `${gpio} · ${label}`,
      value,
      !sensorFresh ? "fail" : !healthKnown || unstable ? "degraded" : "success",
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
  const alignedCount = Object.values(status.motorJoints).filter(
    (motor) => motor?.controlAvailable === true
      && motor?.alignmentFault !== true
      && finite(motor.controlPositionDeg),
  ).length;
  const freshSensorCount = healthKnown
    ? SENSOR_KEYS.filter(([, , , bit]) => (sensorMask & (1 << bit)) !== 0).length
    : null;
  column.append(arrow("read-only RMD 0x92"));
  const motors = document.createElement("div");
  motors.className = "controller-sensor-grid";
  for (const binding of DROPBEAR_USD_BINDINGS.filter((entry) => entry.side === side)) {
    const motor = status.motorJoints?.[`${side}_${binding.firmwareJoint}`];
    const raw = motor?.available === true && finite(motor.positionDeg);
    const aligned = motor?.controlAvailable === true
      && motor?.alignmentFault !== true
      && finite(motor.controlPositionDeg);
    motors.append(node(
      `${binding.canLabel} · ${binding.firmwareJoint.replaceAll("_", " ").toUpperCase()}`,
      `${binding.variant} · ${binding.motorFirmware} · ${raw ? `${motor.positionDeg.toFixed(2)}° raw` : "no verified reply"}${aligned ? ` · ${motor.controlPositionDeg.toFixed(2)}° aligned` : " · alignment held"}`,
      aligned ? "success" : raw ? "degraded" : "fail",
      "sensor",
    ));
  }
  column.append(motors);
  column.append(node(
    "CAN FEEDBACK DIAGNOSIS",
    motorFeedbackDiagnosis(status, nativeCount),
    nativeCount === 6 ? "success" : nativeCount ? "degraded" : "fail",
  ));
  column.append(node(
    "CORRECTED USD TWIN",
    status.fresh
      ? nativeCount
        ? `${freshSensorCount ?? "?"}/5 AS5600 PWM channels, ${nativeCount}/6 raw CAN angles, and ${alignedCount}/6 aligned CAN angles are fresh. Aligned CAN drives the model; AS5600 remains the restart reference and cross-check.`
        : `${freshSensorCount ?? "?"}/5 AS5600 PWM channels are marked fresh by firmware. Only fresh, calibrated channels drive the model while motor-native feedback is absent; hip yaw requires CAN.`
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
  const motorAlignedCount = ["left", "right"].reduce((count, side) => count
    + Object.values(payload?.sides?.[side]?.motorJoints || {}).filter(
      (motor) => motor?.controlAvailable === true
        && motor?.alignmentFault !== true
        && typeof motor.controlPositionDeg === "number"
        && Number.isFinite(motor.controlPositionDeg),
    ).length, 0);
  common.append(
    node(
      "MCP2515 / CAN RX",
      motorNativeCount
        ? `${motorNativeCount}/12 verified RMD 0x92 channels · ${motorAlignedCount}/12 aligned control channels.`
        : "No verified RMD 0x92 actuator replies are present in the admitted telemetry.",
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
    node("SERIAL / CAN CONTROL TX", "Only version, health, and observation requests can transmit here. Motion transport remains absent; the three-stage frontend gate cannot change that.", "locked"),
  );
  container.append(flows, common);
}
