import {
  CONTROLLER_PINS,
  DROPBEAR_SOURCE,
  DropbearSim,
  JOINT_DEFINITIONS,
  TASKS,
} from "./dropbear.js";
import { CAD_EVIDENCE, CadViewer } from "./cad_viewer.js";
import { renderControllerDiagnostics } from "./controller_diagnostics.js";
import {
  DROPBEAR_ARM_MOTOR_BINDINGS,
  DROPBEAR_USD_SOURCE,
  dropbearArmMotorBinding,
  dropbearUsdBinding,
} from "./dropbear_usd.js";
import { RLPolicyPlayer } from "./rl_policy.js";
import { Robot3D } from "./robot_3d.js";
import {
  SoftwarePanelViewer,
  SoftwareRobotViewer,
  supportsWebGL2,
} from "./software_viewers.js";
import {
  applyHardwareObservation,
  clearHardwareObservationHistory,
  validateHardwareObservation,
} from "./hardware_observation.js";
import {
  captureSoftwareZero,
  softwareZeroReadiness,
  validateSoftwareZero,
} from "./hardware_calibration.js";
import {
  angleRecordingCsv,
  observationRecordingRows,
} from "./hardware_recording.js";
import {
  GR00T_WBC_PLAYBACK_SOURCES,
  cancelGr00tWbcPlayback,
  playGr00tWbcSource,
  setupGr00tLab,
  waitForGr00tWbcPlaybackIdle,
} from "./gr00t_lab.js";

const $ = (id) => document.getElementById(id);
const RAD_TO_DEG = 180 / Math.PI;
// v5 permits a partial live-state zero while retaining each measured channel.
// external AS5600 angles.
const SOFTWARE_ZERO_STORAGE_KEY = "dropbear.control.softwareZero.v5";
const MAX_ANGLE_RECORDING_ROWS = 120_000;

function loadSoftwareZero() {
  try {
    return validateSoftwareZero(JSON.parse(localStorage.getItem(SOFTWARE_ZERO_STORAGE_KEY) || "null"));
  } catch (_error) {
    return null;
  }
}

const sim = new DropbearSim();
const PRESET_SOURCES = Object.freeze([
  { value: "neutral", label: "Neutral hold" },
  { value: "walk", label: "Alternating step" },
  { value: "balance", label: "Balance transfer" },
  { value: "sensor-sweep", label: "Sensor sweep" },
  { value: "manual", label: "Manual torque" },
]);
const RL_SOURCES = Object.freeze([
  {
    value: "locomotion-export-required",
    label: "dropbear-locomotion replay · trajectory export required",
    disabled: true,
  },
]);
const GR00T_PROMPT_PREVIEW_PRESETS = Object.freeze({
  stand: "neutral",
  walk: "walk",
});
const GR00T_PROMPT_PREVIEW_TURN_EPSILON_RPS = 0.005;
const DROPBEAR_RETARGET_ACTION_ORDER = Object.freeze([
  "left_outer_calf",
  "left_inner_calf",
  "right_inner_calf",
  "right_outer_calf",
  "left_knee",
  "left_hip_pitch",
  "right_hip_pitch",
  "right_knee",
  "left_hip_yaw",
  "left_hip_roll",
  "right_hip_roll",
  "right_hip_yaw",
  "left_shoulder_pitch",
  "left_shoulder_yaw",
  "left_shoulder_roll",
  "left_elbow_pitch",
  "left_wrist_roll",
  "right_shoulder_pitch",
  "right_shoulder_yaw",
  "right_shoulder_roll",
  "right_elbow_pitch",
  "right_wrist_roll",
]);
let playbackSelectionGeneration = 0;
let playbackSelectionAbortController = null;
const beginPlaybackSelection = () => {
  cancelGr00tWbcPlayback();
  playbackSelectionAbortController?.abort();
  playbackSelectionAbortController = null;
  playbackSelectionGeneration += 1;
  return playbackSelectionGeneration;
};
const isCurrentPlaybackSelection = (generation) => (
  generation === playbackSelectionGeneration
);
const openPlaybackRequest = (generation) => {
  if (!isCurrentPlaybackSelection(generation)) return null;
  const controller = new AbortController();
  playbackSelectionAbortController = controller;
  return controller;
};
const releasePlaybackRequest = (controller) => {
  if (playbackSelectionAbortController === controller) {
    playbackSelectionAbortController = null;
  }
};
const RL_TRAINING_PROFILES = Object.freeze({
  "gentle-forward": Object.freeze({
    label: "Gentle forward",
    updates: 250,
    steps: 128,
    envs: 8,
    epochs: 4,
    batchSize: 512,
    targetSpeed: 0.26,
    targetTurnRate: 0,
    episodeSeconds: 8,
    physicsBackend: "mujoco-usd-proxy-v1",
    device: "cpu",
    verticalConstraint: false,
    armSwing: true,
    rewardWeights: Object.freeze({
      torso: 1.75,
      com: 1.20,
      gaitContact: 0.90,
      gaitSymmetry: 1.10,
      speed: 0.55,
      legSwing: 0.28,
      height: 8.0,
      lateralTilt: 5.0,
      dorsalTilt: 4.5,
      kneeContraction: 0.18,
      armSwing: 0.35,
      energy: 0.018,
      smoothness: 0.065,
      closure: 300.0,
      fall: 7.0,
    }),
  }),
  "circle-walk": Object.freeze({
    label: "Circle walk",
    updates: 400,
    steps: 160,
    envs: 8,
    epochs: 5,
    batchSize: 640,
    targetSpeed: 0.22,
    targetTurnRate: 0.28,
    episodeSeconds: 10,
    physicsBackend: "mujoco-usd-proxy-v1",
    device: "cpu",
    verticalConstraint: false,
    armSwing: true,
    rewardWeights: Object.freeze({
      torso: 1.90,
      com: 1.35,
      gaitContact: 1.00,
      gaitSymmetry: 0.42,
      speed: 0.95,
      legSwing: 0.38,
      height: 8.5,
      lateralTilt: 6.0,
      dorsalTilt: 5.0,
      kneeContraction: 0.12,
      armSwing: 0.50,
      energy: 0.018,
      smoothness: 0.055,
      closure: 325.0,
      fall: 8.0,
    }),
  }),
});
const armMotorStates = DROPBEAR_ARM_MOTOR_BINDINGS.map((binding) => ({
  id: binding.id,
  angleDeg: 0,
  velocityDegS: 0,
  torqueNm: 0,
}));

const ui = {
  view: "sim",
  selectedJointId: 0x141,
  controller: "left",
  consoleController: "left",
  lastRender: 0,
  lastFrame: performance.now(),
  scopeSampleAt: 0,
  scopeHistory: [],
  cadManual: false,
  motorCategory: "legs",
  axisCategory: "leg",
  selectedArmMotorId: null,
  lastRobotFrameAt: performance.now(),
  lastLiveDomAt: 0,
  policyMode: false,
  latestPolicyUrl: null,
  rlStatusSignature: "",
  watchTraining: false,
  previewLoadedKey: null,
  previewLoading: false,
  playbackFamily: "classic",
  playbackMode: "preset",
  playbackSelections: {
    preset: "neutral",
    rl: "reference",
    gr00t: "g1-published-stand",
  },
  gr00tAvailability: {
    decodedG1PoseReady: null,
    nvidiaTokenReady: null,
  },
  gr00tPlayBusy: false,
  autoReplayTraining: true,
  latestRLStatus: null,
  loadedPolicySource: null,
  rlSessions: [],
  selectedRLSessionId: null,
  rlSessionsSignature: "",
  physicsRuntime: null,
  hardwareObservation: {
    active: false,
    // The dashboard is an observation surface first. Live ESP32 state is the
    // default; append ?live=0 only when deliberately reviewing synthetic state.
    autoActivate: new URLSearchParams(window.location.search).get("live") !== "0",
    pending: false,
    requesting: false,
    healthPending: false,
    lastHealthRequestAt: 0,
    streamRequested: false,
    latest: null,
    lastAppliedSignature: "",
    error: "",
    softwareZero: loadSoftwareZero(),
    // Direct-CAN-only is a per-session commissioning choice. Never let an old
    // browser preference make an otherwise live robot reopen as UNOBSERVED.
    angleSource: "auto",
    recording: false,
    recordingRows: [],
    lastRecordedSignature: "",
    lastStateRenderSignature: "",
  },
  hardwareControl: {
    challenge: "",
    leaseToken: "",
    expiresInMs: 0,
    frontendArmed: false,
  },
  hardwareDevices: {
    latest: null,
    selectedDeviceId: "",
    selectedSourceId: "",
    build: null,
    busy: false,
    compileState: "idle",
    lastRawText: "",
  },
};

function selectedJoint() {
  return sim.getJoint(ui.selectedJointId) || sim.joints[0];
}

function signed(value, digits = 1) {
  const number = Number(value) || 0;
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}`;
}

function observationPositionLabel(source) {
  if (source === "motor_control_aligned") return "CAN ALIGNED";
  if (source === "motor_native") return "CAN RAW";
  return "AS5600";
}

function appendTerminal(text, kind = "") {
  const output = $("terminal-output");
  const line = document.createElement("div");
  line.className = `terminal-line ${kind}`.trim();
  line.textContent = text;
  output.appendChild(line);
  while (output.childElementCount > 180) output.removeChild(output.firstChild);
  output.scrollTop = output.scrollHeight;
}

function renderHardwareObservationState() {
  const status = ui.hardwareObservation.latest;
  const output = $("hardware-observation-state");
  const button = $("hardware-observation-toggle");
  const freshSides = ["left", "right"].filter((side) => status?.sides?.[side]?.fresh === true).length;
  const canAngles = ["left", "right"].reduce((count, side) => {
    const sample = status?.sides?.[side];
    if (sample?.health?.schema === "DBH1") {
      return count + ((Number(sample.health.motorFreshMask) || 0) & 0x3f)
        .toString(2).replaceAll("0", "").length;
    }
    return count + Object.values(sample?.motorJoints || {})
      .filter((motor) => motor?.available === true && Number.isFinite(motor?.positionDeg)).length;
  }, 0);
  let label = status?.enabled ? String(status.state || "waiting").toUpperCase() : "DISABLED";
  if (ui.hardwareObservation.requesting) label = "REQUESTING FROM ESP32S";
  if (ui.hardwareObservation.active) {
    label = freshSides === 2
      ? `LIVE · 2/2 · CAN ${canAngles}/12 RECENT`
      : freshSides === 1 ? `DEGRADED · 1/2 · CAN ${canAngles}/12 RECENT` : "STALE · 0/2";
  }
  const zero = ui.hardwareObservation.softwareZero;
  const zeroReadiness = softwareZeroReadiness(status);
  const recording = ui.hardwareObservation.recording;
  const rows = ui.hardwareObservation.recordingRows;
  const renderSignature = JSON.stringify([
    label,
    ui.hardwareObservation.requesting,
    ui.hardwareObservation.active,
    zero?.capturedAt || "",
    zeroReadiness.ready,
    zeroReadiness.reasons,
    zeroReadiness.warnings,
    ui.hardwareObservation.angleSource,
    recording,
    rows.length,
  ]);
  if (renderSignature === ui.hardwareObservation.lastStateRenderSignature) return;
  ui.hardwareObservation.lastStateRenderSignature = renderSignature;
  output.textContent = `READ ONLY · ${label}`;
  output.classList.toggle("warn", ui.hardwareObservation.active && freshSides < 2);
  button.classList.toggle("active", ui.hardwareObservation.active);
  button.setAttribute("aria-pressed", String(ui.hardwareObservation.active));
  button.disabled = ui.hardwareObservation.requesting;
  button.textContent = ui.hardwareObservation.requesting
    ? "REQUESTING LIVE STATE…"
    : ui.hardwareObservation.active ? "LEAVE LIVE STATE" : "USE LIVE STATE";
  $("hardware-angle-source").value = ui.hardwareObservation.angleSource;
  const zeroButton = $("hardware-zero-current");
  zeroButton.disabled = !ui.hardwareObservation.active || !zeroReadiness.ready;
  zeroButton.title = zeroReadiness.ready
    ? `Capture a browser-only zero without changing ESP32 calibration. Available now: ${zeroReadiness.motorAvailable}/12 CAN, ${zeroReadiness.externalAvailable}/10 AS5600.`
    : zeroReadiness.reasons.join("; ");
  $("hardware-zero-state").textContent = zero
    ? `ZERO · ${new Date(zero.capturedAt).toLocaleTimeString()} · TORSO ${zero.torsoForwardDeg.toFixed(1)}° FORWARD`
    : zeroReadiness.ready
      ? `ZERO · READY · CAN ${zeroReadiness.motorAvailable}/12 · AS5600 ${zeroReadiness.externalAvailable}/10`
      : `ZERO BLOCKED · ${zeroReadiness.reasons[0] || "LIVE FEEDBACK INCOMPLETE"}`;
  const recordButton = $("hardware-record-toggle");
  recordButton.disabled = !ui.hardwareObservation.active || freshSides === 0;
  recordButton.classList.toggle("active", recording);
  recordButton.textContent = recording ? "STOP ANGLE RECORDING" : "START ANGLE RECORDING";
  const motorRows = rows.filter((row) => row.motor_native_available).length;
  $("hardware-record-download").disabled = rows.length === 0;
  $("hardware-record-state").textContent = `REC · ${rows.length.toLocaleString()} ROWS · MOTOR NATIVE ${motorRows ? `${motorRows.toLocaleString()} MEASURED` : "UNAVAILABLE"}`;
}

async function refreshHardwareHealth() {
  if (ui.hardwareObservation.healthPending) return;
  ui.hardwareObservation.healthPending = true;
  ui.hardwareObservation.lastHealthRequestAt = performance.now();
  try {
    await requestJson("/api/hardware/observation/health", {
      method: "POST",
      body: JSON.stringify({}),
    });
  } finally {
    ui.hardwareObservation.healthPending = false;
  }
}

function captureCurrentSoftwareZero() {
  const torsoForwardDeg = Number($("hardware-zero-torso").value);
  const zero = captureSoftwareZero(ui.hardwareObservation.latest, torsoForwardDeg);
  ui.hardwareObservation.softwareZero = zero;
  localStorage.setItem(SOFTWARE_ZERO_STORAGE_KEY, JSON.stringify(zero));
  clearHardwareObservationHistory(sim);
  robot.setObservationRootPitchDegrees(zero.torsoForwardDeg);
  applyHardwareObservation(
    sim,
    ui.hardwareObservation.latest,
    performance.now(),
    zero,
    ui.hardwareObservation.angleSource,
  );
  appendTerminal(
    `[hardware] software zero captured from both fresh leg streams · CAN ${softwareZeroReadiness(ui.hardwareObservation.latest).motorAvailable}/12 · torso ${zero.torsoForwardDeg.toFixed(1)}° forward · ESP values unchanged`,
    "ok",
  );
  renderHardwareObservationState();
}

function recordCurrentHardwareObservation(payload) {
  if (!ui.hardwareObservation.recording) return;
  const signature = ["left", "right"]
    .map((side) => payload?.sides?.[side]?.fresh ? payload.sides[side].sequence : 0)
    .join(":");
  if (signature === ui.hardwareObservation.lastRecordedSignature) return;
  ui.hardwareObservation.lastRecordedSignature = signature;
  const rows = observationRecordingRows(payload, ui.hardwareObservation.softwareZero);
  ui.hardwareObservation.recordingRows.push(...rows);
  if (ui.hardwareObservation.recordingRows.length >= MAX_ANGLE_RECORDING_ROWS) {
    ui.hardwareObservation.recordingRows.length = MAX_ANGLE_RECORDING_ROWS;
    ui.hardwareObservation.recording = false;
    appendTerminal("[hardware] angle recording stopped at the 120,000-row browser limit", "warn");
  }
}

function downloadAngleRecording() {
  const rows = ui.hardwareObservation.recordingRows;
  if (!rows.length) return;
  const blob = new Blob([angleRecordingCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `dropbear-angle-recording-${new Date().toISOString().replaceAll(":", "-")}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function pollHardwareObservation() {
  if (ui.hardwareObservation.pending) return;
  ui.hardwareObservation.pending = true;
  try {
    const response = await fetch("/api/hardware/observation", { cache: "no-store" });
    if (!response.ok) throw new Error(`observation status ${response.status}`);
    const payload = await response.json();
    const validated = validateHardwareObservation(payload);
    ui.hardwareObservation.latest = payload;
    if (ui.view === "controller") {
      renderControllerDiagnostics($("controller-diagnostics"), payload);
    }
    ui.hardwareObservation.error = "";
    recordCurrentHardwareObservation(payload);
    if ((ui.hardwareObservation.active || ui.hardwareObservation.autoActivate)
        && performance.now() - ui.hardwareObservation.lastHealthRequestAt >= 2_000) {
      refreshHardwareHealth().catch((error) => {
        ui.hardwareObservation.error = `health refresh: ${error.message}`;
      });
    }
    if (ui.hardwareObservation.active && validated.availableSides.length > 0) {
      const result = applyHardwareObservation(
        sim,
        payload,
        performance.now(),
        ui.hardwareObservation.softwareZero,
        ui.hardwareObservation.angleSource,
      );
      const signature = `${result.sequences.left}:${result.sequences.right}`;
      if (signature !== ui.hardwareObservation.lastAppliedSignature) {
        ui.hardwareObservation.lastAppliedSignature = signature;
      }
    } else if (ui.hardwareObservation.active) {
      clearHardwareObservationHistory(sim);
    } else if (ui.hardwareObservation.autoActivate && !ui.hardwareObservation.requesting) {
      ui.hardwareObservation.autoActivate = false;
      toggleHardwareObservation(true).catch((error) => {
        appendTerminal(`[hardware] automatic live-state request failed · ${error.message}`, "err");
      });
    }
  } catch (error) {
    ui.hardwareObservation.error = error.message;
  } finally {
    ui.hardwareObservation.pending = false;
    renderHardwareObservationState();
  }
}

