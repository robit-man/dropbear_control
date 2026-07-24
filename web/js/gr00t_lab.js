const byId = (id) => document.getElementById(id);

const G1_BODY_JOINT_ORDER = Object.freeze([
  "left_hip_pitch_joint",
  "left_hip_roll_joint",
  "left_hip_yaw_joint",
  "left_knee_joint",
  "left_ankle_pitch_joint",
  "left_ankle_roll_joint",
  "right_hip_pitch_joint",
  "right_hip_roll_joint",
  "right_hip_yaw_joint",
  "right_knee_joint",
  "right_ankle_pitch_joint",
  "right_ankle_roll_joint",
  "waist_yaw_joint",
  "waist_roll_joint",
  "waist_pitch_joint",
  "left_shoulder_pitch_joint",
  "left_shoulder_roll_joint",
  "left_shoulder_yaw_joint",
  "left_elbow_joint",
  "left_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_shoulder_pitch_joint",
  "right_shoulder_roll_joint",
  "right_shoulder_yaw_joint",
  "right_elbow_joint",
  "right_wrist_roll_joint",
  "right_wrist_pitch_joint",
  "right_wrist_yaw_joint",
]);

// Published standing defaults from the pinned NVIDIA GEAR-SONIC G1 deploy
// contract. This fixture is a decoded G1 pose, never a generated VLA token.
const G1_PUBLISHED_STAND_Q = Object.freeze([
  -0.312, 0, 0, 0.669, -0.363, 0,
  -0.312, 0, 0, 0.669, -0.363, 0,
  0, 0, 0,
  0.2, 0.2, 0, 0.6, 0, 0, 0,
  0.2, -0.2, 0, 0.6, 0, 0, 0,
]);

// Checkpoint-specific stable stand token from the pinned NVIDIA GEAR-SONIC
// release. This is an official SONIC fixture, not output from a VLA request.
const NVIDIA_RELEASE_INITIAL_TOKEN = Object.freeze([
  -0.0625, 0, -0.0625, -0.125, -0.1875, -0.0625, 0.1875,
  0.25, 0.1875, -0.125, 0.0625, -0.0625, -0.25, -0.25,
  -0.3125, -0.0625, 0, -0.0625, -0.125, -0.1875, 0,
  -0.25, 0, -0.25, -0.0625, 0.0625, 0.125, -0.125,
  0.25, 0.1875, 0.25, -0.125, 0.125, 0.1875, -0.0625,
  0, -0.1875, -0.1875, 0.25, 0, 0, -0.125,
  0.0625, 0, -0.0625, -0.0625, 0.1875, -0.0625, 0,
  0.0625, 0.125, 0.0625, 0.125, 0.0625, 0.125, 0,
  0.125, 0.1875, 0, 0, 0.0625, 0.0625, 0.1875, 0.0625,
]);
const NVIDIA_RELEASE_DECODER_CHECKPOINT = "sha256:c7241a123eaa36b5d64bad19540efde93cac1ad443bd4572fd12ca99898118ed";

export const GR00T_WBC_PLAYBACK_SOURCES = Object.freeze([
  Object.freeze({
    value: "g1-published-stand",
    label: "Published G1 stand · q29",
    readiness: "decodedG1PoseReady",
  }),
  Object.freeze({
    value: "sonic-release-stand",
    label: "Pinned SONIC release stand · 64D",
    readiness: "nvidiaTokenReady",
  }),
]);

function createBrowserSessionNonce() {
  const random = new Uint32Array(2);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(random);
  } else {
    random[0] = Math.floor(Math.random() * 0x1_0000_0000);
    random[1] = Math.floor(Math.random() * 0x1_0000_0000);
  }
  return [
    Date.now().toString(36),
    random[0].toString(36),
    random[1].toString(36),
  ].join("-");
}

