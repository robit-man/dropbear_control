const byId = (id) => document.getElementById(id);

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
        throw new Error(payload.error || `${response.status} ${response.statusText}`);
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
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  throw new Error("control authorization failed");
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
  const promptForm = byId("gr00t-prompt-form");
  if (!promptForm) return;

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
    }
  }
  poll();
  refreshSessions();
  window.setInterval(poll, 1500);
  window.setInterval(refreshSessions, 5000);
}