function setHardwareObservationActive(active) {
  if (active) {
    const validated = validateHardwareObservation(ui.hardwareObservation.latest);
    if (validated.availableSides.length === 0) throw new Error("no fresh ESP32 leg stream is available");
    beginPlaybackSelection();
    policyPlayer.pause();
    ui.policyMode = false;
    ui.watchTraining = false;
    sim.playMode = false;
    sim.scenario = "hardware-observation";
    ui.hardwareObservation.active = true;
    robot.setObservationRootPitchDegrees(ui.hardwareObservation.softwareZero?.torsoForwardDeg || 0);
    applyHardwareObservation(
      sim,
      ui.hardwareObservation.latest,
      performance.now(),
      ui.hardwareObservation.softwareZero,
      ui.hardwareObservation.angleSource,
    );
    if (!selectedJoint().observationValid) {
      const firstObserved = sim.joints.find((joint) => joint.observationValid);
      if (firstObserved) selectJoint(firstObserved.id);
    }
    appendTerminal(
      `[hardware] live ${validated.availableSides.join(" + ")} state applied to USD · `
      + `${ui.hardwareObservation.angleSource.toUpperCase()} angle source · diagnostic tx ${Number(ui.hardwareObservation.latest?.txBytes) || 0} bytes`,
      "ok",
    );
  } else {
    ui.hardwareObservation.active = false;
    ui.hardwareObservation.lastAppliedSignature = "";
    ui.hardwareObservation.recording = false;
    robot.setObservationRootPitchDegrees(0);
    clearHardwareObservationHistory(sim);
    appendTerminal("[hardware] live state source released · simulation remains paused", "warn");
  }
  renderHardwareObservationState();
}

async function toggleHardwareObservation(forceActive = !ui.hardwareObservation.active) {
  if (!forceActive) {
    setHardwareObservationActive(false);
    try {
      await requestJson("/api/hardware/observation/stream", {
        method: "POST",
        body: JSON.stringify({ enabled: false }),
      });
      ui.hardwareObservation.streamRequested = false;
    } catch (error) {
      appendTerminal(`[hardware] observe-off request failed · ${error.message}`, "warn");
    }
    return;
  }

  ui.hardwareObservation.requesting = true;
  renderHardwareObservationState();
  try {
    const request = await requestJson("/api/hardware/observation/stream", {
      method: "POST",
      body: JSON.stringify({ enabled: true }),
    });
    ui.hardwareObservation.streamRequested = true;
    const deadline = performance.now() + 4_000;
    let validated = { availableSides: [] };
    while (performance.now() < deadline) {
      await pollHardwareObservation();
      validated = validateHardwareObservation(ui.hardwareObservation.latest);
      if (validated.availableSides.length === 2) break;
      await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    if (validated.availableSides.length === 0) {
      const failures = Object.values(request.sides || {})
        .flatMap((side) => side.errors || []);
      throw new Error(failures[0] || "no fresh DB2/DB3 frames arrived; flash an observation-protocol firmware and retry");
    }
    setHardwareObservationActive(true);
  } finally {
    ui.hardwareObservation.requesting = false;
    renderHardwareObservationState();
  }
}

function safetyAcknowledgements() {
  return Object.fromEntries(
    [...document.querySelectorAll("[data-safety-ack]")].map((input) => [
      input.dataset.safetyAck,
      input.checked,
    ]),
  );
}

function allSafetyAcknowledged() {
  return [...document.querySelectorAll("[data-safety-ack]")].every((input) => input.checked);
}

function renderHardwareControlState() {
  const armed = ui.hardwareControl.frontendArmed && Boolean(ui.hardwareControl.leaseToken);
  const button = $("hardware-control-lock");
  button.classList.toggle("armed", armed);
  button.textContent = armed
    ? `FRONTEND ARMED · ${Math.ceil(ui.hardwareControl.expiresInMs / 1000)}s`
    : "CONTROL LOCKED";
  const target = selectedJoint();
  $("hardware-send-target").disabled = !(
    armed
    && ui.hardwareObservation.active
    && ui.axisCategory === "leg"
    && target.observationModelApplied
  );
}

async function pollHardwareControlState() {
  try {
    const response = await fetch("/api/hardware/control/status", { cache: "no-store" });
    if (!response.ok) return;
    const status = await response.json();
    ui.hardwareControl.expiresInMs = Number(status.expiresInMs) || 0;
    if (!status.frontendArmed) {
      ui.hardwareControl.frontendArmed = false;
      ui.hardwareControl.leaseToken = "";
    }
    renderHardwareControlState();
  } catch (_error) {
    ui.hardwareControl.frontendArmed = false;
    ui.hardwareControl.leaseToken = "";
    renderHardwareControlState();
  }
}

async function revokeHardwareControl() {
  try {
    await requestJson("/api/hardware/control/revoke", {
      method: "POST",
      body: JSON.stringify({ reason: "frontend_revoke" }),
    });
  } finally {
    ui.hardwareControl.challenge = "";
    ui.hardwareControl.leaseToken = "";
    ui.hardwareControl.frontendArmed = false;
    ui.hardwareControl.expiresInMs = 0;
    renderHardwareControlState();
  }
}

const requestedRenderer = new URLSearchParams(window.location.search).get("renderer");
const webglAvailable = requestedRenderer !== "2d" && supportsWebGL2();
const softwareRenderer = requestedRenderer === "swiftshader";
const softwareFrameIntervalMs = 66;

function createViewer(createWebGL, createSoftware, label) {
  if (!webglAvailable) return createSoftware();
  try {
    return createWebGL();
  } catch (error) {
    appendTerminal(`[display] ${label} WebGL failed · ${error.message}`, "warn");
    return createSoftware();
  }
}

// Keep the controller inspector on Canvas 2D so the robot owns the only WebGL
// context. This is also usable when Chrome falls back to SwiftShader.
const board = new SoftwarePanelViewer($("board-canvas"), {
  title: "ESP32 PIN MAP",
});

const cadOptions = {
  onStatus: (message, kind) => {
    $("cad-status").className = `load-status ${kind}`;
    $("cad-status").innerHTML = "<span></span>";
    $("cad-status").append(document.createTextNode(message));
  },
  onModel: (model) => {
    $("cad-model").value = model.key;
    $("cad-model-name").textContent = model.model.toUpperCase();
    $("cad-model-dimensions").textContent = `${model.dimensionsMm.map((value) => Number(value).toFixed(0)).join(" × ")} MM`;
    $("cad-model-axis").textContent = `METRES · +${model.axis.toUpperCase()} SHAFT`;
    $("cad-evidence-model").textContent = model.model;
    $("cad-evidence-sha").textContent = `${model.sourceStepSha256.slice(0, 10)}…${model.sourceStepSha256.slice(-6)}`;
    $("cad-evidence-sha").title = model.sourceStepSha256;
    $("cad-evidence-housing").textContent = `${model.housingTriangles.toLocaleString()} tris · ${model.housingSolidCount} solids`;
    $("cad-evidence-output").textContent = `${model.outputTriangles.toLocaleString()} tris · ${model.outputSolidCount} solid`;
    $("cad-evidence-axis").textContent = `Source +${model.axis.toUpperCase()} · coaxial`;
    $("cad-evidence-note").textContent = model.note;
    $("cad-source-download").href = model.sourceUrl;
  },
};

const createSoftwareCad = () => new SoftwarePanelViewer($("cad-canvas"), {
    title: "ACTUATOR CAD",
    onStatus: cadOptions.onStatus,
  });
class LazyCadViewer {
  constructor() {
    this.viewer = null;
    this.modelKey = "x8-pro";
    this.angle = 0;
    this.wireframe = true;
    this.exploded = false;
    this.housingVisible = true;
    this.outputVisible = true;
  }

  ensure() {
    if (this.viewer) return this.viewer;
    this.viewer = createViewer(
      () => new CadViewer($("cad-canvas"), cadOptions),
      createSoftwareCad,
      "CAD",
    );
    this.viewer.setModel(this.modelKey);
    this.viewer.setJointAngle(this.angle);
    this.viewer.setWireframe(this.wireframe);
    this.viewer.setExploded(this.exploded);
    this.viewer.setHousingVisible(this.housingVisible);
    this.viewer.setOutputVisible(this.outputVisible);
    return this.viewer;
  }

  setActive(on) {
    if (on) this.ensure().setActive(true);
    else this.viewer?.setActive(false);
  }

  setModel(key) { this.modelKey = key; this.viewer?.setModel(key); }
  setJointAngle(value) { this.angle = value; this.viewer?.setJointAngle(value); }
  setWireframe(on) { this.wireframe = Boolean(on); this.viewer?.setWireframe(on); }
  setExploded(on) { this.exploded = Boolean(on); this.viewer?.setExploded(on); }
  setHousingVisible(on) { this.housingVisible = Boolean(on); this.viewer?.setHousingVisible(on); }
  setOutputVisible(on) { this.outputVisible = Boolean(on); this.viewer?.setOutputVisible(on); }
  resize() { this.viewer?.resize(); }
  fit() { this.viewer?.fit(); }
}

// Keep the live USD as the only WebGL workload until the operator opens the
// CAD tab. The actuator remains interactive 3D, including under SwiftShader.
const cad = new LazyCadViewer();

const robotOptions = {
  maxFrameRate: softwareRenderer ? 15 : 30,
  softwareRendering: softwareRenderer,
  onJoint: (canId) => {
    ui.motorCategory = "legs";
    document.querySelectorAll("[data-motor-category]").forEach((entry) => {
      entry.classList.toggle("active", entry.dataset.motorCategory === "legs");
    });
    makeJointCards();
    selectJoint(canId);
  },
  onArmMotor: (id) => {
    ui.motorCategory = "arms";
    document.querySelectorAll("[data-motor-category]").forEach((entry) => {
      entry.classList.toggle("active", entry.dataset.motorCategory === "arms");
    });
    makeJointCards();
    selectArmMotor(id);
  },
  onStatus: (message, kind) => {
    $("robot-load-status").className = `load-status robot-load-status ${kind}`;
    $("robot-load-status").innerHTML = "<span></span>";
    $("robot-load-status").append(document.createTextNode(message));
  },
};

const robot = createViewer(
  () => new Robot3D($("robot-canvas"), robotOptions),
  () => new SoftwareRobotViewer($("robot-canvas"), robotOptions),
  "robot",
);

if (!webglAvailable) {
  appendTerminal("[display] WebGL unavailable · using measured-state 2D robot view", "warn");
}

function applyPolicyFrame(frame, policy) {
  const toDegrees = (radians) => radians * 180 / Math.PI;
  sim.scenario = "rl-policy";
  sim.playMode = true;
  sim.time = frame.time;
  sim.joints.forEach((joint, index) => {
    const angle = 180 + toDegrees(frame.q[index] || 0);
    joint.angle = Math.max(joint.minAngle, Math.min(joint.maxAngle, angle));
    joint.rawAngle = joint.angle % 360;
    joint.desiredPosition = joint.angle;
    joint.velocity = toDegrees(frame.dq[index] || 0);
    joint.torque = 0;
  });
  armMotorStates.forEach((state, index) => {
    state.angleDeg = toDegrees(frame.q[index + 12] || 0);
    state.velocityDegS = toDegrees(frame.dq[index + 12] || 0);
    state.torqueNm = 0;
  });
  const loads = frame.contactLoadsKg || [0, 0, 0, 0];
  const leftLoad = loads[0] + loads[1];
  const rightLoad = loads[2] + loads[3];
  sim.gait.left = {
    phase: frame.phase,
    mode: leftLoad > 1 ? "policy stance" : "policy swing",
    swing: leftLoad <= 1,
    contact: Math.min(1, leftLoad / 21),
  };
  sim.gait.right = {
    phase: (frame.phase + 0.5) % 1,
    mode: rightLoad > 1 ? "policy stance" : "policy swing",
    swing: rightLoad <= 1,
    contact: Math.min(1, rightLoad / 21),
  };
  const constrained = Boolean(policy.config?.verticalConstraint);
  robot.setVerticalConstraintEnabled(constrained);
  robot.setExternalRootPose(frame.base, loads);
  $("vertical-constraint").checked = constrained;
}

const policyPlayer = new RLPolicyPlayer({
  onFrame: applyPolicyFrame,
  onState: (state) => {
    if ($("rl-timeline")) {
      $("rl-timeline").disabled = !state.loaded;
      $("rl-timeline").max = String(Math.max(0.01, state.duration));
      $("rl-timeline").value = String(state.elapsed);
      $("rl-time-output").textContent = `${state.elapsed.toFixed(2)} / ${state.duration.toFixed(2)} s`;
    }
    if (state.loaded) {
      $("rl-policy-mode").textContent = state.config?.verticalConstraint ? "Z GUIDE" : "FREE ROOT";
      $("rl-root-summary").textContent = state.config?.verticalConstraint ? "GUIDE ENABLED" : "GUIDE DISABLED";
    }
  },
});

function switchView(name) {
  ui.view = name;
  const workspace = document.querySelector(".workspace");
  document.querySelectorAll("[data-view]").forEach((view) => view.classList.toggle("active", view.dataset.view === name));
  document.querySelectorAll("[data-view-target]").forEach((button) => button.classList.toggle("active", button.dataset.viewTarget === name));
  robot.setActive(name === "sim");
  cad.setActive(name === "cad");
  board.setActive(name === "controller");
  if (name === "controller" && ui.hardwareObservation.latest) {
    renderControllerDiagnostics($("controller-diagnostics"), ui.hardwareObservation.latest);
  }
  if (workspace) {
    workspace.scrollTop = 0;
    requestAnimationFrame(() => { workspace.scrollTop = 0; });
  }
  if (name === "sim") setTimeout(() => robot.resize(), 20);
  if (name === "cad") setTimeout(() => { cad.resize(); cad.fit(); }, 20);
  if (name === "controller") setTimeout(() => board.resize(), 20);
  if (name === "devices" || name === "firmware") renderEspDevices();
}

function setupNavigation() {
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewTarget));
  });
  const requestedView = new URLSearchParams(window.location.search).get("view");
  if (["sim", "cad", "controller", "devices", "firmware"].includes(requestedView)) {
    switchView(requestedView);
  }
}