const GR00T_PLAYBACK_TIMEOUT_MS = 15_000;
const GR00T_PLAYBACK_IDLE_TIMEOUT_MS = 2_000;
const CONTROL_TOKEN_FETCH_TIMEOUT_MS = 5_000;
let browserSessionGeneration = 0;
function createBrowserPlaybackSession(prefix) {
  browserSessionGeneration += 1;
  return [
    prefix,
    createBrowserSessionNonce(),
    browserSessionGeneration.toString(36),
  ].join("-");
}

let browserG1StandSession = createBrowserPlaybackSession("browser-g1-stand");
let browserSonicStandSession = createBrowserPlaybackSession(
  "browser-sonic-release",
);
let browserG1StandSequence = 0;
let browserSonicStandSequence = 0;
let browserPlaybackRequestInFlight = false;
let browserPlaybackRequestController = null;
let browserPlaybackIdlePromise = Promise.resolve();
let controlTokenValue = null;
let controlTokenPromise = null;
let controlTokenGeneration = 0;

function invalidateControlToken() {
  controlTokenGeneration += 1;
  controlTokenValue = null;
  controlTokenPromise = null;
}

function abortReason(signal) {
  if (signal?.reason instanceof Error) return signal.reason;
  const message = typeof signal?.reason === "string"
    ? signal.reason
    : "request was aborted";
  const error = new Error(message);
  error.name = "AbortError";
  return error;
}

function awaitWithCallerSignal(promise, signal) {
  if (!signal) return promise;
  if (signal.aborted) return Promise.reject(abortReason(signal));
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(abortReason(signal));
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(resolve, reject).finally(() => {
      signal.removeEventListener("abort", onAbort);
    });
  });
}

function fetchControlToken() {
  if (controlTokenValue) return Promise.resolve(controlTokenValue);
  if (!controlTokenPromise) {
    const generation = controlTokenGeneration;
    const controller = new AbortController();
    let timedOut = false;
    const timeoutId = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, CONTROL_TOKEN_FETCH_TIMEOUT_MS);
    let trackedPromise;
    trackedPromise = fetch("/api/control-token", {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `${response.status} ${response.statusText}`);
        }
        if (typeof payload.token !== "string" || !payload.token) {
          throw new Error("control token response is invalid");
        }
        if (generation !== controlTokenGeneration) {
          throw new Error("control token request was invalidated");
        }
        controlTokenValue = payload.token;
        return payload.token;
      })
      .catch((error) => {
        if (timedOut) {
          throw new Error(
            `control token request timed out after ${CONTROL_TOKEN_FETCH_TIMEOUT_MS} ms`,
          );
        }
        throw error;
      })
      .finally(() => {
        globalThis.clearTimeout(timeoutId);
        if (controlTokenPromise === trackedPromise) {
          controlTokenPromise = null;
        }
      });
    controlTokenPromise = trackedPromise;
  }
  return controlTokenPromise;
}

export async function getGr00tControlToken(signal = null) {
  if (signal?.aborted) throw abortReason(signal);
  if (controlTokenValue) return controlTokenValue;
  return awaitWithCallerSignal(fetchControlToken(), signal);
}

function rotateBrowserPlaybackSession(sourceId) {
  if (sourceId === "sonic-release-stand") {
    browserSonicStandSession = createBrowserPlaybackSession(
      "browser-sonic-release",
    );
    browserSonicStandSequence = 0;
  } else if (sourceId === "g1-published-stand") {
    // The decoded-pose endpoint does not currently enforce replay state, but
    // rotating here keeps the browser envelope safe if it does in the future.
    browserG1StandSession = createBrowserPlaybackSession("browser-g1-stand");
    browserG1StandSequence = 0;
  }
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
      headers.set(
        "X-Dropbear-Control-Token",
        await getGr00tControlToken(options.signal),
      );
      request.body = options.body === undefined ? "{}" : options.body;
    }
    const response = await fetch(url, request);
    const payload = await response.json().catch(() => ({}));
    if (response.ok) return payload;
    if (response.status === 403 && mutation && attempt === 0) {
      invalidateControlToken();
      continue;
    }
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  throw new Error("control authorization failed");
}

