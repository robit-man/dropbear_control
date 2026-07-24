import {
  CONTROLLER_PINS,
  DROPBEAR_SOURCE,
  DropbearSim,
  JOINT_DEFINITIONS,
  TASKS,
} from "./dropbear.js";
import { Board3D } from "./board_3d.js";
import { CAD_EVIDENCE, CadViewer } from "./cad_viewer.js";
import { DROPBEAR_USD_SOURCE, dropbearUsdBinding } from "./dropbear_usd.js";
import { Robot3D } from "./robot_3d.js";

const $ = (id) => document.getElementById(id);
const sim = new DropbearSim();

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
});

const robot = new Robot3D($("robot-canvas"), {
  onJoint: (canId) => selectJoint(canId),
  onStatus: (message, kind) => {
    $("robot-load-status").className = `load-status robot-load-status ${kind}`;
    $("robot-load-status").innerHTML = "<span></span>";
    $("robot-load-status").append(document.createTextNode(message));
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
}

function selectJoint(id) {
  ui.selectedJointId = Number(id);
  ui.scopeHistory = [];
  ui.cadManual = false;
  const target = selectedJoint();
  $("selected-name").textContent = target.label;
  $("selected-can").textContent = target.canId;
  const usdBinding = dropbearUsdBinding(target.id);
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
  document.querySelectorAll(".joint-card").forEach((card) => card.classList.toggle("active", Number(card.dataset.jointId) === target.id));
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
  $("sim-toggle").addEventListener("click", () => sim.setPlay(!sim.playMode));
  $("sim-reset").addEventListener("click", () => {
    sim.reset();
    ui.scopeHistory = [];
    selectJoint(0x141);
    appendTerminal("[dashboard] simulation reset", "warn");
  });
  $("sim-speed").addEventListener("change", (event) => { sim.speed = Number(event.target.value); });
  $("scenario").addEventListener("change", (event) => {
    sim.setScenario(event.target.value);
    if (event.target.value === "manual") $("impedance-toggle").checked = false;
  });
  $("run-demo").addEventListener("click", () => {
    $("scenario").value = "walk";
    sim.setScenario("walk");
    switchView("sim");
    appendTerminal("[dashboard] full alternating-step demo started", "ok");
  });
  $("robot-fit").addEventListener("click", () => robot.fit());
  $("position-target").addEventListener("input", (event) => {
    const target = selectedJoint();
    const value = Number(event.target.value);
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
  const runningButton = $("sim-toggle");
  runningButton.classList.toggle("stop", sim.playMode);
  runningButton.setAttribute("aria-pressed", String(sim.playMode));
  runningButton.innerHTML = sim.playMode ? '<span class="run-icon">■</span> STOP' : '<span class="run-icon">▶</span> PLAY';
  $("system-state").className = `system-state ${sim.playMode ? "running" : "paused"}`;
  $("system-state").innerHTML = `<span></span>${sim.playMode ? "CONTROL ACTIVE" : "GUARDED PAUSE"}`;
  $("sim-time").textContent = `${sim.time.toFixed(2)} s`;
  $("control-state").textContent = sim.playMode ? sim.scenario.toUpperCase() : "STOP";
  $("can-load").textContent = `${sim.canUtilization.toFixed(1)}%`;
  $("sel-angle").textContent = `${target.angle.toFixed(1)}°`;
  $("sel-velocity").textContent = `${target.velocity.toFixed(1)}°/s`;
  $("sel-torque").textContent = `${target.torque.toFixed(2)} N·m`;
  $("sel-sensor").textContent = target.sensorPin == null ? "NO ANALOG" : `GPIO${target.sensorPin} · ${target.adc}`;
  $("fault-sensor").textContent = target.sensorStuck ? "RELEASE SENSOR" : "FREEZE SENSOR";
  $("fault-thermal").textContent = target.temperature > 80 ? "CLEAR THERMAL" : "THERMAL FAULT";

  for (const card of document.querySelectorAll(".joint-card")) {
    const joint = sim.getJoint(Number(card.dataset.jointId));
    card.querySelector('[data-field="angle"]').textContent = `${joint.angle.toFixed(1)}°`;
    card.querySelector('[data-field="torque"]').textContent = `${joint.torque.toFixed(2)} N·m`;
    const dot = card.querySelector(".joint-dot");
    dot.className = `joint-dot ${joint.temperature > 80 || sim.faults.canDrop ? "warn" : sim.playMode ? "live" : ""}`;
  }

  robot.setJointStates(sim.joints, ui.selectedJointId);
  for (const side of ["left", "right"]) {
    const leg = robot.legTelemetry[side];
    const gait = sim.gait[side];
    const footHeight = $(`${side}-foot-height`);
    $(`${side}-gait-phase`).textContent = sim.playMode && sim.scenario === "walk"
      ? gait.mode.toUpperCase()
      : "HOLD";
    footHeight.textContent = `${signed(leg.footHeightMm, 0)} mm`;
    footHeight.classList.toggle("lift", leg.footHeightMm > 15);
    $(`${side}-ankle-angle`).textContent = `${signed(leg.ankleDeg)}°`;
    $(`${side}-calf-pair`).textContent = `${signed(leg.outerCalfDeg - 180)}° / ${signed(leg.innerCalfDeg - 180)}°`;
  }
  const closureText = $("closure-status-text");
  if (closureText && robot.ready) {
    closureText.textContent = `X8 CRANK → TIE ROD → ANKLE/FOOT PIVOT · MAX CLOSURE ${robot.closureResidualMm.toFixed(3)} mm`;
  }
  drawScope();
  board.setActivity({
    running: sim.running,
    playMode: sim.playMode,
    loadCellsEnabled: sim.loadCellsEnabled,
    time: sim.time,
  });
  if (!ui.cadManual) {
    cad.setJointAngle(target.angle);
    $("cad-angle").value = String(Math.max(120, Math.min(240, target.angle)));
    $("cad-angle-output").textContent = `${target.angle.toFixed(1)}°`;
  }
  $("csv-output").textContent = sim.controllers[ui.consoleController].csv;
  $("fault-can").textContent = sim.faults.canDrop ? "RESTORE CAN" : "DROP CAN";
  $("fault-serial").textContent = sim.faults.serialDrop ? "RESTORE SERIAL" : "DROP SERIAL";
  $("fault-imu").textContent = sim.faults.imuDrift ? "CLEAR IMU DRIFT" : "DRIFT IMU";
}

function frame(now) {
  const dt = Math.min(0.05, (now - ui.lastFrame) / 1000);
  ui.lastFrame = now;
  sim.step(dt);
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

setupNavigation();
makeJointCards();
setupSimControls();
setupCadControls();
setupBoardControls();
setupFirmware();
selectJoint(0x141);
renderLive();
requestAnimationFrame(frame);

window.dropbearTwin = {
  sim,
  robot,
  board,
  cad,
  source: DROPBEAR_SOURCE,
  usdSource: DROPBEAR_USD_SOURCE,
  cadEvidence: CAD_EVIDENCE,
};