function makeJointCards() {
  const list = $("joint-list");
  list.innerHTML = "";
  if (ui.motorCategory === "arms") {
    for (const definition of DROPBEAR_ARM_MOTOR_BINDINGS) {
      const state = armMotorStates.find((entry) => entry.id === definition.id);
      const button = document.createElement("button");
      button.type = "button";
      button.className = [
        "joint-card",
        "arm-card",
        definition.motor === "RMD-X10" ? "x10" : "x8",
        definition.closedLoop ? "closed-loop" : "",
      ].filter(Boolean).join(" ");
      button.dataset.armMotorId = definition.id;
      button.style.setProperty("--side-color", definition.side === "left" ? "var(--left)" : "var(--right)");
      button.innerHTML = `
        <div class="joint-card-top">
          <b>${definition.label}</b>
          <code>${definition.motor}</code>
        </div>
        <div class="joint-card-state">
          <span>SHAFT<em data-field="angle">${state.angleDeg.toFixed(1)}°</em></span>
          <span><i class="joint-dot live"></i>USD<em>${definition.usdJoint}</em></span>
        </div>`;
      button.addEventListener("click", () => selectArmMotor(definition.id));
      list.appendChild(button);
    }
    $("motor-map-title").textContent = "Installed arm motor map";
    return;
  }
  for (const definition of JOINT_DEFINITIONS) {
    const binding = dropbearUsdBinding(definition.id);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "joint-card";
    button.dataset.jointId = String(definition.id);
    button.style.setProperty("--side-color", definition.side === "left" ? "var(--left)" : "var(--right)");
    button.innerHTML = `
      <div class="joint-card-top">
        <b>${definition.label}</b>
        <code title="${binding?.modelName || binding?.variant || "RMD"} · FW ${binding?.motorFirmware || "unknown"} · ${binding?.anglePayload || "angle layout unknown"} · ${binding?.encoderProfile || "feedback unknown"}">${definition.canId} · ${binding?.motor || "RMD"} ${binding?.reductionRatio || "?"}:1 · FW ${binding?.motorFirmware || "?"}</code>
      </div>
      <div class="joint-card-state">
        <span><i class="joint-dot" data-field="motor-dot"></i>CAN MOTOR<em data-field="motor-angle">WAITING</em></span>
        <span><i class="joint-dot" data-field="sensor-dot"></i>AS5600<em data-field="sensor-angle">WAITING</em></span>
      </div>
      <div class="joint-card-model"><span>MODEL</span><em data-field="angle">180.0°</em></div>`;
    button.addEventListener("click", () => selectJoint(definition.id));
    list.appendChild(button);
  }
  $("motor-map-title").textContent = "Installed leg motor map";
}

function selectJoint(id) {
  ui.axisCategory = "leg";
  ui.selectedArmMotorId = null;
  robot.setArmSelection(null);
  ui.selectedJointId = Number(id);
  ui.scopeHistory = [];
  ui.cadManual = false;
  const target = selectedJoint();
  $("selected-name").textContent = target.label;
  const usdBinding = dropbearUsdBinding(target.id);
  $("selected-can").textContent = usdBinding
    ? `${target.canId} · ${usdBinding.modelName || usdBinding.variant} · FW ${usdBinding.motorFirmware} · ${usdBinding.angleReference}`
    : target.canId;
  const cadModelKey = usdBinding?.motor === "RMD-X8" ? "x8-pro" : "x10-s2";
  cad.setModel(cadModelKey);
  $("cad-model").value = cadModelKey;
  $("selected-usd").textContent = usdBinding
    ? `USD ${usdBinding.usdJoint}${usdBinding.closure ? " · CLOSURE" : " · FK"}`
    : "USD BINDING UNRESOLVED";
  $("cad-joint-name").textContent = target.label;
  $("position-target").value = String(Math.round(target.desiredPosition - 180));
  $("position-target").min = String(target.minAngle - 180);
  $("position-target").max = String(target.maxAngle - 180);
  $("position-output").textContent = `${Math.round(target.desiredPosition - 180)}° q`;
  $("torque-target").value = String(Math.round(target.command * 100));
  $("torque-output").textContent = `${target.command.toFixed(2)} N·m`;
  $("impedance-toggle").checked = target.impedanceEnabled;
  $("impedance-toggle").disabled = !target.impedanceCapable;
  $("position-target").disabled = !target.impedanceCapable;
  $("torque-target").disabled = false;
  $("fault-sensor").disabled = false;
  $("fault-thermal").disabled = false;
  document.querySelectorAll(".joint-card").forEach((card) => card.classList.toggle("active", Number(card.dataset.jointId) === target.id));
}

function selectArmMotor(id) {
  const binding = dropbearArmMotorBinding(id);
  const state = armMotorStates.find((entry) => entry.id === id);
  if (!binding || !state) return;
  ui.axisCategory = "arm";
  ui.cadManual = false;
  ui.selectedArmMotorId = id;
  robot.setArmSelection(id);
  const cadModelKey = binding.motor === "RMD-X8" ? "x8-pro" : "x10-s2";
  cad.setModel(cadModelKey);
  $("cad-model").value = cadModelKey;
  $("selected-name").textContent = binding.label;
  $("selected-can").textContent = `${binding.motor} · AUX`;
  $("selected-usd").textContent = [
    `USD ${binding.usdJoint}`,
    binding.sourceSemantic.toUpperCase(),
    binding.closedLoop ? "CLOSED LOOP" : null,
  ].filter(Boolean).join(" · ");
  $("cad-joint-name").textContent = binding.label;
  $("position-target").min = "-120";
  $("position-target").max = "120";
  $("position-target").value = String(state.angleDeg);
  $("position-target").disabled = false;
  $("position-output").textContent = `${state.angleDeg.toFixed(0)}°`;
  $("torque-target").value = "0";
  $("torque-target").disabled = true;
  $("torque-output").textContent = "0.00 N·m";
  $("impedance-toggle").checked = false;
  $("impedance-toggle").disabled = true;
  $("fault-sensor").disabled = true;
  $("fault-thermal").disabled = true;
  document.querySelectorAll(".arm-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.armMotorId === id);
  });
}

function setupMotorCategories() {
  document.querySelectorAll("[data-motor-category]").forEach((button) => {
    button.addEventListener("click", () => {
      ui.motorCategory = button.dataset.motorCategory;
      document.querySelectorAll("[data-motor-category]").forEach((entry) => {
        entry.classList.toggle("active", entry === button);
      });
      makeJointCards();
      if (ui.motorCategory === "arms") {
        selectArmMotor(ui.selectedArmMotorId || DROPBEAR_ARM_MOTOR_BINDINGS[0].id);
      } else {
        selectJoint(ui.selectedJointId);
      }
    });
  });
}

function rememberPlaybackSelection() {
  const value = $("scenario")?.value;
  if (!value) return;
  const key = ui.playbackFamily === "gr00t" ? "gr00t" : ui.playbackMode;
  ui.playbackSelections[key] = value;
}

function syncPlaybackButtons() {
  const modeButton = $("playback-mode");
  modeButton.dataset.mode = ui.playbackMode === "rl" ? "trained" : "preset";
  modeButton.textContent = ui.playbackMode === "rl" ? "LOCOMOTION" : "DIAGNOSTIC";
  modeButton.setAttribute("aria-pressed", String(ui.playbackMode === "rl"));
  const familyButton = $("playback-family");
  familyButton.dataset.family = ui.playbackFamily;
  familyButton.textContent = ui.playbackFamily === "gr00t" ? "GR00T" : "CLASSIC";
  familyButton.setAttribute("aria-pressed", String(ui.playbackFamily === "gr00t"));
}

function populatePlaybackSources(mode, selectedValue = null) {
  const sources = ui.playbackFamily === "gr00t"
    ? GR00T_WBC_PLAYBACK_SOURCES
    : mode === "rl"
      ? RL_SOURCES
      : PRESET_SOURCES;
  const select = $("scenario");
  select.innerHTML = "";
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source.value;
    option.textContent = source.label;
    if (source.disabled) {
      option.disabled = true;
    } else if (
      ui.playbackFamily === "gr00t"
      && ui.gr00tAvailability[source.readiness] !== true
    ) {
      option.disabled = true;
      option.textContent += ui.gr00tAvailability[source.readiness] === false
        ? " · unavailable"
        : " · checking";
    } else if (source.value === "latest" && !ui.latestPolicyUrl) {
      option.disabled = true;
    } else if (source.value === "live" && !ui.latestRLStatus?.livePolicyUrl) {
      option.textContent += " · waiting";
    }
    select.appendChild(option);
  }
  const fallback = ui.playbackFamily === "gr00t"
    ? "g1-published-stand"
    : mode === "rl"
      ? "locomotion-export-required"
      : "neutral";
  select.value = sources.some((source) => source.value === selectedValue) ? selectedValue : fallback;
  const selectionKey = ui.playbackFamily === "gr00t" ? "gr00t" : mode;
  ui.playbackSelections[selectionKey] = select.value || fallback;
  $("playback-source-label").textContent = ui.playbackFamily === "gr00t"
    ? "GR00T WBC SOURCE"
    : mode === "rl"
      ? "LOCOMOTION POLICY PLAYBACK"
      : "MOTION PRESET";
}

function setPlaybackMode(mode, selectedValue = null) {
  rememberPlaybackSelection();
  // PRESET/TRAINED is the classic playback axis. Entering either state from
  // GR00T returns to CLASSIC, preventing a meaningless PRESET + GR00T pair.
  ui.playbackFamily = "classic";
  ui.playbackMode = mode === "rl" ? "rl" : "preset";
  syncPlaybackButtons();
  populatePlaybackSources(
    ui.playbackMode,
    selectedValue ?? ui.playbackSelections[ui.playbackMode],
  );
}

function setPlaybackFamily(family, selectedValue = null) {
  rememberPlaybackSelection();
  ui.playbackFamily = family === "gr00t" ? "gr00t" : "classic";
  // GR00T sources are WBC policies/fixtures, never classic motion presets.
  // Returning to CLASSIC intentionally remains in TRAINED, restoring RL.
  ui.playbackMode = "rl";
  syncPlaybackButtons();
  const key = ui.playbackFamily === "gr00t" ? "gr00t" : "rl";
  populatePlaybackSources("rl", selectedValue ?? ui.playbackSelections[key]);
}

async function configurePlaybackSource(
  value,
  {
    preserveLiveWatch = false,
    generation = beginPlaybackSelection(),
  } = {},
) {
  if (!isCurrentPlaybackSelection(generation)) return false;
  if (ui.hardwareObservation.active) setHardwareObservationActive(false);
  if (ui.playbackFamily !== "classic") {
    throw new Error("classic playback configuration requested while GR00T is selected");
  }
  ui.playbackSelections[ui.playbackMode] = value;
  policyPlayer.pause();
  if (ui.playbackMode === "preset") {
    ui.policyMode = false;
    ui.loadedPolicySource = null;
    ui.watchTraining = preserveLiveWatch && ui.watchTraining;
    robot.setExternalRootPose(null, null);
    robot.setVerticalConstraintEnabled($("vertical-constraint").checked);
    sim.setScenario(value);
    sim.setPlay(false);
    if (value === "manual") $("impedance-toggle").checked = false;
    appendTerminal(`[dashboard] preset armed · ${value} · press Play to run`, "ok");
    return true;
  }

  ui.policyMode = true;
  sim.scenario = "rl-policy";
  sim.setPlay(false);
  ui.watchTraining = value === "live";
  if (value === "locomotion-export-required") {
    policyPlayer.clear();
    ui.loadedPolicySource = null;
    appendTerminal("[policy] dropbear-locomotion checkpoint found; browser trajectory export is not present", "warn");
    return true;
  } else if (value === "reference") {
    if (!await loadPolicy(
      "/assets/rl/dropbear-walk-reference.json",
      "Tracked reference walking policy",
      { generation },
    )) return false;
  } else if (value === "authored") {
    if (!await loadPolicy(
      "/assets/rl/dropbear-authored-reference.json",
      "Authored residual-zero walking baseline",
      { generation },
    )) return false;
  } else if (value === "latest" && ui.latestPolicyUrl) {
    if (!await loadPolicy(
      ui.latestPolicyUrl,
      "Latest completed local walking policy",
      { generation },
    )) return false;
  } else if (value === "live") {
    ui.previewLoadedKey = null;
    await pollRLStatus();
    if (!isCurrentPlaybackSelection(generation)) return false;
    if (!ui.latestRLStatus?.livePolicyUrl) {
      policyPlayer.clear();
      robot.setExternalRootPose(null, null);
      robot.setVerticalConstraintEnabled($("vertical-constraint").checked);
    }
    appendTerminal("[rl] live training policy selected; each completed update will replace playback", "ok");
  } else if (value.startsWith("session:")) {
    const experimentId = value.slice("session:".length);
    const session = ui.rlSessions.find(
      (candidate) => candidate.experimentId === experimentId,
    );
    if (!session?.policyUrl) {
      throw new Error("selected session does not have a replayable policy");
    }
    await loadPolicy(
      session.policyUrl,
      `Stored run · ${experimentId.slice(-8).toUpperCase()}`,
      { generation },
    );
    if (!isCurrentPlaybackSelection(generation)) return false;
  }
  if (!isCurrentPlaybackSelection(generation)) return false;
  ui.loadedPolicySource = value;
  return true;
}