export async function playGr00tWbcSource(
  sourceId,
  {
    dispatch = true,
    signal = null,
    timeoutMs = GR00T_PLAYBACK_TIMEOUT_MS,
  } = {},
) {
  if (browserPlaybackRequestInFlight) {
    throw new Error("a GR00T WBC playback request is already in flight");
  }
  browserPlaybackRequestInFlight = true;
  const requestController = new AbortController();
  browserPlaybackRequestController = requestController;
  let resolvePlaybackIdle;
  browserPlaybackIdlePromise = new Promise((resolve) => {
    resolvePlaybackIdle = resolve;
  });
  let timedOut = false;
  const forwardAbort = () => requestController.abort(signal?.reason);
  if (signal?.aborted) forwardAbort();
  else signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeoutId = globalThis.setTimeout(() => {
    timedOut = true;
    requestController.abort();
  }, Math.max(1, Number(timeoutMs) || GR00T_PLAYBACK_TIMEOUT_MS));
  let request;
  let requestAcknowledged = false;
  try {
    if (sourceId === "g1-published-stand") {
      const sequence = browserG1StandSequence;
      browserG1StandSequence += 1;
      request = {
        schema: "dropbear-gr00t-retarget-request-v1",
        sessionId: browserG1StandSession,
        sequence,
        refinementIterations: 1,
        source: {
          kind: "decoded-g1-pose",
          schema: "unitree-g1-body-position-v1",
          jointOrder: G1_BODY_JOINT_ORDER,
          positionsRad: G1_PUBLISHED_STAND_Q,
          producer: "nvidia-gear-sonic-published-g1-stand-fixture",
          nvidiaVlaDerived: false,
        },
      };
    } else if (sourceId === "sonic-release-stand") {
      const sequence = browserSonicStandSequence;
      browserSonicStandSequence += 1;
      request = {
        schema: "dropbear-gr00t-retarget-request-v1",
        sessionId: browserSonicStandSession,
        sequence,
        refinementIterations: 1,
        source: {
          kind: "nvidia-sonic-release-token-fixture",
          schema: "nvidia-gr00t-sonic-motion-token-64d-v1",
          motionToken: NVIDIA_RELEASE_INITIAL_TOKEN,
          producer: "nvidia-gear-sonic-release",
          checkpoint: NVIDIA_RELEASE_DECODER_CHECKPOINT,
          sequenceStart: sequence,
        },
      };
    } else {
      throw new Error(`unsupported GR00T WBC playback source: ${sourceId}`);
    }
    const payload = await requestJson("/api/gr00t/retarget", {
      method: "POST",
      body: JSON.stringify(request),
      signal: requestController.signal,
    });
    requestAcknowledged = true;
    const playbackPayload = { ...payload, playbackSourceId: sourceId };
    if (dispatch) {
      window.dispatchEvent(new CustomEvent(
        "dropbear:retargeted-pose",
        { detail: playbackPayload },
      ));
    }
    return playbackPayload;
  } catch (error) {
    if (request && !requestAcknowledged) {
      rotateBrowserPlaybackSession(sourceId);
    }
    if (timedOut) {
      throw new Error(`GR00T WBC playback timed out after ${timeoutMs} ms`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", forwardAbort);
    if (browserPlaybackRequestController === requestController) {
      browserPlaybackRequestController = null;
    }
    browserPlaybackRequestInFlight = false;
    resolvePlaybackIdle();
  }
}

export function cancelGr00tWbcPlayback() {
  browserPlaybackRequestController?.abort();
  return browserPlaybackIdlePromise;
}

export async function waitForGr00tWbcPlaybackIdle(
  timeoutMs = GR00T_PLAYBACK_IDLE_TIMEOUT_MS,
) {
  if (!browserPlaybackRequestInFlight) return;
  const idlePromise = browserPlaybackIdlePromise;
  let timeoutId;
  try {
    await Promise.race([
      idlePromise,
      new Promise((_, reject) => {
        timeoutId = globalThis.setTimeout(() => {
          reject(new Error(
            `GR00T WBC playback did not cancel within ${timeoutMs} ms`,
          ));
        }, Math.max(1, Number(timeoutMs) || GR00T_PLAYBACK_IDLE_TIMEOUT_MS));
      }),
    ]);
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

function setGate(id, ready, readyLabel = "READY", blockedLabel = "BLOCKED") {
  const gate = byId(id);
  if (!gate) return;
  gate.classList.toggle("ready", Boolean(ready));
  gate.classList.toggle("blocked", !ready);
  gate.querySelector("b").textContent = ready ? readyLabel : blockedLabel;
}

function numberValue(id) {
  return Number(byId(id).value);
}

function trainingConfig() {
  return {
    motionProfile: byId("gr00t-motion-profile").value,
    devices: byId("gr00t-devices").value.split(",").map(Number),
    updates: numberValue("gr00t-updates"),
    rolloutSteps: numberValue("gr00t-rollout-steps"),
    environments: numberValue("gr00t-environments"),
    ppoEpochs: numberValue("gr00t-ppo-epochs"),
    batchSize: numberValue("gr00t-batch-size"),
    precision: byId("gr00t-precision").value,
    targetSpeed: numberValue("gr00t-target-speed"),
    targetTurnRate: numberValue("gr00t-target-turn"),
    verticalConstraint: byId("gr00t-vertical-constraint").checked,
  };
}

function renderPrompt(plan) {
  const result = byId("gr00t-prompt-result");
  result.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "gr00t-plan-summary";
  const values = [
    ["PRIMITIVE", plan.primitive],
    ["PROFILE", plan.motion_profile],
    ["SPEED", `${Number(plan.target_speed_mps).toFixed(2)} m/s`],
    ["TURN", `${Number(plan.target_turn_rate_rps).toFixed(2)} rad/s`],
    ["STRIDE", Number(plan.stride_scale).toFixed(2)],
    ["KNEE", Number(plan.knee_scale).toFixed(2)],
    ["ARM", Number(plan.arm_swing_scale).toFixed(2)],
    ["TOKEN", `${plan.tokenDimension}D · ${plan.tokenSource}`],
  ];
  for (const [label, value] of values) {
    const cell = document.createElement("div");
    const span = document.createElement("span");
    const bold = document.createElement("b");
    span.textContent = label;
    bold.textContent = String(value).toUpperCase();
    cell.append(span, bold);
    summary.append(cell);
  }
  const token = document.createElement("code");
  token.textContent = plan.token_state.slice(0, 12).map((value) => Number(value).toFixed(3)).join("  ");
  const note = document.createElement("p");
  note.textContent = `Confidence ${(100 * Number(plan.confidence)).toFixed(0)}% · ${plan.notes.join(" · ")} · hardware locked`;
  result.append(summary, token, note);
}

function renderBridgeResult(payload) {
  const result = byId("gr00t-bridge-result");
  if (!result) return;
  result.innerHTML = "";
  const diagnostics = payload.diagnostics || {};
  const provenance = payload.provenance || {};
  const values = [
    ["SOURCE", provenance.inputClass || "unknown"],
    ["G1 DECODER", provenance.g1ShadowDecodeUsed ? "used" : "not used"],
    ["MOTORS", `${diagnostics.actionCount || 0} / 22`],
    ["SATURATED", diagnostics.saturationCount || 0],
  ];
  const summary = document.createElement("div");
  summary.className = "gr00t-plan-summary";
  for (const [label, value] of values) {
    const cell = document.createElement("div");
    const span = document.createElement("span");
    const bold = document.createElement("b");
    span.textContent = label;
    bold.textContent = String(value).toUpperCase();
    cell.append(span, bold);
    summary.append(cell);
  }
  const positions = payload.retarget?.target?.positionsRad || [];
  const target = document.createElement("code");
  target.textContent = positions
    .map((value) => Number(value).toFixed(3))
    .join("  ");
  const note = document.createElement("p");
  note.textContent = [
    `USD closure ${Number(diagnostics.maximumUsdClosureResidualM || 0).toExponential(2)} m`,
    `task ${Number(diagnostics.seedTaskError || 0).toFixed(3)} → ${Number(diagnostics.finalTaskError || 0).toFixed(3)}`,
    `DLS ${diagnostics.refinementIterationsAccepted || 0}/${diagnostics.refinementIterationsRequested || 0}`,
    "contact forces remain Isaac/PhysX-authoritative",
    "hardware locked",
  ].join(" · ");
  result.append(summary, target, note);
}

function renderTraining(training = {}) {
  const running = ["running", "stopping"].includes(training.state);
  byId("gr00t-train").disabled = running;
  byId("gr00t-stop").disabled = !running;
  byId("gr00t-training-id").textContent = training.sessionId
    ? training.sessionId.slice(-8).toUpperCase()
    : "NEW SESSION";
  byId("gr00t-rail-state").hidden = !training.sessionId;
  const progress = training.progress || {};
  const update = Number(progress.update || progress.updatesComplete || 0);
  const total = Number(progress.updates || training.config?.updates || 0);
  byId("gr00t-training-fill").style.width = `${total ? 100 * update / total : training.state === "complete" ? 100 : 0}%`;
  const log = byId("gr00t-training-log");
  log.innerHTML = "";
  for (const event of (training.events || []).slice(-32)) {
    const row = document.createElement("div");
    const tag = document.createElement("span");
    tag.textContent = String(event.event || "LOG").toUpperCase();
    const metric = event.event === "progress"
      ? `update ${event.update || event.updatesComplete || "?"}/${event.updates || total || "?"} · loss ${Number(event.loss ?? event.policyLoss ?? 0).toFixed(4)} · ${event.device || "CUDA"}`
      : event.message || (event.event === "complete" ? "checkpoint and session manifest written" : JSON.stringify(event));
    row.append(tag, document.createTextNode(metric));
    log.append(row);
  }
  if (!log.childElementCount) {
    const row = document.createElement("div");
    const tag = document.createElement("span");
    tag.textContent = String(training.state || "READY").toUpperCase();
    row.append(tag, document.createTextNode(training.error || "Waiting for a CUDA training session."));
    log.append(row);
  }
  log.scrollTop = log.scrollHeight;
}

function renderRuntime(status) {
  const gates = status.gates || {};
  const ready = gates.cudaPolicy
    && gates.onnxCuda
    && gates.tensorRtExact
    && gates.cudaDeploymentVerified;
  const state = byId("gr00t-runtime-state");
  state.className = `load-status ${ready ? "ok" : "error"}`;
  state.innerHTML = "<span></span>";
  state.append(document.createTextNode(
    ready ? "CUDA RESIDUAL ENGINE BUILD VERIFIED" : "RUNTIME GATE INCOMPLETE",
  ));
  setGate("gr00t-gate-cuda", gates.cudaPolicy, "A100 READY");
  setGate("gr00t-gate-onnx", gates.onnxCuda, "CUDA EP READY");
  setGate("gr00t-gate-trt", gates.tensorRtExact, "10.13 READY");
  setGate("gr00t-gate-smoke", gates.cudaDeploymentVerified, "BUILD VERIFIED");
  setGate("gr00t-gate-isaac", gates.authoritativeIsaacPhysx, "VALIDATED", "NOT VALIDATED");
  setGate("gr00t-gate-hardware", gates.hardwareDeployment, "ADMITTED", "LOCKED");
  const revision = status.upstream?.commit || status.upstream?.revision || "";
  byId("gr00t-upstream-revision").textContent = revision
    ? `UPSTREAM ${String(revision).slice(0, 8).toUpperCase()}`
    : "UPSTREAM UNPINNED";
  const devices = status.probe?.devices || [];
  const compatibleDevices = devices.filter(
    (device) => Number(device.capability?.[0] || 0) >= 7,
  );
  const selector = byId("gr00t-devices");
  const fingerprint = compatibleDevices
    .map((device) => `${device.index}:${device.name}`)
    .join("|");
  if (selector && selector.dataset.inventory !== fingerprint) {
    const previous = selector.value;
    selector.innerHTML = "";
    for (let count = 1; count <= Math.min(3, compatibleDevices.length); count += 1) {
      const selectedDevices = compatibleDevices.slice(0, count);
      const option = document.createElement("option");
      option.value = selectedDevices.map((device) => device.index).join(",");
      option.textContent = selectedDevices
        .map((device) => `${device.name.replace("NVIDIA ", "")} · GPU ${device.index}`)
        .join(" + ");
      selector.append(option);
    }
    selector.dataset.inventory = fingerprint;
    if ([...selector.options].some((option) => option.value === previous)) {
      selector.value = previous;
    }
  }
  const list = byId("gr00t-device-list");
  list.innerHTML = "";
  if (!devices.length) {
    list.append(document.createTextNode(status.probe?.error || "No CUDA devices detected."));
  } else {
    for (const device of devices) {
      const row = document.createElement("div");
      const span = document.createElement("span");
      const bold = document.createElement("b");
      span.textContent = `CUDA ${device.index}`;
      bold.textContent = `${device.name} · SM ${device.capability.join(".")}`;
      row.append(span, bold);
      list.append(row);
    }
    const verification = status.verification || {};
    const row = document.createElement("div");
    const span = document.createElement("span");
    const bold = document.createElement("b");
    span.textContent = "LAST E2E";
    bold.textContent = verification.verified
      ? `${verification.sessionId} · ONNX ${Number(verification.onnx?.max_abs_error || 0).toExponential(2)} · TRT ${Number(verification.tensorRt?.max_abs_error || 0).toExponential(2)}`
      : verification.reason || "NOT VERIFIED";
    row.append(span, bold);
    list.append(row);
  }
  const bridge = status.retargetBridge || {};
  const bridgeReady = Boolean(bridge.decodedG1PoseReady);
  setGate(
    "gr00t-bridge-pose",
    bridgeReady,
    "READY",
    bridge.error ? "ERROR" : "BLOCKED",
  );
  setGate(
    "gr00t-bridge-token",
    bridge.nvidiaTokenReady,
    "G1 SHADOW READY",
    "DECODER BLOCKED",
  );
  setGate(
    "gr00t-bridge-target",
    bridgeReady,
    "22 AXES READY",
    "BLOCKED",
  );
  setGate(
    "gr00t-bridge-physx",
    bridge.target?.fullUsdPassiveSolve,
    "FULL GRAPH READY",
    "BLOCKED",
  );
  const bridgeState = byId("gr00t-bridge-state");
  if (bridgeState) {
    bridgeState.textContent = bridgeReady
      ? bridge.nvidiaTokenReady
        ? "POSE + TOKEN READY"
        : "POSE READY · TOKEN GATED"
      : "BRIDGE BLOCKED";
  }
  const preview = byId("gr00t-preview-g1-pose");
  if (preview) {
    preview.dataset.ready = bridgeReady ? "1" : "0";
    if (!preview.dataset.busy) preview.disabled = !bridgeReady;
  }
  const tokenPreview = byId("gr00t-preview-sonic-token");
  if (tokenPreview) {
    tokenPreview.dataset.ready = bridge.nvidiaTokenReady ? "1" : "0";
    if (!tokenPreview.dataset.busy) {
      tokenPreview.disabled = !bridge.nvidiaTokenReady;
    }
  }
  window.dispatchEvent(new CustomEvent("dropbear:gr00t-runtime", {
    detail: {
      decodedG1PoseReady: bridgeReady,
      nvidiaTokenReady: Boolean(bridge.nvidiaTokenReady),
    },
  }));
  renderTraining(status.training);
}

function applySessionConfig(session) {
  const config = session.config || {};
  const values = {
    "gr00t-motion-profile": config.motion_profile,
    "gr00t-devices": config.devices,
    "gr00t-updates": config.updates,
    "gr00t-rollout-steps": config.rollout_steps,
    "gr00t-environments": config.environments,
    "gr00t-ppo-epochs": config.ppo_epochs,
    "gr00t-batch-size": config.batch_size,
    "gr00t-precision": config.amp ? config.amp_dtype : "float32",
    "gr00t-target-speed": config.target_speed,
    "gr00t-target-turn": config.target_turn_rate,
  };
  for (const [id, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && byId(id)) {
      byId(id).value = String(value);
    }
  }
  byId("gr00t-vertical-constraint").checked = Boolean(config.vertical_constraint);
  byId("gr00t-training-id").textContent = `COPY ${String(session.sessionId).slice(-8).toUpperCase()}`;
}

function renderSessions(payload = {}) {
  const list = byId("gr00t-session-list");
  if (!list) return;
  list.innerHTML = "";
  const sessions = payload.sessions || [];
  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "rl-session-empty";
    empty.textContent = "No local CUDA sessions yet.";
    list.append(empty);
    return;
  }
  for (const session of sessions) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "gr00t-session-row";
    row.setAttribute("role", "option");
    row.addEventListener("click", () => applySessionConfig(session));
    const heading = document.createElement("div");
    const name = document.createElement("b");
    const state = document.createElement("span");
    name.textContent = String(session.sessionId).toUpperCase();
    state.textContent = String(session.state || "complete").toUpperCase();
    heading.append(name, state);
    const metrics = session.metrics || {};
    const detail = document.createElement("p");
    detail.textContent = [
      `${session.config?.updates || metrics.updates || "?"} updates`,
      `${Number(metrics.reward || 0).toFixed(3)} reward`,
      `${Number(metrics.upright_percent || 0).toFixed(1)}% upright`,
      session.device?.device_names?.join(" + ") || "CUDA",
    ].join(" · ");
    row.append(heading, detail);
    if (session.deployment) {
      const link = document.createElement("a");
      link.href = session.deployment;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "DEPLOYMENT REPORT ↗";
      link.addEventListener("click", (event) => event.stopPropagation());
      row.append(link);
    }
    list.append(row);
  }
}

export function setupGr00tLab() {
  let currentPlan = null;
  let previewGeneration = 0;
  let previewAbortController = null;
  let previewRequestPromise = null;
  let previewReadinessKey = null;
  const promptForm = byId("gr00t-prompt-form");
  if (!promptForm) return;

  const cancelPreviewRequest = () => {
    previewGeneration += 1;
    previewAbortController?.abort();
    previewAbortController = null;
    previewReadinessKey = null;
  };

  const runPreview = async (
    sourceId,
    button,
    readinessKey,
    errorPrefix,
  ) => {
    cancelPreviewRequest();
    const generation = previewGeneration;
    if (previewRequestPromise) {
      try {
        await previewRequestPromise;
      } catch {
        // Cancellation or a failed previous preview releases the module lock.
      }
      if (generation !== previewGeneration) return;
    }
    if (button.dataset.ready !== "1") return;
    const controller = new AbortController();
    previewAbortController = controller;
    previewReadinessKey = readinessKey;
    button.dataset.busy = "1";
    button.disabled = true;
    const request = playGr00tWbcSource(sourceId, {
      dispatch: false,
      signal: controller.signal,
    });
    previewRequestPromise = request;
    try {
      const payload = await request;
      if (
        generation !== previewGeneration
        || controller.signal.aborted
        || button.dataset.ready !== "1"
      ) return;
      renderBridgeResult(payload);
      window.dispatchEvent(new CustomEvent(
        "dropbear:retargeted-pose",
        { detail: payload },
      ));
    } catch (error) {
      if (generation !== previewGeneration || controller.signal.aborted) return;
      byId("gr00t-bridge-result").textContent = `${errorPrefix} · ${error.message}`;
    } finally {
      if (previewRequestPromise === request) previewRequestPromise = null;
      if (previewAbortController === controller) {
        previewAbortController = null;
        previewReadinessKey = null;
      }
      delete button.dataset.busy;
      button.disabled = button.dataset.ready !== "1";
    }
  };

  window.addEventListener("dropbear:gr00t-runtime", (event) => {
    const readiness = event.detail || {};
    const buttonReadiness = [
      ["gr00t-preview-g1-pose", "decodedG1PoseReady"],
      ["gr00t-preview-sonic-token", "nvidiaTokenReady"],
    ];
    for (const [id, key] of buttonReadiness) {
      const button = byId(id);
      if (!button) continue;
      const ready = readiness[key] === true;
      button.dataset.ready = ready ? "1" : "0";
      if (!button.dataset.busy) button.disabled = !ready;
    }
    if (
      previewReadinessKey
      && readiness[previewReadinessKey] !== true
    ) {
      cancelPreviewRequest();
    }
  });

  promptForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    byId("gr00t-plan-prompt").disabled = true;
    try {
      currentPlan = await requestJson("/api/gr00t/prompt", {
        method: "POST",
        body: JSON.stringify({ prompt: byId("gr00t-prompt").value }),
      });
      renderPrompt(currentPlan);
      byId("gr00t-preview-prompt").disabled = false;
      byId("gr00t-motion-profile").value = currentPlan.motion_profile;
      byId("gr00t-target-speed").value = currentPlan.target_speed_mps;
      byId("gr00t-target-turn").value = currentPlan.target_turn_rate_rps;
    } catch (error) {
      byId("gr00t-prompt-result").textContent = `PLAN REJECTED · ${error.message}`;
      byId("gr00t-preview-prompt").disabled = true;
    } finally {
      byId("gr00t-plan-prompt").disabled = false;
    }
  });

  byId("gr00t-preview-prompt").addEventListener("click", () => {
    if (!currentPlan) return;
    window.dispatchEvent(new CustomEvent("dropbear:prompt-plan", { detail: currentPlan }));
  });

  byId("gr00t-preview-g1-pose").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    await runPreview(
      "g1-published-stand",
      button,
      "decodedG1PoseReady",
      "RETARGET REJECTED",
    );
  });

  byId("gr00t-preview-sonic-token").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    await runPreview(
      "sonic-release-stand",
      button,
      "nvidiaTokenReady",
      "SONIC DECODE REJECTED",
    );
  });

  byId("gr00t-training-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const training = await requestJson("/api/gr00t/train", {
        method: "POST",
        body: JSON.stringify(trainingConfig()),
      });
      renderTraining(training);
    } catch (error) {
      renderTraining({ state: "error", error: error.message, events: [] });
    }
  });

  byId("gr00t-stop").addEventListener("click", async () => {
    try {
      renderTraining(await requestJson("/api/gr00t/stop", {
        method: "POST",
        body: "{}",
      }));
    } catch (error) {
      renderTraining({ state: "error", error: error.message, events: [] });
    }
  });

  async function refreshSessions() {
    try {
      renderSessions(await requestJson("/api/gr00t/sessions"));
    } catch (error) {
      renderSessions({ sessions: [] });
    }
  }
  byId("gr00t-refresh-sessions").addEventListener("click", refreshSessions);

  async function poll() {
    try {
      renderRuntime(await requestJson("/api/gr00t/status"));
    } catch (error) {
      const state = byId("gr00t-runtime-state");
      state.className = "load-status error";
      state.innerHTML = "<span></span>";
      state.append(document.createTextNode(`GR00T SERVICE OFFLINE · ${error.message}`));
      window.dispatchEvent(new CustomEvent("dropbear:gr00t-runtime", {
        detail: {
          decodedG1PoseReady: false,
          nvidiaTokenReady: false,
          status: "offline",
        },
      }));
    }
  }
  poll();
  refreshSessions();
  window.setInterval(poll, 1500);
  window.setInterval(refreshSessions, 5000);
}
