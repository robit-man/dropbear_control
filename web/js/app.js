import {
  CONTROLLER_PINS,
  DROPBEAR_SOURCE,
  DropbearSim,
  JOINT_DEFINITIONS,
  TASKS,
} from "./dropbear.js";
import { Board3D } from "./board_3d.js";
import { CAD_EVIDENCE, CadViewer } from "./cad_viewer.js";
import {
  DROPBEAR_ARM_MOTOR_BINDINGS,
  DROPBEAR_USD_SOURCE,
  dropbearArmMotorBinding,
  dropbearUsdBinding,
} from "./dropbear_usd.js";
import { RLPolicyPlayer } from "./rl_policy.js";
import { Robot3D } from "./robot_3d.js";
import {
  GR00T_WBC_PLAYBACK_SOURCES,
  cancelGr00tWbcPlayback,
  playGr00tWbcSource,
  setupGr00tLab,
  waitForGr00tWbcPlaybackIdle,
} from "./gr00t_lab.js";

const $ = (id) => document.getElementById(id);
const RAD_TO_DEG = 180 / Math.PI;
const sim = new DropbearSim();
const PRESET_SOURCES = Object.freeze([
  { value: "neutral", label: "Neutral hold" },
  { value: "walk", label: "Alternating step" },
  { value: "balance", label: "Balance transfer" },
  { value: "sensor-sweep", label: "Sensor sweep" },
  { value: "manual", label: "Manual torque" },
]);
const RL_SOURCES = Object.freeze([
  { value: "reference", label: "Tracked PPO reference" },
  { value: "authored", label: "Authored walking baseline" },
  { value: "latest", label: "Latest completed local policy" },
  { value: "live", label: "Live policy from active training" },
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
};

function selectedJoint() {
  return sim.getJoint(ui.selectedJointId) || sim.joints[0];
}

function signed(value, digits = 1) {
  const number = Number(value) || 0;
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}`;
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

const board = new Board3D($("board-canvas"), {
  onPin: (data) => {
    $("pin-title").textContent = data.component || "Board component";
    $("pin-detail").textContent = data.detail || "ESP32 DevKit V1 reference component.";
    document.querySelectorAll(".pin-row").forEach((row) => {
      row.classList.toggle("active", Number(row.dataset.gpio) === Number(data.gpio));
    });
  },
});

const cad = new CadViewer($("cad-canvas"), {
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
});

const robot = new Robot3D($("robot-canvas"), {
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
});

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
  if (workspace) {
    workspace.scrollTop = 0;
    requestAnimationFrame(() => { workspace.scrollTop = 0; });
  }
  if (name === "sim") setTimeout(() => robot.resize(), 20);
  if (name === "cad") setTimeout(() => { cad.resize(); cad.fit(); }, 20);
  if (name === "controller") setTimeout(() => board.resize(), 20);
}

function setupNavigation() {
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewTarget));
  });
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
    const button = document.createElement("button");
    button.type = "button";
    button.className = "joint-card";
    button.dataset.jointId = String(definition.id);
    button.style.setProperty("--side-color", definition.side === "left" ? "var(--left)" : "var(--right)");
    button.innerHTML = `
      <div class="joint-card-top">
        <b>${definition.label}</b>
        <code>${definition.canId}</code>
      </div>
      <div class="joint-card-state">
        <span>POSITION<em data-field="angle">180.0°</em></span>
        <span><i class="joint-dot"></i>TORQUE<em data-field="torque">0.00 N·m</em></span>
      </div>`;
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
  $("selected-can").textContent = target.canId;
  const usdBinding = dropbearUsdBinding(target.id);
  const cadModelKey = usdBinding?.motor === "RMD-X8" ? "x8-pro" : "x10-s2";
  cad.setModel(cadModelKey);
  $("cad-model").value = cadModelKey;
  $("selected-usd").textContent = usdBinding
    ? `USD ${usdBinding.usdJoint}${usdBinding.closure ? " · CLOSURE" : " · FK"}`
    : "USD BINDING UNRESOLVED";
  $("cad-joint-name").textContent = target.label;
  $("position-target").value = String(Math.round(target.desiredPosition));
  $("position-target").min = String(target.minAngle);
  $("position-target").max = String(target.maxAngle);
  $("position-output").textContent = `${Math.round(target.desiredPosition)}°`;
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
  modeButton.textContent = ui.playbackMode === "rl" ? "TRAINED" : "PRESET";
  modeButton.setAttribute("aria-pressed", String(ui.playbackMode === "rl"));
  const familyButton = $("playback-family");
  familyButton.dataset.family = ui.playbackFamily;
  familyButton.textContent = ui.playbackFamily === "gr00t" ? "GR00T" : "CLASSIC";
  familyButton.setAttribute("aria-pressed", String(ui.playbackFamily === "gr00t"));
}

function populatePlaybackSources(mode, selectedValue = null) {
  const sessionSources = ui.rlSessions
    .filter((session) => session.policyUrl)
    .map((session) => ({
      value: `session:${session.experimentId}`,
      label: `Run ${session.experimentId.slice(-8).toUpperCase()}`,
    }));
  const sources = ui.playbackFamily === "gr00t"
    ? GR00T_WBC_PLAYBACK_SOURCES
    : mode === "rl"
      ? [...RL_SOURCES, ...sessionSources]
      : PRESET_SOURCES;
  const select = $("scenario");
  select.innerHTML = "";
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source.value;
    option.textContent = source.label;
    if (
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
      ? "reference"
      : "neutral";
  select.value = sources.some((source) => source.value === selectedValue) ? selectedValue : fallback;
  const selectionKey = ui.playbackFamily === "gr00t" ? "gr00t" : mode;
  ui.playbackSelections[selectionKey] = select.value || fallback;
  $("playback-source-label").textContent = ui.playbackFamily === "gr00t"
    ? "GR00T WBC SOURCE"
    : mode === "rl"
      ? "POLICY"
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
  if (value === "reference") {
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
  const savedResolution = Number(localStorage.getItem("dropbear-usd-resolution") || 100);
  const resolutionPercent = Math.max(50, Math.min(200, savedResolution));
  $("usd-resolution").value = String(resolutionPercent);
  $("usd-resolution-output").textContent = `${resolutionPercent}%`;
  robot.setResolutionScale(resolutionPercent / 100);
  $("usd-resolution").addEventListener("input", (event) => {
    const percent = Number(event.target.value);
    robot.setResolutionScale(percent / 100);
    $("usd-resolution-output").textContent = `${percent}%`;
    localStorage.setItem("dropbear-usd-resolution", String(percent));
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
    sim.setJointTarget(target.id, value, true);
    $("impedance-toggle").checked = target.impedanceEnabled;
    $("position-output").textContent = `${value.toFixed(0)}°`;
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
  appendTerminal("Guarded pause active. Source firmware would set playMode=true during setup.", "warn");
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
  window.setInterval(pollRLStatus, 800);
  window.setInterval(pollRLSessions, 3000);
}

function drawScope() {
  const canvas = $("scope-canvas");
  const rect = canvas.getBoundingClientRect();
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
  const effectivePlaying = ui.policyMode ? policyPlayer.playing : sim.playMode;
  runningButton.classList.toggle("stop", effectivePlaying);
  runningButton.setAttribute("aria-pressed", String(effectivePlaying));
  runningButton.innerHTML = effectivePlaying ? '<span class="run-icon">■</span> STOP' : '<span class="run-icon">▶</span> PLAY';
  $("system-state").className = `system-state ${effectivePlaying ? "running" : "paused"}`;
  $("system-state").innerHTML = `<span></span>${effectivePlaying ? "CONTROL ACTIVE" : "GUARDED PAUSE"}`;
  $("sim-time").textContent = `${sim.time.toFixed(2)} s`;
  $("control-state").textContent = effectivePlaying ? sim.scenario.toUpperCase() : "STOP";
  $("can-load").textContent = `${sim.canUtilization.toFixed(1)}%`;
  $("sel-angle").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.angleDeg || 0).toFixed(1)}°`
    : `${target.angle.toFixed(1)}°`;
  $("sel-velocity").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.velocityDegS || 0).toFixed(1)}°/s`
    : `${target.velocity.toFixed(1)}°/s`;
  $("sel-torque").textContent = ui.axisCategory === "arm"
    ? `${(selectedArm?.torqueNm || 0).toFixed(2)} N·m`
    : `${target.torque.toFixed(2)} N·m`;
  $("sel-sensor").textContent = ui.axisCategory === "arm"
    ? "AUX · CAN UNMAPPED"
    : target.sensorPin == null ? "NO ANALOG" : `GPIO${target.sensorPin} · ${target.adc}`;
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
    card.querySelector('[data-field="angle"]').textContent = `${joint.angle.toFixed(1)}°`;
    card.querySelector('[data-field="torque"]').textContent = `${joint.torque.toFixed(2)} N·m`;
    const dot = card.querySelector(".joint-dot");
    dot.className = `joint-dot ${joint.temperature > 80 || sim.faults.canDrop ? "warn" : sim.playMode ? "live" : ""}`;
  }

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
}

function frame(now) {
  const dt = Math.min(0.05, (now - ui.lastFrame) / 1000);
  ui.lastFrame = now;
  if (ui.policyMode) policyPlayer.update(dt);
  else sim.step(dt);
  if (now - ui.scopeSampleAt > 38) {
    const target = selectedJoint();
    ui.scopeHistory.push({ t: sim.time, angle: target.angle, desired: target.desiredPosition, torque: target.torque });
    while (ui.scopeHistory.length > 260) ui.scopeHistory.shift();
    ui.scopeSampleAt = now;
  }
  if (now - ui.lastRender > 65) {
    renderLive();
    ui.lastRender = now;
  }
  requestAnimationFrame(frame);
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
setupCadControls();
setupBoardControls();
setupFirmware();
setupRLLab();
setupGr00tLab();
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
requestAnimationFrame(frame);

window.dropbearTwin = {
  sim,
  robot,
  board,
  cad,
  armMotorStates,
  armMotorBindings: DROPBEAR_ARM_MOTOR_BINDINGS,
  policyPlayer,
  source: DROPBEAR_SOURCE,
  usdSource: DROPBEAR_USD_SOURCE,
  cadEvidence: CAD_EVIDENCE,
  get physicsRuntime() { return ui.physicsRuntime; },
};