function setupSimControls() {
  const resolutionStorageKey = "dropbear-usd-resolution-v5";
  const savedResolution = Number(localStorage.getItem(resolutionStorageKey) || 100);
  const resolutionPercent = Math.max(50, Math.min(200, savedResolution));
  $("usd-resolution").value = String(resolutionPercent);
  $("usd-resolution-output").textContent = `${resolutionPercent}%`;
  robot.setResolutionScale(resolutionPercent / 100);
  $("usd-resolution").addEventListener("input", (event) => {
    const percent = Number(event.target.value);
    robot.setResolutionScale(percent / 100);
    $("usd-resolution-output").textContent = `${percent}%`;
    localStorage.setItem(resolutionStorageKey, String(percent));
  });
  setPlaybackMode("preset", "neutral");
  $("sim-toggle").addEventListener("click", async () => {
    if (ui.gr00tPlayBusy) return;
    const generation = beginPlaybackSelection();
    try {
      await waitForGr00tWbcPlaybackIdle();
    } catch (error) {
      if (isCurrentPlaybackSelection(generation)) {
        appendTerminal(`[gr00t] previous playback did not stop · ${error.message}`, "err");
      }
      return;
    }
    if (!isCurrentPlaybackSelection(generation)) return;
    const visibleFamily = $("playback-family").dataset.family === "gr00t"
      ? "gr00t"
      : "classic";
    if (visibleFamily === "gr00t") {
      const selectedSource = $("scenario").value;
      const source = GR00T_WBC_PLAYBACK_SOURCES.find(
        (candidate) => candidate.value === selectedSource,
      );
      policyPlayer.pause();
      sim.setPlay(false);
      ui.policyMode = false;
      ui.watchTraining = false;
      ui.playbackFamily = "gr00t";
      ui.playbackMode = "rl";
      ui.playbackSelections.gr00t = selectedSource;
      if (!source) {
        appendTerminal(`[gr00t] unknown WBC playback source · ${selectedSource}`, "err");
        return;
      }
      if (ui.gr00tAvailability[source.readiness] !== true) {
        appendTerminal(
          `[gr00t] ${selectedSource} unavailable · required decoder gate is closed`,
          "warn",
        );
        return;
      }
      const playButton = $("sim-toggle");
      const requestController = openPlaybackRequest(generation);
      if (!requestController) return;
      ui.gr00tPlayBusy = true;
      playButton.disabled = true;
      playButton.dataset.busy = "1";
      playButton.setAttribute("aria-busy", "true");
      try {
        const payload = await playGr00tWbcSource(
          selectedSource,
          {
            dispatch: false,
            signal: requestController.signal,
          },
        );
        if (
          !isCurrentPlaybackSelection(generation)
          || $("playback-family").dataset.family !== "gr00t"
          || $("scenario").value !== selectedSource
          || ui.gr00tAvailability[source.readiness] !== true
        ) return;
        window.dispatchEvent(new CustomEvent(
          "dropbear:retargeted-pose",
          { detail: payload },
        ));
      } catch (error) {
        if (!isCurrentPlaybackSelection(generation)) return;
        appendTerminal(
          `[gr00t] selected WBC source rejected · ${selectedSource} · ${error.message}`,
          "err",
        );
      } finally {
        releasePlaybackRequest(requestController);
        ui.gr00tPlayBusy = false;
        playButton.disabled = false;
        delete playButton.dataset.busy;
        playButton.setAttribute("aria-busy", "false");
      }
      return;
    }
    // The visible mode switch is the playback authority.  Reconcile against it
    // on every click so stale policy/training state can never consume a preset
    // Play command and leave the dashboard in guarded pause.
    const visibleMode = $("playback-mode").dataset.mode === "trained" ? "rl" : "preset";
    if (visibleMode === "preset") {
      const selectedPreset = $("scenario").value;
      if (!ui.policyMode && sim.playMode) {
        sim.setPlay(false);
        return;
      }
      // This is intentionally the former RUN EXAMPLE sequence: reload the
      // selected trajectory to reset its phase, then explicitly start it.
      policyPlayer.pause();
      ui.policyMode = false;
      ui.playbackMode = "preset";
      ui.watchTraining = false;
      robot.setExternalRootPose(null, null);
      robot.setVerticalConstraintEnabled($("vertical-constraint").checked);
      sim.setScenario(selectedPreset);
      sim.setPlay(true);
      switchView("sim");
      appendTerminal(`[dashboard] selected preset started · ${selectedPreset}`, "ok");
      return;
    }
    if (policyPlayer.playing) {
      policyPlayer.pause();
      return;
    }
    const selectedPolicy = $("scenario").value;
    ui.policyMode = true;
    if (!policyPlayer.policy || ui.loadedPolicySource !== selectedPolicy) {
      const configured = await configurePlaybackSource(
        selectedPolicy,
        { generation },
      );
      if (!configured || !isCurrentPlaybackSelection(generation)) return;
    }
    if (!isCurrentPlaybackSelection(generation)) return;
    if (policyPlayer.policy) {
      policyPlayer.seek(0);
      policyPlayer.play();
      switchView("sim");
      appendTerminal(`[rl] selected policy started · ${selectedPolicy}`, "ok");
    } else {
      appendTerminal(`[rl] ${selectedPolicy} has no policy frames yet`, "warn");
    }
  });
  $("sim-reset").addEventListener("click", () => {
    if (ui.hardwareObservation.active) setHardwareObservationActive(false);
    beginPlaybackSelection();
    policyPlayer.pause();
    ui.policyMode = false;
    ui.loadedPolicySource = null;
    ui.watchTraining = false;
    sim.reset();
    setPlaybackMode("preset", "neutral");
    robot.setVerticalConstraintEnabled(true);
    robot.setExternalRootPose(null, null);
    $("vertical-constraint").checked = true;
    robot.resetGroundConstraint();
    armMotorStates.forEach((state) => {
      state.angleDeg = 0;
      state.velocityDegS = 0;
      state.torqueNm = 0;
    });
    ui.lastRobotFrameAt = performance.now();
    ui.scopeHistory = [];
    ui.motorCategory = "legs";
    document.querySelectorAll("[data-motor-category]").forEach((entry) => {
      entry.classList.toggle("active", entry.dataset.motorCategory === "legs");
    });
    makeJointCards();
    selectJoint(0x141);
    appendTerminal("[dashboard] simulation reset", "warn");
  });
  $("sim-speed").addEventListener("change", (event) => { sim.speed = Number(event.target.value); });
  $("playback-mode").addEventListener("click", async () => {
    setPlaybackMode(ui.playbackMode === "rl" ? "preset" : "rl");
    await configurePlaybackSource($("scenario").value);
  });
  $("playback-family").addEventListener("click", async () => {
    if (ui.hardwareObservation.active) setHardwareObservationActive(false);
    const generation = beginPlaybackSelection();
    policyPlayer.pause();
    sim.setPlay(false);
    ui.policyMode = false;
    ui.loadedPolicySource = null;
    ui.watchTraining = false;
    if (ui.playbackFamily === "classic") {
      setPlaybackFamily("gr00t");
      sim.setScenario("manual");
      appendTerminal(
        `[gr00t] WBC source armed · ${$("scenario").value} · press Play to apply`,
        "ok",
      );
      return;
    }
    setPlaybackFamily("classic");
    await configurePlaybackSource($("scenario").value, { generation });
  });
  $("scenario").addEventListener("change", async (event) => {
    if (ui.hardwareObservation.active) setHardwareObservationActive(false);
    if (ui.playbackFamily === "gr00t") {
      ui.playbackSelections.gr00t = event.target.value;
      beginPlaybackSelection();
      policyPlayer.pause();
      sim.setPlay(false);
      ui.policyMode = false;
      appendTerminal(
        `[gr00t] WBC source armed · ${event.target.value} · press Play to apply`,
        "ok",
      );
      return;
    }
    await configurePlaybackSource(event.target.value);
  });
  $("robot-fit").addEventListener("click", () => robot.fit());
  $("vertical-constraint").addEventListener("change", (event) => {
    robot.setVerticalConstraintEnabled(event.target.checked);
    if (!event.target.checked && !policyPlayer.policy) robot.setExternalRootPose(null, null);
  });
  $("position-target").addEventListener("input", (event) => {
    const value = Number(event.target.value);
    if (ui.axisCategory === "arm") {
      const state = armMotorStates.find((entry) => entry.id === ui.selectedArmMotorId);
      if (state) state.angleDeg = value;
      $("position-output").textContent = `${value.toFixed(0)}°`;
      const cardValue = document.querySelector(`[data-arm-motor-id="${ui.selectedArmMotorId}"] [data-field="angle"]`);
      if (cardValue) cardValue.textContent = `${value.toFixed(1)}°`;
      return;
    }
    const target = selectedJoint();
    sim.setJointTarget(target.id, 180 + value, true);
    $("impedance-toggle").checked = target.impedanceEnabled;
    $("position-output").textContent = `${value.toFixed(0)}° q`;
  });
  $("torque-target").addEventListener("input", (event) => {
    const value = Number(event.target.value);
    sim.setJointTorque(ui.selectedJointId, value);
    $("torque-output").textContent = `${(value / 100).toFixed(2)} N·m`;
  });
  $("impedance-toggle").addEventListener("change", (event) => {
    const target = selectedJoint();
    if (target.impedanceCapable) target.impedanceEnabled = event.target.checked;
  });
  $("fault-sensor").addEventListener("click", () => sim.injectFault("sensor", ui.selectedJointId));
  $("fault-thermal").addEventListener("click", () => sim.injectFault("thermal", ui.selectedJointId));
}

function setupHardwareControls() {
  const angleSource = $("hardware-angle-source");
  if (![...angleSource.options].some((option) => option.value === ui.hardwareObservation.angleSource)) {
    ui.hardwareObservation.angleSource = "auto";
  }
  angleSource.value = ui.hardwareObservation.angleSource;
  angleSource.addEventListener("change", (event) => {
    ui.hardwareObservation.angleSource = event.target.value;
    clearHardwareObservationHistory(sim);
    if (ui.hardwareObservation.active && ui.hardwareObservation.latest) {
      applyHardwareObservation(
        sim,
        ui.hardwareObservation.latest,
        performance.now(),
        ui.hardwareObservation.softwareZero,
        ui.hardwareObservation.angleSource,
      );
    }
    appendTerminal(
      `[hardware] live angle source · ${event.target.options[event.target.selectedIndex].text}`,
      "ok",
    );
    ui.hardwareObservation.lastStateRenderSignature = "";
    renderHardwareObservationState();
  });
  if (ui.hardwareObservation.softwareZero) {
    $("hardware-zero-torso").value = ui.hardwareObservation.softwareZero.torsoForwardDeg;
  }
  $("hardware-observation-toggle").addEventListener("click", async () => {
    try {
      await toggleHardwareObservation();
    } catch (error) {
      appendTerminal(`[hardware] observation source unavailable · ${error.message}`, "err");
    }
  });

  $("hardware-zero-current").addEventListener("click", () => {
    try {
      captureCurrentSoftwareZero();
    } catch (error) {
      appendTerminal(`[hardware] software zero rejected · ${error.message}`, "err");
    }
  });

  $("hardware-record-toggle").addEventListener("click", () => {
    if (ui.hardwareObservation.recording) {
      ui.hardwareObservation.recording = false;
      appendTerminal(
        `[hardware] angle recording stopped · ${ui.hardwareObservation.recordingRows.length.toLocaleString()} rows ready for CSV`,
        "ok",
      );
    } else {
      ui.hardwareObservation.recordingRows = [];
      ui.hardwareObservation.lastRecordedSignature = "";
      ui.hardwareObservation.recording = true;
      recordCurrentHardwareObservation(ui.hardwareObservation.latest);
      appendTerminal(
        "[hardware] angle recording started · external sensor, zeroed, model, and motor-native channels retained separately",
        "ok",
      );
    }
    renderHardwareObservationState();
  });

  $("hardware-record-download").addEventListener("click", downloadAngleRecording);

  $("hardware-control-lock").addEventListener("click", async () => {
    if (ui.hardwareControl.frontendArmed) {
      await revokeHardwareControl();
      appendTerminal("[hardware] frontend control lease revoked", "warn");
      return;
    }
    try {
      const state = await requestJson("/api/hardware/control/advance", {
        method: "POST",
        body: JSON.stringify({ stage: 1 }),
      });
      ui.hardwareControl.challenge = state.challenge;
      document.querySelectorAll("[data-safety-ack]").forEach((input) => { input.checked = false; });
      $("hardware-arm-stage2").disabled = true;
      $("hardware-arm-stage2").hidden = false;
      $("hardware-arm-stage3").hidden = true;
      $("hardware-arm-stage-2").className = "active";
      $("hardware-arm-stage-3").className = "";
      $("hardware-arm-summary").textContent = "Stage 1 of 3 is complete. Review and acknowledge every item before continuing.";
      $("hardware-arm-result").className = "hardware-arm-result";
      $("hardware-arm-result").textContent = "Physical transport remains locked independently of this frontend sequence.";
      $("hardware-arm-dialog").showModal();
    } catch (error) {
      appendTerminal(`[hardware] arm review rejected · ${error.message}`, "err");
    }
  });

  document.querySelectorAll("[data-safety-ack]").forEach((input) => {
    input.addEventListener("change", () => {
      $("hardware-arm-stage2").disabled = !allSafetyAcknowledged();
    });
  });

  $("hardware-arm-stage2").addEventListener("click", async () => {
    try {
      const state = await requestJson("/api/hardware/control/advance", {
        method: "POST",
        body: JSON.stringify({
          stage: 2,
          challenge: ui.hardwareControl.challenge,
          acknowledgements: safetyAcknowledgements(),
        }),
      });
      ui.hardwareControl.challenge = state.challenge;
      $("hardware-arm-stage-2").className = "complete";
      $("hardware-arm-stage-3").className = "active";
      $("hardware-safety-acknowledgements").disabled = true;
      $("hardware-arm-stage2").hidden = true;
      $("hardware-arm-stage3").hidden = false;
      $("hardware-arm-summary").textContent = "Stage 2 of 3 is complete. The final click opens a short frontend lease; the backend transport remains independently locked.";
    } catch (error) {
      $("hardware-arm-result").textContent = error.message;
      appendTerminal(`[hardware] safety acknowledgement rejected · ${error.message}`, "err");
    }
  });

  $("hardware-arm-stage3").addEventListener("click", async () => {
    try {
      const state = await requestJson("/api/hardware/control/advance", {
        method: "POST",
        body: JSON.stringify({
          stage: 3,
          challenge: ui.hardwareControl.challenge,
          confirm: true,
        }),
      });
      ui.hardwareControl.challenge = "";
      ui.hardwareControl.leaseToken = state.leaseToken;
      ui.hardwareControl.frontendArmed = true;
      ui.hardwareControl.expiresInMs = Number(state.expiresInMs) || 0;
      $("hardware-arm-stage-3").className = "complete";
      $("hardware-arm-stage3").hidden = true;
      $("hardware-arm-summary").textContent = "All three stages are complete. The frontend channel is armed for a bounded interval.";
      $("hardware-arm-result").className = "hardware-arm-result ok";
      $("hardware-arm-result").textContent = "Frontend lease active. Physical transport is still locked until the independent hardware backend is installed and admitted.";
      renderHardwareControlState();
      appendTerminal("[hardware] frontend control lease armed · physical transport still locked", "warn");
    } catch (error) {
      $("hardware-arm-result").textContent = error.message;
      appendTerminal(`[hardware] final acknowledgement rejected · ${error.message}`, "err");
    }
  });

  $("hardware-arm-dialog").addEventListener("close", () => {
    $("hardware-safety-acknowledgements").disabled = false;
    if (!ui.hardwareControl.frontendArmed) revokeHardwareControl();
  });

  $("hardware-send-target").addEventListener("click", async () => {
    const target = selectedJoint();
    try {
      await requestJson("/api/hardware/command", {
        method: "POST",
        body: JSON.stringify({
          schema: "dropbear-hardware-command-v1",
          leaseToken: ui.hardwareControl.leaseToken,
          requestId: crypto.randomUUID(),
          jointName: `${target.side}_${target.key}`,
          mode: "joint_position",
          valueSi: (target.desiredPosition - 180) * Math.PI / 180,
        }),
      });
    } catch (error) {
      appendTerminal(`[hardware] command held · ${error.message}`, "warn");
    }
  });

  pollHardwareObservation();
  pollHardwareControlState();
  window.setInterval(pollHardwareObservation, 100);
  window.setInterval(pollHardwareControlState, 1000);
}

function setupCadControls() {
  $("cad-model").addEventListener("change", (event) => {
    ui.cadManual = true;
    cad.setModel(event.target.value);
  });
  $("cad-lines").addEventListener("change", (event) => cad.setWireframe(event.target.checked));
  $("cad-explode").addEventListener("change", (event) => cad.setExploded(event.target.checked));
  $("cad-housing").addEventListener("change", (event) => cad.setHousingVisible(event.target.checked));
  $("cad-output").addEventListener("change", (event) => cad.setOutputVisible(event.target.checked));
  $("cad-fit").addEventListener("click", () => cad.fit());
  $("cad-angle").addEventListener("input", (event) => {
    ui.cadManual = true;
    const value = Number(event.target.value);
    cad.setJointAngle(value);
    $("cad-angle-output").textContent = `${value.toFixed(1)}°`;
  });
}

function setupBoardControls() {
  const groups = [...new Map(CONTROLLER_PINS.map((pin) => [pin.bus, pin.color])).entries()];
  $("bus-legend").innerHTML = "";
  for (const [bus, color] of groups) {
    const button = document.createElement("button");
    button.style.setProperty("--bus-color", color);
    button.innerHTML = `<i></i>${bus}`;
    button.addEventListener("click", () => {
      const pin = CONTROLLER_PINS.find((entry) => entry.bus === bus);
      if (pin) {
        board.focusPin(pin.gpio);
        $("pin-title").textContent = `${bus} SIGNAL GROUP`;
        $("pin-detail").textContent = CONTROLLER_PINS.filter((entry) => entry.bus === bus)
          .map((entry) => `GPIO${entry.gpio} ${entry.role}`).join(" · ");
      }
    });
    $("bus-legend").appendChild(button);
  }

  const map = $("pin-map");
  map.innerHTML = "";
  for (const pin of CONTROLLER_PINS) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "pin-row";
    row.dataset.gpio = String(pin.gpio);
    row.style.setProperty("--pin-color", pin.color);
    row.innerHTML = `<code>GPIO${pin.gpio}</code><b>${pin.bus}</b><span>${pin.role}${pin.inferred ? " · inferred VSPI default" : ""}${pin.optional ? " · optional example" : ""}</span><i></i>`;
    row.addEventListener("click", () => {
      board.focusPin(pin.gpio);
      $("pin-title").textContent = `GPIO${pin.gpio} / ${pin.label}`;
      $("pin-detail").textContent = `${pin.bus} · ${pin.role}${pin.inferred ? ". SPI pin is inferred from Arduino ESP32 VSPI defaults because the firmware sets only CS/INT explicitly." : "."}`;
      document.querySelectorAll(".pin-row").forEach((entry) => entry.classList.toggle("active", entry === row));
    });
    map.appendChild(row);
  }
  $("pin-count").textContent = `${CONTROLLER_PINS.length} NETS`;
  $("board-reset-view").addEventListener("click", () => board.resetView());
  document.querySelectorAll(".controller-tab").forEach((button) => {
    button.addEventListener("click", () => {
      ui.controller = button.dataset.controller;
      document.querySelectorAll(".controller-tab").forEach((entry) => entry.classList.toggle("active", entry === button));
      $("pin-title").textContent = `${ui.controller.toUpperCase()} ESP32`;
      $("pin-detail").textContent = `Chirality ${sim.controllers[ui.controller].chirality}; ${sim.controllers[ui.controller].csv}`;
    });
  });
}

function setupFirmware() {
  $("task-list").innerHTML = TASKS.map((task, index) => `
    <div class="task-row">
      <div class="task-row-top"><b>${task.name}</b><code>CORE ${task.core} · ${task.periodMs} ms</code></div>
      <p>${task.role}</p>
      <div class="task-meter"><i style="width:${12 + index * 4}px;animation-delay:${-index * .23}s"></i></div>
    </div>`).join("");

  const submit = (command) => {
    appendTerminal(`${ui.consoleController}> ${command}`, "command");
    const result = sim.command(command, ui.consoleController);
    appendTerminal(result.output, result.ok ? "ok" : "err");
  };
  $("terminal-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const command = $("terminal-command").value;
    submit(command);
    $("terminal-command").select();
  });
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      $("terminal-command").value = button.dataset.command;
      submit(button.dataset.command);
    });
  });
  document.querySelectorAll(".console-controller-tab").forEach((button) => {
    button.addEventListener("click", () => {
      ui.consoleController = button.dataset.consoleController;
      document.querySelectorAll(".console-controller-tab").forEach((entry) => entry.classList.toggle("active", entry === button));
      appendTerminal(`[dashboard] selected ${ui.consoleController} serial port`, "warn");
    });
  });
  $("fault-can").addEventListener("click", () => sim.injectFault("can"));
  $("fault-serial").addEventListener("click", () => sim.injectFault("serial"));
  $("fault-imu").addEventListener("click", () => sim.injectFault("imu"));

  appendTerminal(`Dropbear low-level twin · source ${DROPBEAR_SOURCE.commit.slice(0, 8)}`, "ok");
  appendTerminal("Serial 115200 · MCP2515 CAN 1000 kbps · MCP clock 8 MHz");
  appendTerminal("Guarded pause active. Live observation leaves ESP32 playMode disabled.", "info");
}

let controlTokenPromise = null;

function invalidateControlToken() {
  controlTokenPromise = null;
}

async function getControlToken() {
  if (!controlTokenPromise) {
    controlTokenPromise = fetch("/api/control-token", {
      cache: "no-store",
      credentials: "same-origin",
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      if (typeof payload.token !== "string" || !payload.token) {
        throw new Error("control token response is invalid");
      }
      return payload.token;
    }).catch((error) => {
      invalidateControlToken();
      throw error;
    });
  }
  return controlTokenPromise;
}

async function requestJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const mutation = method !== "GET" && method !== "HEAD";
  for (let attempt = 0; attempt < (mutation ? 2 : 1); attempt += 1) {
    const headers = new Headers(options.headers || {});
    const request = {
      ...options,
      method,
      headers,
      cache: options.cache || "no-store",
      credentials: "same-origin",
    };
    if (mutation) {
      headers.set("Content-Type", "application/json");
      headers.set("X-Dropbear-Control-Token", await getControlToken());
      request.body = options.body === undefined ? "{}" : options.body;
    }
    const response = await fetch(url, request);
    const payload = await response.json().catch(() => ({}));
    if (response.ok) return payload;
    if (response.status === 403 && mutation && attempt === 0) {
      invalidateControlToken();
      continue;
    }
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  throw new Error("control authorization failed");
}

function selectedEspDevice() {
  return ui.hardwareDevices.latest?.devices?.find(
    (device) => device.id === ui.hardwareDevices.selectedDeviceId,
  ) || null;
}

function selectedFirmwareSource() {
  return ui.hardwareDevices.latest?.sources?.find(
    (source) => source.id === ui.hardwareDevices.selectedSourceId,
  ) || null;
}

function replaceSelectOptions(select, records, selected, label) {
  const signature = records.map((record) => `${record.id}:${label(record)}`).join("|");
  if (select.dataset.signature !== signature) {
    select.replaceChildren(...records.map((record) => {
      const option = document.createElement("option");
      option.value = record.id;
      option.textContent = label(record);
      return option;
    }));
    select.dataset.signature = signature;
  }
  if (records.some((record) => record.id === selected)) select.value = selected;
}

function clearEspBuild(reason = "No firmware has been compiled in this server session.") {
  ui.hardwareDevices.build = null;
  ui.hardwareDevices.compileState = "idle";
  $("esp-build-output").textContent = reason;
  renderEspCompileStatus();
  renderEspUploadInterlock();
}

function renderEspCompileStatus() {
  const status = $("esp-compile-status");
  if (!status) return;
  const state = ui.hardwareDevices.compileState;
  const labels = {
    idle: "READY",
    compiling: "COMPILING",
    passed: "COMPILE PASSED",
    failed: "COMPILE FAILED",
  };
  status.className = `esp-compile-status ${state}`;
  status.querySelector("b").textContent = labels[state] || labels.idle;
}

function renderEspUploadInterlock() {
  const device = selectedEspDevice();
  const build = ui.hardwareDevices.build;
  const expected = device ? `FLASH ${String(device.role).toUpperCase()}` : "FLASH <ROLE>";
  $("esp-confirm-label").textContent = `TYPE ${expected}`;
  const acknowledged = ["esp-ack-supported", "esp-ack-power", "esp-ack-estop"]
    .every((id) => $(id).checked);
  $("esp-upload").disabled = !(
    build?.state === "passed"
    && acknowledged
    && $("esp-flash-confirm").value === expected
    && !ui.hardwareDevices.busy
  );
}

function renderEspDevices() {
  const payload = ui.hardwareDevices.latest;
  if (!payload) return;
  const devices = payload.devices || [];
  const sources = payload.sources || [];
  if (!devices.some((device) => device.id === ui.hardwareDevices.selectedDeviceId)) {
    ui.hardwareDevices.selectedDeviceId = devices[0]?.id || "";
  }
  if (!sources.some((source) => source.id === ui.hardwareDevices.selectedSourceId)) {
    ui.hardwareDevices.selectedSourceId = (
      sources.find((source) => source.family === "universal-behemoth") || sources[0]
    )?.id || "";
  }

  const status = $("esp-device-status");
  status.className = `load-status ${devices.length ? "ok" : "error"}`;
  status.title = "";
  status.innerHTML = "<span></span>";
  status.append(document.createTextNode(`${devices.length} USB DEVICE${devices.length === 1 ? "" : "S"}`));

  const cards = $("esp-device-cards");
  cards.replaceChildren(...devices.map((device) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `esp-device-card${device.id === ui.hardwareDevices.selectedDeviceId ? " active" : ""}`;
    const firmware = device.firmware || {};
    const version = firmware.version || "not reported";
    card.innerHTML = `<header><span class="panel-kicker"></span><span class="device-live"></span></header><h2></h2><small></small><code></code>`;
    card.querySelector(".panel-kicker").textContent = device.tty;
    card.querySelector(".device-live").textContent = String(device.serialState || "unknown").toUpperCase();
    card.querySelector("h2").textContent = device.role.replaceAll("_", " ");
    const health = device.health?.overall ? ` · HEALTH ${String(device.health.overall).toUpperCase()}` : "";
    card.querySelector("small").textContent = `${firmware.family || "unknown"} · ${version} · ${firmware.commandProtocol || "?"}/${firmware.telemetryProtocol || device.telemetryFormat || "?"}${health}`;
    card.querySelector("code").textContent = device.stablePath;
    card.addEventListener("click", () => {
      if (ui.hardwareDevices.selectedDeviceId !== device.id) {
        ui.hardwareDevices.selectedDeviceId = device.id;
        ui.hardwareDevices.lastRawText = "";
        clearEspBuild("Device changed. Compile again after reviewing the exact target.");
      }
      renderEspDevices();
    });
    return card;
  }));

  const deviceLabel = (device) => `${device.role.replaceAll("_", " ")} · ${device.tty} · ${device.pathLabel}`;
  replaceSelectOptions($("esp-device-select"), devices, ui.hardwareDevices.selectedDeviceId, deviceLabel);
  replaceSelectOptions($("esp-flash-device"), devices, ui.hardwareDevices.selectedDeviceId, deviceLabel);
  replaceSelectOptions(
    $("esp-firmware-source"),
    sources,
    ui.hardwareDevices.selectedSourceId,
    (source) => `${source.family} · ${source.interface || "serial"} · ${source.filename} · ${source.sha256.slice(0, 12)}`,
  );

  const device = selectedEspDevice();
  $("esp-serial-title").textContent = device
    ? `${device.role.replaceAll("_", " ")} · ${device.tty}`
    : "No serial device";
  const rawText = device?.rawTail?.length
    ? device.rawTail.map((line) => `${String(line.direction).startsWith("tx") ? ">" : "<"} ${line.text}`).join("\n")
    : "No complete serial lines received from this device yet.";
  const rawOutput = $("esp-raw-output");
  if (rawText !== ui.hardwareDevices.lastRawText) {
    const follow = rawOutput.scrollHeight - rawOutput.scrollTop - rawOutput.clientHeight < 50;
    rawOutput.textContent = rawText;
    ui.hardwareDevices.lastRawText = rawText;
    if (follow) rawOutput.scrollTop = rawOutput.scrollHeight;
  }
  $("esp-toolchain-state").textContent = payload.toolchain?.ready
    ? `READY · ${payload.toolchain.board} · ESP32 ${payload.toolchain.requiredEsp32Core} + UART FIX · FastAccelStepper ${payload.toolchain.libraryVersions?.FastAccelStepper}`
    : payload.toolchain?.available
      ? `DEPENDENCY BLOCKED · ${(payload.toolchain.issues || []).join(" · ")}`
      : "ARDUINO MISSING";
  const partition = payload.toolchain || {};
  $("esp-partition-state").textContent = partition.spiffsPreservedInPlace
    ? `SPIFFS PRESERVE · ${partition.partitionLayout} · ${partition.spiffsOffset} + ${partition.spiffsSize}`
    : `SPIFFS LAYOUT BLOCKED · ${(partition.issues || []).join(" · ")}`;
  renderEspCompileStatus();
  renderEspUploadInterlock();
}

async function pollEspDevices() {
  try {
    ui.hardwareDevices.latest = await requestJson("/api/hardware/devices");
    if (ui.view === "devices" || ui.view === "firmware") renderEspDevices();
  } catch (error) {
    const status = $("esp-device-status");
    status.className = "load-status error";
    status.textContent = "DEVICE SERVICE OFFLINE · RETRYING";
    status.title = `The dashboard backend is unreachable: ${error.message}`;
  }
}

function setupEspDevices() {
  const chooseDevice = (value) => {
    if (ui.hardwareDevices.selectedDeviceId !== value) {
      ui.hardwareDevices.selectedDeviceId = value;
      ui.hardwareDevices.lastRawText = "";
      clearEspBuild("Device changed. Compile again after reviewing the exact target.");
    }
    renderEspDevices();
  };
  $("esp-device-select").addEventListener("change", (event) => chooseDevice(event.target.value));
  $("esp-flash-device").addEventListener("change", (event) => chooseDevice(event.target.value));
  $("esp-firmware-source").addEventListener("change", (event) => {
    ui.hardwareDevices.selectedSourceId = event.target.value;
    clearEspBuild("Source changed. Compile the newly selected firmware before upload.");
    renderEspDevices();
  });
  $("esp-query-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const device = selectedEspDevice();
    if (!device) return;
    const command = $("esp-query-command").value;
    try {
      const result = await requestJson("/api/hardware/serial/query", {
        method: "POST",
        body: JSON.stringify({ deviceId: device.id, command }),
      });
      appendTerminal(`[serial] ${device.role} ${result.command} · ${result.bytes} bytes`, "ok");
      window.setTimeout(pollEspDevices, 150);
    } catch (error) {
      appendTerminal(`[serial] diagnostic query held · ${error.message}`, "err");
    }
  });
  $("esp-compile").addEventListener("click", async () => {
    const source = selectedFirmwareSource();
    if (!source || ui.hardwareDevices.busy) return;
    ui.hardwareDevices.busy = true;
    ui.hardwareDevices.compileState = "compiling";
    $("esp-compile").disabled = true;
    $("esp-build-output").textContent = `Compiling ${source.filename}\nSHA-256 ${source.sha256}\nBoard ${ui.hardwareDevices.latest?.toolchain?.board || "unknown"}\nSPIFFS preserve ${ui.hardwareDevices.latest?.toolchain?.spiffsOffset || "unknown"} + ${ui.hardwareDevices.latest?.toolchain?.spiffsSize || "unknown"}\n…`;
    renderEspCompileStatus();
    renderEspUploadInterlock();
    try {
      const build = await requestJson("/api/hardware/firmware/compile", {
        method: "POST",
        body: JSON.stringify({ sourceId: source.id }),
      });
      ui.hardwareDevices.build = build;
      ui.hardwareDevices.compileState = build.state === "passed" ? "passed" : "failed";
      $("esp-build-output").textContent = [
        `${build.state.toUpperCase()} · ${build.filename}`,
        `SHA-256 ${build.sha256}`,
        `BOARD ${build.board} · ${build.durationSeconds}s`,
        `PARTITIONS ${build.partitionLayout} · SPIFFS ${build.spiffsOffset} + ${build.spiffsSize} · ${build.binaryBytes} app bytes`,
        "",
        build.output,
      ].join("\n");
      appendTerminal(`[firmware] compile ${build.state} · ${build.filename} · ${build.sha256.slice(0, 12)}`, build.state === "passed" ? "ok" : "err");
    } catch (error) {
      clearEspBuild(`Compile failed\n${error.message}`);
      ui.hardwareDevices.compileState = "failed";
      appendTerminal(`[firmware] compile failed · ${error.message}`, "err");
    } finally {
      ui.hardwareDevices.busy = false;
      $("esp-compile").disabled = false;
      renderEspCompileStatus();
      renderEspUploadInterlock();
    }
  });
  ["esp-ack-supported", "esp-ack-power", "esp-ack-estop", "esp-flash-confirm"]
    .forEach((id) => $(id).addEventListener("input", renderEspUploadInterlock));
  $("esp-upload").addEventListener("click", async () => {
    const device = selectedEspDevice();
    const build = ui.hardwareDevices.build;
    if (!device || !build || ui.hardwareDevices.busy) return;
    ui.hardwareDevices.busy = true;
    renderEspUploadInterlock();
    $("esp-build-output").textContent += `\n\nUploading to ${device.stablePath}…`;
    try {
      const result = await requestJson("/api/hardware/firmware/upload", {
        method: "POST",
        body: JSON.stringify({
          buildId: build.id,
          deviceId: device.id,
          sourceSha256: build.sha256,
          robotSupported: $("esp-ack-supported").checked,
          actuatorPowerSafe: $("esp-ack-power").checked,
          estopReady: $("esp-ack-estop").checked,
          confirmation: $("esp-flash-confirm").value,
        }),
      });
      $("esp-build-output").textContent += `\nUPLOAD PASSED\n${result.output}`;
      appendTerminal(`[firmware] upload passed · ${device.role} · ${build.sha256.slice(0, 12)}`, "ok");
    } catch (error) {
      $("esp-build-output").textContent += `\nUPLOAD FAILED\n${error.message}`;
      appendTerminal(`[firmware] upload failed · ${device.role} · ${error.message}`, "err");
    } finally {
      ui.hardwareDevices.busy = false;
      renderEspUploadInterlock();
      pollEspDevices();
    }
  });
  pollEspDevices();
  window.setInterval(() => {
    if (ui.view === "devices" || ui.view === "firmware") pollEspDevices();
  }, 1000);
}

async function pollPhysicsRuntime() {
  try {
    const status = await requestJson("/api/physics/status");
    ui.physicsRuntime = status;
    const chip = $("physics-runtime-status");
    const sourceVerified = Boolean(status.sourceUsd?.verified);
    const physx = status.backends?.find(
      (backend) => backend.id === "isaac-physx-usd",
    );
    const mujoco = status.backends?.find(
      (backend) => backend.id === "mujoco-usd-proxy-v1",
    );
    chip.classList.toggle("verified", sourceVerified);
    chip.querySelector("span").textContent = sourceVerified
      ? "SOURCE USD VERIFIED"
      : "SOURCE USD NOT VERIFIED";
    chip.querySelector("b").textContent = [
      `${Number(status.groundTruth?.totalAuthoredMassKg || 0).toFixed(3)} KG`,
      "FORCE CONTACT",
      mujoco?.available ? "MUJOCO RL READY" : "MUJOCO OFFLINE",
      physx?.available ? "PHYSX READY" : "PHYSX OFFLINE",
    ].join(" · ");
  } catch (error) {
    const chip = $("physics-runtime-status");
    chip.querySelector("span").textContent = "PHYSICS STATUS OFFLINE";
    chip.querySelector("b").textContent = error.message;
  }
}

function renderRLStatus(status) {
  ui.latestRLStatus = status;
  const running = ["running", "stopping"].includes(status.state);
  $("rl-server-state").className = `load-status ${status.state === "error" ? "error" : running ? "loading" : "ok"}`;
  $("rl-server-state").innerHTML = "<span></span>";
  $("rl-server-state").append(document.createTextNode(
    status.state === "idle" ? "TRAINER READY" : `TRAINER ${status.state.toUpperCase()}`,
  ));
  $("rl-start").disabled = running;
  $("rl-stop").disabled = !running;
  $("sim-rl-start").disabled = running;
  $("sim-rl-stop").disabled = !running;
  $("global-training-stop").disabled = !running;
  const policyEpochsComplete = status.progress && status.config
    ? status.progress.update * status.config.epochs
    : 0;
  const policyEpochsTotal = status.config
    ? status.config.updates * status.config.epochs
    : 0;
  $("rl-progress-title").textContent = status.progress
    ? `Update ${status.progress.update} / ${status.progress.updates} · epoch ${policyEpochsComplete} / ${policyEpochsTotal}`
    : status.state === "complete" ? "Experiment complete" : "No experiment running";
  $("rl-experiment-id").textContent = status.experimentId?.slice(-8).toUpperCase() || "LOCAL";
  const progress = status.progress
    ? 100 * status.progress.update / Math.max(1, status.progress.updates)
    : status.state === "complete" ? 100 : 0;
  $("rl-progress-fill").style.width = `${progress}%`;
  const metric = status.progress || {};
  $("rl-reward").textContent = Number.isFinite(metric.reward) ? metric.reward.toFixed(3) : "—";
  $("rl-upright").textContent = Number.isFinite(metric.upright_percent) ? `${metric.upright_percent.toFixed(1)}%` : "—";
  $("rl-speed").textContent = Number.isFinite(metric.speed) ? `${metric.speed.toFixed(3)} m/s` : "—";
  $("rl-falls").textContent = Number.isFinite(metric.fall_percent) ? `${metric.fall_percent.toFixed(1)}%` : "—";
  $("rl-closure").textContent = Number.isFinite(metric.closure_max_m) ? `${(metric.closure_max_m * 1000).toFixed(3)} mm` : "—";
  $("rl-torso-tilt").textContent = Number.isFinite(metric.torso_tilt_degrees) ? `${metric.torso_tilt_degrees.toFixed(2)}°` : "—";
  $("rl-com-variation").textContent = Number.isFinite(metric.com_variation_m) ? `${(metric.com_variation_m * 1000).toFixed(2)} mm` : "—";
  $("rl-gait-symmetry").textContent = Number.isFinite(metric.gait_symmetry_percent) ? `${metric.gait_symmetry_percent.toFixed(1)}%` : "—";
  $("rl-leg-swing").textContent = Number.isFinite(metric.leg_swing_percent) ? `${metric.leg_swing_percent.toFixed(1)}%` : "—";
  $("rl-knee-contraction").textContent = Number.isFinite(metric.knee_contraction_degrees) ? `${metric.knee_contraction_degrees.toFixed(1)}°` : "—";
  $("rl-lateral-tilt").textContent = Number.isFinite(metric.lateral_tilt_degrees) ? `${metric.lateral_tilt_degrees.toFixed(2)}°` : "—";
  $("rl-dorsal-tilt").textContent = Number.isFinite(metric.dorsal_tilt_degrees) ? `${metric.dorsal_tilt_degrees.toFixed(2)}°` : "—";
  $("rl-turn-rate").textContent = Number.isFinite(metric.turn_rate) ? `${metric.turn_rate.toFixed(3)} rad/s` : "—";
  const strip = $("global-training-strip");
  const hasExperiment = Boolean(status.experimentId);
  strip.hidden = !hasExperiment;
  strip.className = `global-training-strip ${status.state}`;
  document.body.classList.toggle("training-active", hasExperiment);
  $("rl-rail-state").hidden = !hasExperiment;
  $("global-training-state").textContent = status.state.toUpperCase();
  $("global-training-id").textContent = status.experimentId?.slice(-8).toUpperCase() || "LOCAL";
  $("global-training-epoch").textContent = `EPOCH ${policyEpochsComplete} / ${policyEpochsTotal}`;
  $("global-training-fill").style.width = `${progress}%`;
  $("global-training-reward").textContent = Number.isFinite(metric.reward) ? metric.reward.toFixed(3) : "—";
  $("global-training-upright").textContent = Number.isFinite(metric.upright_percent) ? `${metric.upright_percent.toFixed(1)}%` : "—";
  $("global-training-phase").textContent = status.state === "complete"
    ? "POLICY READY"
    : metric.update ? `UPDATE ${metric.update}/${metric.updates}` : "INITIALIZING";
  const overlay = $("training-live-overlay");
  overlay.hidden = !ui.watchTraining || !status.experimentId;
  $("training-live-update").textContent = metric.update
    ? `UPDATE ${metric.update} / ${metric.updates} · EPOCH ${policyEpochsComplete} / ${policyEpochsTotal}`
    : "WAITING FOR FIRST UPDATE";
  $("training-live-reward").textContent = Number.isFinite(metric.reward) ? metric.reward.toFixed(3) : "—";
  $("training-live-upright").textContent = Number.isFinite(metric.upright_percent) ? `${metric.upright_percent.toFixed(1)}%` : "—";
  $("training-live-torso").textContent = Number.isFinite(metric.torso_tilt_degrees) ? `${metric.torso_tilt_degrees.toFixed(2)}°` : "—";
  $("training-live-com").textContent = Number.isFinite(metric.com_variation_m) ? `${(metric.com_variation_m * 1000).toFixed(2)} mm` : "—";
  $("training-live-speed").textContent = Number.isFinite(metric.speed) ? `${metric.speed.toFixed(3)} m/s` : "—";
  $("training-live-falls").textContent = Number.isFinite(metric.fall_percent) ? `${metric.fall_percent.toFixed(1)}%` : "—";

  if (status.policyUrl) {
    ui.latestPolicyUrl = status.policyUrl;
    const latestOption = $("scenario").querySelector('option[value="latest"]');
    if (latestOption) latestOption.disabled = status.state !== "complete";
  }
  const signature = JSON.stringify(status.events || []);
  if (signature !== ui.rlStatusSignature) {
    ui.rlStatusSignature = signature;
    const log = $("rl-log");
    log.innerHTML = "";
    for (const event of (status.events || []).slice(-50)) {
      const row = document.createElement("div");
      const label = document.createElement("span");
      const message = document.createTextNode(
        event.event === "progress"
          ? `update ${event.update}/${event.updates} · reward ${event.reward.toFixed(3)} · upright ${event.upright_percent.toFixed(1)}%`
          : event.event === "preview"
            ? `update ${event.update}/${event.updates} · score ${event.selectionScore?.toFixed(3) || "—"}${event.isBest ? " · new best" : ""}`
          : event.event === "complete"
            ? `policy exported · ${event.evaluation?.frameCount || 0} frames`
            : event.message || event.event || "event",
      );
      label.textContent = String(event.event || "LOG").toUpperCase();
      row.append(label, message);
      log.append(row);
    }
    if (!log.childElementCount) {
      const row = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = "READY";
      row.append(label, document.createTextNode("Configure a bounded local experiment or load the tracked reference policy."));
      log.append(row);
    }
    log.scrollTop = log.scrollHeight;
  }
  refreshLivePreview(status);
}

async function refreshLivePreview(status) {
  if (
    !ui.watchTraining
    || !ui.autoReplayTraining
    || ui.playbackFamily !== "classic"
    || ui.playbackMode !== "rl"
    || $("scenario").value !== "live"
    || !status.livePolicyUrl
    || !status.previewUpdate
    || ui.previewLoading
  ) return;
  const key = `${status.experimentId}:${status.previewUpdate}`;
  if (ui.previewLoadedKey === key) return;
  const generation = playbackSelectionGeneration;
  ui.previewLoading = true;
  try {
    const policy = await loadPolicy(
      `${status.livePolicyUrl}?update=${status.previewUpdate}`,
      `Live policy · update ${status.previewUpdate} / ${status.progress?.updates || "?"}`,
      { generation, loop: true },
    );
    if (
      !policy
      || !isCurrentPlaybackSelection(generation)
      || ui.playbackFamily !== "classic"
      || ui.playbackMode !== "rl"
      || $("scenario").value !== "live"
    ) return;
    ui.previewLoadedKey = key;
    ui.policyMode = true;
    ui.loadedPolicySource = "live";
    policyPlayer.loop = true;
    policyPlayer.play();
    $("rl-policy-title").textContent = `Live policy · update ${status.previewUpdate} / ${status.progress?.updates || "?"}`;
  } catch (error) {
    if (!isCurrentPlaybackSelection(generation)) return;
    appendTerminal(`[rl] live preview ${status.previewUpdate} unavailable: ${error.message}`, "warn");
  } finally {
    ui.previewLoading = false;
  }
}

async function pollRLStatus() {
  try {
    renderRLStatus(await requestJson("/api/rl/status"));
  } catch (error) {
    $("rl-server-state").className = "load-status error";
    $("rl-server-state").innerHTML = "<span></span>";
    $("rl-server-state").append(document.createTextNode(`TRAINER OFFLINE · ${error.message}`));
  }
}

async function loadPolicy(
  url,
  label,
  {
    play = false,
    loop = false,
    generation = playbackSelectionGeneration,
  } = {},
) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!isCurrentPlaybackSelection(generation)) return null;
    if (!response.ok) throw new Error(`policy HTTP ${response.status}`);
    const policy = await response.json();
    if (!isCurrentPlaybackSelection(generation)) return null;
    policyPlayer.setPolicy(policy, url);
    ui.policyMode = true;
    policyPlayer.loop = loop;
    $("rl-policy-title").textContent = label;
    if (play) policyPlayer.play();
    appendTerminal(`[rl] loaded ${policy.frames.length} policy frames from ${url}`, "ok");
    return policy;
  } catch (error) {
    if (!isCurrentPlaybackSelection(generation)) return null;
    appendTerminal(`[rl] policy load failed: ${error.message}`, "err");
    throw error;
  }
}

const rewardWeightDefaults = Object.freeze({
  ...RL_TRAINING_PROFILES["gentle-forward"].rewardWeights,
});

const rewardWeightInputSuffix = Object.freeze({
  torso: "torso",
  com: "com",
  gaitContact: "gait-contact",
  gaitSymmetry: "gait-symmetry",
  speed: "speed",
  legSwing: "leg-swing",
  height: "height",
  lateralTilt: "lateral-tilt",
  dorsalTilt: "dorsal-tilt",
  kneeContraction: "knee-contraction",
  armSwing: "arm-swing",
  energy: "energy",
  smoothness: "smoothness",
  closure: "closure",
  fall: "fall",
});

function readRewardWeights(prefix) {
  return Object.fromEntries(Object.entries(rewardWeightInputSuffix).map(([key, suffix]) => [
    key,
    Number($(`${prefix}-weight-${suffix}`).value),
  ]));
}

function writeRewardWeights(prefix, weights = rewardWeightDefaults) {
  for (const [key, suffix] of Object.entries(rewardWeightInputSuffix)) {
    $(`${prefix}-weight-${suffix}`).value = weights[key] ?? rewardWeightDefaults[key];
  }
}

function selectedRLSession() {
  return ui.rlSessions.find(
    (session) => session.experimentId === ui.selectedRLSessionId,
  ) || null;
}

function warmStartConfig() {
  const session = selectedRLSession();
  return $("rl-session-warm-start").checked && session?.checkpointPath
    ? { initCheckpoint: session.checkpointPath }
    : {};
}

function advancedRLConfig() {
  return {
    motionProfile: $("rl-motion-profile").value,
    updates: Number($("rl-updates").value),
    steps: Number($("rl-steps").value),
    envs: Number($("rl-envs").value),
    epochs: Number($("rl-epochs").value),
    batchSize: Number($("rl-batch-size").value),
    targetSpeed: Number($("rl-target-speed").value),
    targetTurnRate: Number($("rl-target-turn-rate").value),
    episodeSeconds: Number($("rl-episode-seconds").value),
    seed: Number($("rl-seed").value),
    device: $("rl-device").value,
    physicsBackend: $("rl-physics-backend").value,
    verticalConstraint: $("rl-vertical-constraint").checked,
    armSwing: $("rl-arm-swing").checked,
    rewardWeights: readRewardWeights("rl"),
    ...warmStartConfig(),
  };
}

function quickRLConfig() {
  return {
    ...advancedRLConfig(),
    updates: Number($("sim-rl-updates").value),
    epochs: Number($("sim-rl-epochs").value),
    targetSpeed: Number($("sim-rl-target-speed").value),
    targetTurnRate: Number($("sim-rl-target-turn-rate").value),
    motionProfile: $("sim-rl-motion-profile").value,
    device: $("sim-rl-device").value,
    verticalConstraint: $("sim-rl-vertical-constraint").checked,
    armSwing: $("sim-rl-arm-swing").checked,
    rewardWeights: readRewardWeights("sim-rl"),
  };
}

function selectRLSession(experimentId) {
  ui.selectedRLSessionId = experimentId || null;
  const session = selectedRLSession();
  document.querySelectorAll(".rl-session-card").forEach((card) => {
    const selected = card.dataset.experimentId === ui.selectedRLSessionId;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-selected", String(selected));
  });
  $("rl-session-copy").disabled = !session?.config;
  $("rl-session-replay").disabled = !session?.policyUrl;
  $("rl-session-warm-start").disabled = !session?.checkpointAvailable;
  if (!session?.checkpointAvailable) $("rl-session-warm-start").checked = false;
  const selection = $("rl-session-selection");
  selection.querySelector("b").textContent = session
    ? `RUN ${session.experimentId.slice(-8).toUpperCase()}`
    : "NEW RUN";
  selection.querySelector("span").textContent = session
    ? `${String(session.state).toUpperCase()} · select copy, replay, or warm-start`
    : "Edit the parameters above and start training. Existing runs are retained.";
}

function applyRLSessionConfig(session) {
  const config = session?.config;
  if (!config) return;
  const values = {
    "rl-updates": config.updates,
    "rl-steps": config.steps,
    "rl-envs": config.envs,
    "rl-epochs": config.epochs,
    "rl-batch-size": config.batchSize,
    "rl-target-speed": config.targetSpeed,
    "rl-target-turn-rate": config.targetTurnRate ?? 0,
    "rl-motion-profile": config.motionProfile || "custom",
    "rl-episode-seconds": config.episodeSeconds,
    "rl-seed": config.seed,
    "rl-device": config.device,
    "rl-physics-backend": config.physicsBackend || "teaching-plant-v2",
    "sim-rl-updates": config.updates,
    "sim-rl-epochs": config.epochs,
    "sim-rl-target-speed": config.targetSpeed,
    "sim-rl-target-turn-rate": config.targetTurnRate ?? 0,
    "sim-rl-motion-profile": config.motionProfile || "custom",
    "sim-rl-device": config.device,
  };
  for (const [id, value] of Object.entries(values)) {
    if (value != null && $(id)) $(id).value = String(value);
  }
  $("rl-vertical-constraint").checked = Boolean(config.verticalConstraint);
  $("rl-arm-swing").checked = Boolean(config.armSwing);
  $("sim-rl-vertical-constraint").checked = Boolean(config.verticalConstraint);
  $("sim-rl-arm-swing").checked = Boolean(config.armSwing);
  writeRewardWeights("rl", config.rewardWeights);
  writeRewardWeights("sim-rl", config.rewardWeights);
  appendTerminal(
    `[rl] copied exact parameters from ${session.experimentId}; history remains unchanged`,
    "ok",
  );
}

function formatSessionValue(value, digits = 2, suffix = "") {
  return Number.isFinite(Number(value))
    ? `${Number(value).toFixed(digits)}${suffix}`
    : "—";
}

function renderRLSessions(payload) {
  const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  ui.rlSessions = sessions;
  $("rl-session-count").textContent = `${sessions.length} RUN${sessions.length === 1 ? "" : "S"}`;
  const signature = JSON.stringify(sessions.map((session) => [
    session.experimentId,
    session.state,
    session.progress?.update,
    session.evaluation?.meanReward,
    session.checkpointAvailable,
  ]));
  if (signature !== ui.rlSessionsSignature) {
    ui.rlSessionsSignature = signature;
    const list = $("rl-session-list");
    list.innerHTML = "";
    for (const session of sessions) {
      const config = session.config || {};
      const evaluation = session.evaluation || {};
      const progress = session.progress || {};
      const card = document.createElement("button");
      card.type = "button";
      card.className = "rl-session-card";
      card.dataset.experimentId = session.experimentId;
      card.setAttribute("role", "option");
      card.innerHTML = `
        <div class="rl-session-card-head">
          <b>${session.experimentId.slice(-8).toUpperCase()}</b>
          <span class="rl-session-state ${session.state}">${String(session.state).toUpperCase()}</span>
        </div>
        <div class="rl-session-card-time">${new Date(session.createdAt).toLocaleString()}</div>
        <div class="rl-session-card-config">
          <span>UPDATES<b>${config.updates ?? "—"}</b></span>
          <span>EPOCHS<b>${config.epochs ?? "—"} / U</b></span>
          <span>TARGET<b>${formatSessionValue(config.targetSpeed, 2, " M/S")}</b></span>
          <span>TURN<b>${formatSessionValue(config.targetTurnRate, 2, " RAD/S")}</b></span>
        </div>
        <div class="rl-session-card-metrics">
          <span>REWARD<b>${formatSessionValue(evaluation.meanReward ?? progress.reward, 3)}</b></span>
          <span>UPRIGHT<b>${formatSessionValue(evaluation.uprightPercent ?? progress.upright_percent, 1, "%")}</b></span>
          <span>BACKEND<b>${config.physicsBackend === "mujoco-usd-proxy-v1" ? "MUJOCO" : config.physicsBackend === "teaching-plant-v2" ? "PREVIEW" : config.physicsBackend || "—"}</b></span>
        </div>`;
      card.addEventListener("click", () => selectRLSession(session.experimentId));
      list.appendChild(card);
    }
    if (!sessions.length) {
      const empty = document.createElement("div");
      empty.className = "rl-session-empty";
      empty.textContent = "No stored sessions yet.";
      list.appendChild(empty);
    }
  }
  if (
    ui.selectedRLSessionId
    && !sessions.some((session) => session.experimentId === ui.selectedRLSessionId)
  ) {
    ui.selectedRLSessionId = null;
  }
  if (!ui.selectedRLSessionId && payload.selectedExperimentId) {
    ui.selectedRLSessionId = payload.selectedExperimentId;
  }
  selectRLSession(ui.selectedRLSessionId);
  if (ui.playbackFamily === "classic" && ui.playbackMode === "rl") {
    populatePlaybackSources("rl", $("scenario").value);
  }
}

async function pollRLSessions() {
  try {
    renderRLSessions(await requestJson("/api/rl/sessions"));
  } catch (error) {
    appendTerminal(`[rl] session index unavailable: ${error.message}`, "warn");
  }
}

async function replaySelectedRLSession() {
  const session = selectedRLSession();
  if (!session?.policyUrl) return;
  const source = `session:${session.experimentId}`;
  const generation = beginPlaybackSelection();
  setPlaybackMode("rl", source);
  const configured = await configurePlaybackSource(source, { generation });
  if (!configured || !isCurrentPlaybackSelection(generation)) return;
  policyPlayer.loop = true;
  policyPlayer.seek(0);
  policyPlayer.play();
  switchView("sim");
  appendTerminal(`[rl] replaying stored run ${session.experimentId}`, "ok");
}

async function startRLTraining(config) {
  try {
    const status = await requestJson("/api/rl/train", {
      method: "POST",
      body: JSON.stringify(config),
    });
    ui.watchTraining = true;
    ui.previewLoadedKey = null;
    $("rl-auto-replay").checked = ui.autoReplayTraining;
    $("sim-rl-auto-replay").checked = ui.autoReplayTraining;
    setPlaybackMode("rl", "live");
    ui.policyMode = true;
    sim.scenario = "rl-policy";
    renderRLStatus(status);
    pollRLSessions();
    switchView("sim");
    appendTerminal(`[rl] experiment started · ${config.updates} updates × ${config.epochs} epochs · live USD replay armed`, "ok");
  } catch (error) {
    appendTerminal(`[rl] start rejected: ${error.message}`, "err");
  }
}

async function stopRLTraining() {
  try {
    renderRLStatus(await requestJson("/api/rl/stop", {
      method: "POST",
      body: "{}",
    }));
  } catch (error) {
    appendTerminal(`[rl] stop failed: ${error.message}`, "err");
  }
}

function watchTrainingOnSim() {
  ui.watchTraining = true;
  ui.autoReplayTraining = true;
  ui.previewLoadedKey = null;
  $("rl-auto-replay").checked = true;
  $("sim-rl-auto-replay").checked = true;
  setPlaybackMode("rl", "live");
  ui.policyMode = true;
  sim.scenario = "rl-policy";
  switchView("sim");
  pollRLStatus();
}

function applyRLTrainingProfile(profileId, { announce = true } = {}) {
  const profile = RL_TRAINING_PROFILES[profileId];
  if (!profile) return;
  const values = {
    "rl-motion-profile": profileId,
    "sim-rl-motion-profile": profileId,
    "rl-updates": profile.updates,
    "sim-rl-updates": profile.updates,
    "rl-steps": profile.steps,
    "rl-envs": profile.envs,
    "rl-epochs": profile.epochs,
    "sim-rl-epochs": profile.epochs,
    "rl-batch-size": profile.batchSize,
    "rl-target-speed": profile.targetSpeed,
    "sim-rl-target-speed": profile.targetSpeed,
    "rl-target-turn-rate": profile.targetTurnRate,
    "sim-rl-target-turn-rate": profile.targetTurnRate,
    "rl-episode-seconds": profile.episodeSeconds,
    "rl-device": profile.device,
    "sim-rl-device": profile.device,
    "rl-physics-backend": profile.physicsBackend,
  };
  for (const [id, value] of Object.entries(values)) {
    $(id).value = String(value);
  }
  $("rl-vertical-constraint").checked = profile.verticalConstraint;
  $("sim-rl-vertical-constraint").checked = profile.verticalConstraint;
  $("rl-arm-swing").checked = profile.armSwing;
  $("sim-rl-arm-swing").checked = profile.armSwing;
  writeRewardWeights("rl", profile.rewardWeights);
  writeRewardWeights("sim-rl", profile.rewardWeights);
  if (announce) {
    const radius = profile.targetTurnRate
      ? ` · nominal radius ${(profile.targetSpeed / Math.abs(profile.targetTurnRate)).toFixed(2)} m`
      : "";
    appendTerminal(
      `[rl] ${profile.label} profile loaded · ${profile.targetSpeed.toFixed(2)} m/s · ${profile.targetTurnRate.toFixed(2)} rad/s${radius}`,
      "ok",
    );
  }
}

function markRLProfileCustom(event) {
  if (
    event.target.id === "rl-motion-profile"
    || event.target.id === "sim-rl-motion-profile"
    || event.target.id === "sim-rl-auto-replay"
  ) return;
  $("rl-motion-profile").value = "custom";
  $("sim-rl-motion-profile").value = "custom";
}

function setupRLLab() {
  for (const [key, suffix] of Object.entries(rewardWeightInputSuffix)) {
    const advanced = $(`rl-weight-${suffix}`);
    const quick = $(`sim-rl-weight-${suffix}`);
    advanced.addEventListener("change", () => { quick.value = advanced.value; });
    quick.addEventListener("change", () => { advanced.value = quick.value; });
  }
  $("rl-reset-weights").addEventListener("click", () => {
    writeRewardWeights("rl");
    writeRewardWeights("sim-rl");
  });
  $("sim-rl-reset-weights").addEventListener("click", () => {
    writeRewardWeights("rl");
    writeRewardWeights("sim-rl");
  });
  for (const id of ["rl-motion-profile", "sim-rl-motion-profile"]) {
    $(id).addEventListener("change", (event) => {
      const profileId = event.target.value;
      if (profileId === "custom") {
        $("rl-motion-profile").value = "custom";
        $("sim-rl-motion-profile").value = "custom";
        return;
      }
      applyRLTrainingProfile(profileId);
    });
  }
  $("rl-form").addEventListener("input", markRLProfileCustom);
  $("sim-training-panel").addEventListener("input", markRLProfileCustom);
  $("rl-session-new").addEventListener("click", () => {
    ui.selectedRLSessionId = null;
    $("rl-session-warm-start").checked = false;
    selectRLSession(null);
    appendTerminal("[rl] new run armed; stored sessions were not changed", "ok");
  });
  $("rl-session-copy").addEventListener("click", () => {
    applyRLSessionConfig(selectedRLSession());
  });
  $("rl-session-replay").addEventListener("click", () => {
    replaySelectedRLSession().catch((error) => {
      appendTerminal(`[rl] session replay failed: ${error.message}`, "err");
    });
  });
  $("rl-form").addEventListener("submit", (event) => {
    event.preventDefault();
    ui.autoReplayTraining = $("rl-auto-replay").checked;
    startRLTraining(advancedRLConfig());
  });
  $("sim-training-toggle").addEventListener("click", () => {
    const panel = $("sim-training-panel");
    panel.hidden = !panel.hidden;
    $("sim-training-toggle").setAttribute("aria-expanded", String(!panel.hidden));
    $("sim-training-toggle").textContent = panel.hidden ? "TRAIN RL" : "CLOSE TRAINING";
  });
  $("sim-training-panel").addEventListener("submit", (event) => {
    event.preventDefault();
    ui.autoReplayTraining = $("sim-rl-auto-replay").checked;
    startRLTraining(quickRLConfig());
  });
  $("rl-stop").addEventListener("click", stopRLTraining);
  $("sim-rl-stop").addEventListener("click", stopRLTraining);
  $("global-training-stop").addEventListener("click", stopRLTraining);
  $("sim-rl-advanced").addEventListener("click", () => switchView("rl"));
  $("global-training-lab").addEventListener("click", () => switchView("rl"));
  $("global-training-live").addEventListener("click", watchTrainingOnSim);
  $("rl-open-sim").addEventListener("click", () => {
    setPlaybackMode("rl", policyPlayer.policy ? $("scenario").value : "reference");
    switchView("sim");
    if (!policyPlayer.policy) configurePlaybackSource("reference");
  });
  for (const id of ["rl-auto-replay", "sim-rl-auto-replay"]) {
    $(id).addEventListener("change", (event) => {
      ui.autoReplayTraining = event.target.checked;
      $("rl-auto-replay").checked = ui.autoReplayTraining;
      $("sim-rl-auto-replay").checked = ui.autoReplayTraining;
    });
  }
  $("rl-timeline").addEventListener("input", (event) => {
    ui.policyMode = true;
    policyPlayer.seek(Number(event.target.value));
  });
  applyRLTrainingProfile("gentle-forward", { announce: false });
  pollRLStatus();
  pollRLSessions();
  window.setInterval(() => {
    if (ui.view === "rl" || ui.watchTraining) pollRLStatus();
  }, 800);
  window.setInterval(() => {
    if (ui.view === "rl") pollRLSessions();
  }, 3000);
}

function drawScope() {
  const canvas = $("scope-canvas");
  if (!canvas.dropbearScopeSize) {
    const rect = canvas.getBoundingClientRect();
    canvas.dropbearScopeSize = { width: rect.width, height: rect.height };
    canvas.dropbearScopeObserver = new ResizeObserver(([entry]) => {
      canvas.dropbearScopeSize = {
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      };
    });
    canvas.dropbearScopeObserver.observe(canvas);
  }
  const rect = canvas.dropbearScopeSize;
  const ratio = Math.min(devicePixelRatio, 2);
  const width = Math.max(300, Math.round(rect.width * ratio));
  const height = Math.max(150, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#080d13";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#152430";
  ctx.lineWidth = 1;
  for (let x = 0; x <= width; x += width / 12) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
  for (let y = 0; y <= height; y += height / 6) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
  const history = ui.scopeHistory;
  if (history.length < 2) return;
  const t0 = history[0].t;
  const tSpan = Math.max(0.001, history.at(-1).t - t0);
  const plot = (field, color, min, max) => {
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = ratio * 1.25;
    history.forEach((sample, index) => {
      const x = (sample.t - t0) / tSpan * width;
      const y = height - (sample[field] - min) / (max - min) * height;
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  plot("desired", "#fbbf24", 90, 270);
  plot("angle", "#22d3ee", 90, 270);
  plot("torque", "#fb7185", -3.2, 3.2);
}

function renderLive() {
  const target = selectedJoint();
  const selectedArm = armMotorStates.find((entry) => entry.id === ui.selectedArmMotorId);
  const runningButton = $("sim-toggle");
  const observingHardware = ui.hardwareObservation.active;
  document.body.classList.toggle("hardware-observing", observingHardware);
  const effectivePlaying = !observingHardware && (ui.policyMode ? policyPlayer.playing : sim.playMode);
  const hardwareFreshSides = ["left", "right"].filter(
    (side) => ui.hardwareObservation.latest?.sides?.[side]?.fresh === true,
  ).length;
  const poseNow = performance.now();
  const poseDt = Math.max(0, Math.min(0.08, (poseNow - ui.lastRobotFrameAt) / 1000));
  ui.lastRobotFrameAt = poseNow;
  robot.setJointStates(
    sim.joints,
    ui.axisCategory === "leg" ? ui.selectedJointId : null,
    armMotorStates,
    poseDt,
  );
  sim.setFootContactState(robot.groundContact);
  if (observingHardware && poseNow - ui.lastLiveDomAt < 200) return;
  ui.lastLiveDomAt = poseNow;
  runningButton.classList.toggle("stop", effectivePlaying);
  runningButton.setAttribute("aria-pressed", String(effectivePlaying));
  runningButton.disabled = observingHardware;
  runningButton.innerHTML = effectivePlaying ? '<span class="run-icon">■</span> STOP' : '<span class="run-icon">▶</span> PLAY';
  $("system-state").className = `system-state ${observingHardware ? "observing" : effectivePlaying ? "running" : "paused"}`;
  $("system-state").innerHTML = `<span></span>${observingHardware ? (hardwareFreshSides ? `READ ONLY · LIVE ${hardwareFreshSides}/2` : "READ ONLY · STALE") : effectivePlaying ? "CONTROL ACTIVE" : "GUARDED PAUSE"}`;
  $("sim-time").textContent = `${sim.time.toFixed(2)} s`;
  $("control-state").textContent = observingHardware ? "OBSERVE" : effectivePlaying ? sim.scenario.toUpperCase() : "STOP";
  $("can-load").textContent = `${sim.canUtilization.toFixed(1)}%`;
  $("sel-angle-label").textContent = observingHardware && ui.axisCategory === "leg" ? "MODEL ANGLE" : "ANGLE";
  $("sel-velocity-label").textContent = observingHardware && ui.axisCategory === "leg" ? "CAN MOTOR" : "VELOCITY";
  $("sel-torque-label").textContent = observingHardware && ui.axisCategory === "leg" ? "AS5600" : "TORQUE";
  $("sel-sensor-label").textContent = observingHardware && ui.axisCategory === "leg" ? "SIGNAL STATE" : "SENSOR";
  $("sel-angle").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.angleDeg || 0).toFixed(1)}°`
    : observingHardware
      ? target.observationModelApplied
        ? `${target.observationMechanismDeg.toFixed(1)}° · ${observationPositionLabel(target.observationPositionSource)}`
        : "HELD · NO QUALIFIED SOURCE"
    : target.observationValid
      ? `${target.observationRawDeg.toFixed(1)}° ${observationPositionLabel(target.observationPositionSource)} · ${target.observationModelApplied ? `${target.observationZeroedDeg.toFixed(1)}° zero · ${target.observationMechanismDeg.toFixed(1)}° model` : "MODEL HELD"}`
      : `${(target.angle - 180).toFixed(1)}°`;
  $("sel-velocity").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.velocityDegS || 0).toFixed(1)}°/s`
    : observingHardware
      ? Number.isFinite(target.observationMotorDeg)
        ? `${target.observationMotorDeg.toFixed(2)}° · DIRECT`
        : "NO 0x92 REPLY"
    : `${target.velocity.toFixed(1)}°/s`;
  $("sel-torque").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.torqueNm || 0).toFixed(2)} N·m`
    : observingHardware
      ? target.sensorPin == null
        ? "NOT FITTED"
        : Number.isFinite(target.observationExternalDeg)
          ? `${target.observationExternalDeg.toFixed(1)}° · ${target.observationExternalFresh ? "FRESH" : "STALE"}`
          : "NO PWM"
    : `${target.torque.toFixed(2)} N·m`;
  $("sel-sensor").textContent = ui.axisCategory === "arm"
    ? "AUX · CAN UNMAPPED"
    : target.sensorPin == null
      ? observingHardware && target.observationValid
        ? `LIVE ${observationPositionLabel(target.observationPositionSource)} · ${Number(target.observationAgeMs || 0).toFixed(0)} ms`
        : "NO ANALOG"
      : observingHardware
        ? target.observationValid
        ? `GPIO${target.sensorPin} · CAN ${Number.isFinite(target.observationMotorDeg) ? "FRESH" : "NO REPLY"} · PWM ${target.observationExternalFresh ? "FRESH" : "STALE"} · ${Number(target.observationAgeMs || 0).toFixed(0)} ms`
          : `GPIO${target.sensorPin} · UNAVAILABLE`
        : `GPIO${target.sensorPin} · ${target.adc}`;
  $("fault-sensor").textContent = ui.axisCategory === "arm"
    ? "NO SENSOR MAP"
    : target.sensorStuck ? "RELEASE SENSOR" : "FREEZE SENSOR";
  $("fault-thermal").textContent = ui.axisCategory === "arm"
    ? "NO THERMAL MAP"
    : target.temperature > 80 ? "CLEAR THERMAL" : "THERMAL FAULT";
  $("fault-sensor").disabled = ui.axisCategory === "arm";
  $("fault-thermal").disabled = ui.axisCategory === "arm";

  for (const card of document.querySelectorAll(".joint-card[data-joint-id]")) {
    const joint = sim.getJoint(Number(card.dataset.jointId));
    const motorAvailable = Number.isFinite(joint.observationMotorDeg);
    const sensorAvailable = Number.isFinite(joint.observationExternalDeg);
    const motorOutput = card.querySelector('[data-field="motor-angle"]');
    const sensorOutput = card.querySelector('[data-field="sensor-angle"]');
    const motorDot = card.querySelector('[data-field="motor-dot"]');
    const sensorDot = card.querySelector('[data-field="sensor-dot"]');
    motorOutput.textContent = observingHardware
      ? motorAvailable ? `${joint.observationMotorDeg.toFixed(2)}° · FRESH` : "— · NO REPLY"
      : `${(joint.angle - 180).toFixed(1)}° · SIM`;
    sensorOutput.textContent = observingHardware
      ? joint.sensorPin == null ? "— · NOT FITTED"
        : sensorAvailable
          ? `${joint.observationExternalDeg.toFixed(1)}° · ${joint.observationExternalFresh ? "FRESH" : "STALE"}`
          : "— · NO PWM"
      : joint.sensorPin == null ? "— · NOT FITTED" : `GPIO${joint.sensorPin} · SIM`;
    motorDot.className = `joint-dot ${motorAvailable ? "observed" : observingHardware ? "warn" : ""}`;
    sensorDot.className = `joint-dot ${joint.observationExternalFresh ? "observed" : sensorAvailable || observingHardware ? "warn" : ""}`;
    card.querySelector('[data-field="angle"]').textContent = observingHardware && !joint.observationValid
      ? "HELD · NO QUALIFIED SOURCE"
      : joint.observationValid
        ? joint.observationModelApplied
          ? `${joint.observationMechanismDeg.toFixed(1)}° · ${observationPositionLabel(joint.observationPositionSource)}`
          : `HELD · ${observationPositionLabel(joint.observationPositionSource)}`
        : `${(joint.angle - 180).toFixed(1)}°`;
  }
  if (ui.motorCategory === "legs") {
    $("motor-map-title").textContent = observingHardware
      ? "Live leg feedback · direct channels"
      : "Installed leg motor map";
  }

  for (const side of ["left", "right"]) {
    const leg = robot.legTelemetry[side];
    const gait = sim.gait[side];
    const footHeight = $(`${side}-foot-height`);
    $(`${side}-gait-phase`).textContent = effectivePlaying && ["walk", "rl-policy"].includes(sim.scenario)
      ? gait.mode.toUpperCase()
      : "HOLD";
    footHeight.textContent = `${signed(leg.footHeightMm, 0)} mm`;
    footHeight.classList.toggle("lift", leg.footHeightMm > 15);
    const contactLabel = leg.heelContact && leg.toeContact
      ? "HEEL + TOE"
      : leg.heelContact ? "HEEL" : leg.toeContact ? "TOE" : "OPEN";
    const contactOutput = $(`${side}-foot-contact`);
    contactOutput.textContent = contactLabel;
    contactOutput.classList.toggle("contact", leg.contact);
    $(`${side}-foot-load`).textContent = `${leg.heelLoadKg.toFixed(1)} / ${leg.toeLoadKg.toFixed(1)} kg`;
    $(`${side}-ankle-angle`).textContent = `${signed(leg.ankleDeg)}°`;
    $(`${side}-calf-pair`).textContent = `${signed(leg.outerCalfDeg - 180)}° / ${signed(leg.innerCalfDeg - 180)}°`;
  }
  const closureText = $("closure-status-text");
  if (closureText && robot.ready) {
    const guide = robot.verticalConstraintEnabled ? "Z GUIDE" : "FREE ROOT";
    const normalForce = Number(robot.groundContact.normalForceN);
    const force = Number.isFinite(normalForce) ? ` · N ${normalForce.toFixed(0)} N` : "";
    closureText.textContent = `${guide} ${signed(robot.groundContact.offsetZ * 1000, 0)} mm${force} · LEG ${robot.legClosureResidualMm.toFixed(3)} mm · ARM ${robot.armClosureResidualMm.toFixed(3)} mm · MAX ${robot.closureResidualMm.toFixed(3)} mm`;
  }
  $("root-z-offset").textContent = `${signed(robot.groundContact.offsetZ * 1000, 0)} mm`;
  drawScope();
  board.setActivity({
    running: sim.running,
    playMode: sim.playMode,
    loadCellsEnabled: sim.loadCellsEnabled,
    time: sim.time,
  });
  if (!ui.cadManual) {
    const outputRotation = ui.axisCategory === "arm"
      ? (selectedArm?.angleDeg || 0)
      : target.angle - 180;
    cad.setJointAngle(outputRotation);
    $("cad-angle").value = String(Math.max(-180, Math.min(180, outputRotation)));
    $("cad-angle-output").textContent = `${signed(outputRotation)}°`;
  }
  $("csv-output").textContent = sim.controllers[ui.consoleController].csv;
  $("fault-can").textContent = sim.faults.canDrop ? "RESTORE CAN" : "DROP CAN";
  $("fault-serial").textContent = sim.faults.serialDrop ? "RESTORE SERIAL" : "DROP SERIAL";
  $("fault-imu").textContent = sim.faults.imuDrift ? "CLEAR IMU DRIFT" : "DRIFT IMU";
  $("torque-target").disabled = observingHardware;
  $("impedance-toggle").disabled = observingHardware;
  renderHardwareObservationState();
  renderHardwareControlState();
}

function frame(now) {
  const dt = Math.min(0.05, (now - ui.lastFrame) / 1000);
  ui.lastFrame = now;
  if (ui.hardwareObservation.active) {
    // The passive reader owns actual joint state while selected. Never advance
    // the synthetic plant underneath a stale or fresh hardware sample.
  } else if (ui.policyMode) policyPlayer.update(dt);
  else sim.step(dt);
  if (now - ui.scopeSampleAt > 38) {
    const target = selectedJoint();
    ui.scopeHistory.push({ t: sim.time, angle: target.angle, desired: target.desiredPosition, torque: target.torque });
    while (ui.scopeHistory.length > 260) ui.scopeHistory.shift();
    ui.scopeSampleAt = now;
  }
  if (softwareRenderer || now - ui.lastRender > 65) {
    renderLive();
    ui.lastRender = now;
  }
  scheduleFrame();
}

function scheduleFrame() {
  if (softwareRenderer) window.setTimeout(() => frame(performance.now()), softwareFrameIntervalMs);
  else requestAnimationFrame(frame);
}

window.addEventListener("dropbear:gr00t-runtime", (event) => {
  const next = event.detail || {};
  const poseReady = Boolean(next.decodedG1PoseReady);
  const tokenReady = Boolean(next.nvidiaTokenReady);
  const changed = poseReady !== ui.gr00tAvailability.decodedG1PoseReady
    || tokenReady !== ui.gr00tAvailability.nvidiaTokenReady;
  ui.gr00tAvailability.decodedG1PoseReady = poseReady;
  ui.gr00tAvailability.nvidiaTokenReady = tokenReady;
  if (changed && ui.playbackFamily === "gr00t") {
    const selectedSource = GR00T_WBC_PLAYBACK_SOURCES.find(
      (source) => source.value === $("scenario").value,
    );
    if (
      !selectedSource
      || ui.gr00tAvailability[selectedSource.readiness] !== true
    ) {
      beginPlaybackSelection();
    }
    populatePlaybackSources("rl", ui.playbackSelections.gr00t);
  }
});

setupNavigation();
makeJointCards();
setupMotorCategories();
setupSimControls();
setupHardwareControls();
setupEspDevices();
setupCadControls();
setupBoardControls();
setupFirmware();
window.addEventListener("dropbear:prompt-plan", async (event) => {
  const plan = event.detail || {};
  const primitive = String(plan.primitive || "").trim().toLowerCase();
  const targetTurnRate = Number(plan.target_turn_rate_rps);
  const scenario = GR00T_PROMPT_PREVIEW_PRESETS[primitive] || null;
  const unavailableReason = !Number.isFinite(targetTurnRate)
    ? "the plan has an invalid turn-rate target"
    : Math.abs(targetTurnRate) > GR00T_PROMPT_PREVIEW_TURN_EPSILON_RPS
      ? `the browser preset runner cannot apply ${targetTurnRate.toFixed(2)} rad/s turning`
      : !scenario
        ? `the browser preset runner has no ${primitive || "unknown"} reference`
        : null;
  if (unavailableReason) {
    const result = $("gr00t-prompt-result");
    result?.querySelector(".gr00t-preview-unavailable")?.remove();
    if (result) {
      const notice = document.createElement("p");
      notice.className = "gr00t-preview-unavailable";
      notice.textContent = `PREVIEW UNAVAILABLE · ${unavailableReason}. The plan was not played.`;
      result.append(notice);
    }
    appendTerminal(`[gr00t] no browser preset matches ${primitive || "unknown"} · ${unavailableReason}`, "warn");
    return;
  }
  try {
    setPlaybackMode("preset", scenario);
    await configurePlaybackSource(scenario);
    sim.setPlay(true);
    switchView("sim");
    appendTerminal(
      `[gr00t] browser preset preview · ${primitive} → ${scenario} · `
      + "fixed-rate kinematic reference; planner speed is metadata only",
      "ok",
    );
  } catch (error) {
    appendTerminal(`[gr00t] prompt preview failed: ${error.message}`, "err");
  }
});
window.addEventListener("dropbear:retargeted-pose", (event) => {
  const payload = event.detail || {};
  const responseFrames = Array.isArray(payload.frames)
    ? payload.frames
    : [payload];
  if (payload.hardwareAuthorized !== false || !responseFrames.length) {
    appendTerminal("[gr00t] rejected pose without a hardware-locked contract", "err");
    return;
  }
  const frames = [];
  for (const frame of responseFrames) {
    if (frame.retarget?.hardwareAuthorized !== false) {
      appendTerminal("[gr00t] rejected frame without a hardware-locked contract", "err");
      return;
    }
    const target = frame.retarget?.target || {};
    const order = target.jointOrder;
    const positions = target.positionsRad;
    const valid = Array.isArray(order)
      && Array.isArray(positions)
      && order.length === DROPBEAR_RETARGET_ACTION_ORDER.length
      && positions.length === DROPBEAR_RETARGET_ACTION_ORDER.length
      && order.every(
        (name, index) => name === DROPBEAR_RETARGET_ACTION_ORDER[index],
      )
      && positions.every(Number.isFinite);
    if (!valid) {
      appendTerminal("[gr00t] rejected malformed Dropbear retarget frame", "err");
      return;
    }
    const armTargets = [];
    for (let index = 12; index < order.length; index += 1) {
      const id = `arm-${order[index].replaceAll("_", "-")}`;
      const state = armMotorStates.find((candidate) => candidate.id === id);
      if (!state) {
        appendTerminal(`[gr00t] no browser motor binding for ${order[index]}`, "err");
        return;
      }
      armTargets.push({ state, position: positions[index] });
    }
    frames.push({ order, positions, armTargets });
  }
  for (let index = 0; index < sim.joints.length; index += 1) {
    const state = sim.joints[index];
    const expected = `${state.side}_${state.key}`;
    if (DROPBEAR_RETARGET_ACTION_ORDER[index] !== expected) {
      appendTerminal(`[gr00t] action-order mismatch at ${index}: ${expected}`, "err");
      return;
    }
  }
  const generation = beginPlaybackSelection();
  policyPlayer.pause();
  ui.policyMode = false;
  ui.loadedPolicySource = null;
  ui.watchTraining = false;
  if (
    GR00T_WBC_PLAYBACK_SOURCES.some(
      (source) => source.value === payload.playbackSourceId,
    )
  ) {
    setPlaybackFamily("gr00t", payload.playbackSourceId);
  } else {
    setPlaybackMode("preset", "manual");
  }
  sim.setScenario("manual");
  sim.setPlay(false);
  robot.setVerticalConstraintEnabled($("vertical-constraint").checked);
  switchView("sim");

  const applyFrame = ({ positions, armTargets }) => {
    for (let index = 0; index < sim.joints.length; index += 1) {
      const state = sim.joints[index];
      const angle = Math.min(
        state.maxAngle,
        Math.max(state.minAngle, 180 + positions[index] * RAD_TO_DEG),
      );
      if (!sim.setJointTarget(state.id, angle, true)) {
        state.desiredPosition = angle;
      }
      state.angle = state.desiredPosition;
      state.velocity = 0;
    }
    for (const { state, position } of armTargets) {
      state.angleDeg = position * RAD_TO_DEG;
      state.velocityDegS = 0;
      state.torqueNm = 0;
    }
    renderLive();
  };

  if (frames.length === 1) {
    applyFrame(frames[0]);
    appendTerminal(
      `[gr00t] ${payload.provenance?.inputClass || "decoded-g1-pose"} → `
      + "22 Dropbear USD motor targets · static SIL preview · hardware locked",
      "ok",
    );
    return;
  }
  const startedAt = performance.now();
  const playFrame = (index) => {
    if (!isCurrentPlaybackSelection(generation)) return;
    applyFrame(frames[index]);
    if (index + 1 >= frames.length) {
      appendTerminal(
        `[gr00t] ${frames.length}-frame q22 horizon complete · nominal 20 ms USD preview · `
        + "hardware locked",
        "ok",
      );
      return;
    }
    const nextDeadline = startedAt + (index + 1) * 20;
    window.setTimeout(
      () => playFrame(index + 1),
      Math.max(0, nextDeadline - performance.now()),
    );
  };
  appendTerminal(
    `[gr00t] ${frames.length}-frame q22 horizon · starting nominal 20 ms USD preview`,
    "ok",
  );
  playFrame(0);
});
pollPhysicsRuntime();
selectJoint(0x141);
renderLive();
scheduleFrame();

window.dropbearTwin = {
  sim,
  robot,
  board,
  cad,
  switchView,
  armMotorStates,
  armMotorBindings: DROPBEAR_ARM_MOTOR_BINDINGS,
  policyPlayer,
  source: DROPBEAR_SOURCE,
  usdSource: DROPBEAR_USD_SOURCE,
  cadEvidence: CAD_EVIDENCE,
  get physicsRuntime() { return ui.physicsRuntime; },
};
