// web/js/app.js
//
// Dashboard controller: wires the protocol/motors/sim/webserial modules to the
// DOM. Supports two modes:
//   - Simulation: runs the in-browser MotorSim fleet and renders live state.
//   - WebSerial: connects to the ESP32 and exchanges 64-byte frames. (Requires
//     a firmware serial frame parser; see webserial.js header.)

import { Frame, FrameType } from "./protocol.js";
import { defaultFleet, decodeModel, LEGACY_VARIANTS, legacySpec } from "./motors.js";
import { MotorSim, MotorState, FaultCode } from "./sim.js";
import { WebSerialTransport } from "./webserial.js";
import { livePinView, DATA_FLOW } from "./pins.js";
import {
  COMMANDS, commandGroups, buildCommand, describeFrame,
  STATUS_WORD_BITS, FAULT_CODES, PARAM_ADDRESSES, FRAME_TYPES,
  NATIVE_RMDX_COMMANDS,
} from "./commands.js";

const $ = (id) => document.getElementById(id);

const state = {
  mode: "idle", // idle | sim | serial
  fleet: [], // MotorSim[]
  selected: null, // MotorSim
  transport: null,
  seq: 0,
  raf: null,
  lastT: 0,
  hw: null, // { board, pins }
};

// ---- logging -------------------------------------------------------------
function log(msg, kind = "") {
  const el = $("log");
  const line = document.createElement("div");
  line.className = "line" + (kind ? " " + kind : "");
  const t = new Date().toLocaleTimeString();
  line.innerHTML = `<b>[${t}]</b> ${msg}`;
  el.prepend(line);
  while (el.childElementCount > 200) el.removeChild(el.lastChild);
}

// ---- fleet rendering -----------------------------------------------------
function renderFleet() {
  const list = $("fleet-list");
  list.innerHTML = "";
  for (const m of state.fleet) {
    const card = document.createElement("div");
    card.className = "fleet-card" + (state.selected === m ? " active" : "");
    const fault = m.fault !== FaultCode.NONE;
    const dot = fault ? "fault" : m.enabled ? "ok" : "idle";
    card.innerHTML = `
      <div class="fc-model">${m.spec.model}</div>
      <div class="fc-sub">${m.spec.series} · ${m.spec.gearbox}</div>
      <div class="fc-state"><span class="dot ${dot}"></span>${stateName(m.status)}</div>`;
    card.onclick = () => selectMotor(m);
    list.appendChild(card);
  }
}

function stateName(s) {
  return Object.keys(MotorState).find((k) => MotorState[k] === s) || "UNKNOWN";
}
function faultName(f) {
  return Object.keys(FaultCode).find((k) => FaultCode[k] === f) || "NONE";
}

// ---- detail panel --------------------------------------------------------
function selectMotor(m) {
  state.selected = m;
  $("detail-empty").classList.add("hidden");
  $("detail").classList.remove("hidden");
  $("d-model").textContent = m.spec.model;
  $("d-series").textContent = m.spec.series;
  renderFleet();
  renderDetail();
}

function renderDetail() {
  const m = state.selected;
  if (!m) return;
  $("d-state").textContent = stateName(m.status);
  $("d-state").className = "tag state " + (m.fault !== FaultCode.NONE ? "fault" : m.enabled ? "run" : "");
  $("m-pos").textContent = m.position.toFixed(2) + " rad";
  $("m-vel").textContent = m.velocity.toFixed(2) + " rad/s";
  $("m-torq").textContent = m.torque.toFixed(2) + " N·m";
  $("m-temp").textContent = m.temperature.toFixed(0) + " °C";
  $("m-fault").textContent = faultName(m.fault);
  $("m-uptime").textContent = m.uptime.toFixed(0) + " s";
  const enc = m.spec.encoderType || "absolute";
  const res = m.spec.encoderResolution || "—";
  $("m-enc").textContent = enc === "incremental" ? "Incremental" : "Absolute";
  $("m-res").textContent = res + (enc === "incremental" ? " PPR" : " bit");
  $("m-zeroed").textContent = (m.zeroedPosition || 0).toFixed(2) + " rad";
  $("c-as5600").checked = !!m.as5600;
  drawMotor(m);
}

// ---- canvas visualization ------------------------------------------------
function drawMotor(m) {
  const c = $("motor-canvas");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height;
  const cx = w / 2, cy = h / 2;
  ctx.clearRect(0, 0, w, h);

  // housing
  ctx.strokeStyle = "#2a2a2a";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, 90, 0, Math.PI * 2);
  ctx.stroke();

  // rotor (rotates with position)
  const ang = m.position % (Math.PI * 2);
  ctx.strokeStyle = m.fault !== FaultCode.NONE ? "#fca5a5" : "#facc15";
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(ang) * 80, cy + Math.sin(ang) * 80);
  ctx.stroke();

  // hub
  ctx.fillStyle = "#1c232c";
  ctx.beginPath();
  ctx.arc(cx, cy, 18, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#f59e0b";
  ctx.stroke();

  // temperature ring
  const t = Math.min(1, Math.max(0, (m.temperature - 25) / 95));
  ctx.strokeStyle = `rgb(${Math.round(63 + t * 192)}, ${Math.round(182 - t * 127)}, ${Math.round(255 - t * 196)})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(cx, cy, 100, -Math.PI / 2, -Math.PI / 2 + t * Math.PI * 2);
  ctx.stroke();
}

// ---- simulation loop -----------------------------------------------------
function tick(ts) {
  if (state.mode !== "sim") return;
  if (!state.lastT) state.lastT = ts;
  const dt = Math.min(0.05, (ts - state.lastT) / 1000);
  state.lastT = ts;

  for (const m of state.fleet) {
    m.step(dt);
    if (state.transport && state.transport.connected) {
      state.transport.send(m.toStatusFrame(state.seq++)).catch(() => {});
    }
  }
  renderFleet();
  renderDetail();
  renderPinGrid(); // keep live pin/signal + data-flow view in sync with sim
  state.raf = requestAnimationFrame(tick);
}

function startSim() {
  if (state.mode === "sim") return;
  state.mode = "sim";
  state.fleet = defaultFleet().map((spec) => new MotorSim(spec));
  state.selected = state.fleet[0];
  $("conn-status").textContent = "sim";
  $("conn-status").className = "status-pill sim";
  $("btn-sim").textContent = "Stop Simulation";
  log("Simulation started with " + state.fleet.length + " motors.", "ok");
  renderFleet();
  selectMotor(state.selected);
  state.lastT = 0;
  state.raf = requestAnimationFrame(tick);
}

function stopSim() {
  if (state.mode !== "sim") return;
  state.mode = "idle";
  if (state.raf) cancelAnimationFrame(state.raf);
  state.raf = null;
  state.fleet = [];
  state.selected = null;
  $("conn-status").textContent = "offline";
  $("conn-status").className = "status-pill offline";
  $("btn-sim").textContent = "Start Simulation";
  $("detail").classList.add("hidden");
  $("detail-empty").classList.remove("hidden");
  renderFleet();
  log("Simulation stopped.", "ok");
}

function toggleSim() {
  if (state.mode === "sim") stopSim();
  else startSim();
}

// ---- controls ------------------------------------------------------------
function wireControls() {
  $("c-enable").onclick = () => {
    if (!state.selected) return;
    state.selected.enable();
    log(`Enable motor ${state.selected.id}`);
    renderDetail();
  };
  $("c-disable").onclick = () => {
    if (!state.selected) return;
    state.selected.disable();
    log(`Disable motor ${state.selected.id}`);
    renderDetail();
  };
  $("c-clear").onclick = () => {
    if (!state.selected) return;
    state.selected.clearFault();
    log(`Clear fault motor ${state.selected.id}`, "ok");
    renderDetail();
  };
  $("c-send").onclick = () => {
    if (!state.selected) return;
    const mode = $("c-mode").value;
    let v = parseFloat($("c-target").value) || 0;
    const useDeg = $("c-unit-deg").checked;
    if (mode === "position") {
      if (useDeg) v = v * Math.PI / 180;
      state.selected.setPosition(v);
    } else if (mode === "velocity") state.selected.setVelocity(v);
    else state.selected.setTorque(v);
    log(`Motor ${state.selected.id} ${mode} -> ${v}`);
    renderDetail();
  };
  $("c-overtemp").onclick = () => {
    if (!state.selected) return;
    state.selected.temperature = 130;
    log(`Injected overheat on motor ${state.selected.id}`, "err");
    renderDetail();
  };
  $("c-as5600").onchange = () => {
    if (!state.selected) return;
    const on = $("c-as5600").checked;
    state.selected.setAs5600(on);
    log(`AS5600 on motor ${state.selected.id} ${on ? "attached" : "detached"}`, on ? "ok" : "");
    renderDetail();
  };
  $("c-calibrate").onclick = () => {
    if (!state.selected) return;
    const off = state.selected.calibrate();
    log(`Calibrated zero on motor ${state.selected.id} @ ${off.toFixed(2)} rad`, "ok");
    renderDetail();
  };
  $("cmd-send").onclick = issueCommand;
}

// ---- command console -----------------------------------------------------
let selectedCmd = null; // currently selected COMMANDS entry

function renderCommandSelect() {
  const sel = $("cmd-select");
  sel.innerHTML = "";
  const groups = commandGroups();
  for (const [group, cmds] of Object.entries(groups)) {
    const og = document.createElement("optgroup");
    og.label = group;
    for (const c of cmds) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.label;
      og.appendChild(opt);
    }
    sel.appendChild(og);
  }
  sel.onchange = () => renderCommandParams();
  renderCommandParams();
}

function renderCommandParams() {
  const id = $("cmd-select").value;
  selectedCmd = COMMANDS.find((c) => c.id === id) || null;
  const box = $("cmd-params");
  box.innerHTML = "";
  if (!selectedCmd) return;
  for (const p of selectedCmd.params) {
    const row = document.createElement("div");
    row.className = "ctl-row";
    const label = document.createElement("label");
    label.textContent = p.label;
    const input = document.createElement(p.options ? "select" : "input");
    if (p.options) {
      for (const o of p.options) {
        const o2 = document.createElement("option");
        o2.value = String(o.v);
        o2.textContent = o.t;
        input.appendChild(o2);
      }
    } else if (p.type === "raw") {
      input.type = "text";
      input.placeholder = "e.g. 01 02 03";
      input.value = String(p.def ?? "");
    } else {
      input.type = "number";
      input.step = p.scale && p.scale < 1 ? "0.001" : "1";
      input.value = String(p.def ?? 0);
    }
    input.dataset.key = p.key;
    row.appendChild(label);
    row.appendChild(input);
    box.appendChild(row);
  }
  const note = document.createElement("div");
  note.className = "doc-note";
  note.textContent = selectedCmd.desc + "  [" + selectedCmd.doc + "]";
  box.appendChild(note);
}

function issueCommand() {
  if (!selectedCmd) return;
  if (!state.selected) {
    log("Select a motor first.", "err");
    return;
  }
  const values = {};
  for (const inp of $("cmd-params").querySelectorAll("[data-key]")) {
    values[inp.dataset.key] = inp.value;
  }
  const frame = buildCommand(selectedCmd, state.selected.id, values, state.seq++);
  const summary = describeFrame(frame);
  log("TX " + summary, "ok");

  // Apply locally in simulation mode; otherwise forward over the transport.
  if (state.mode === "sim") {
    state.selected.applyFrame(frame);
    renderDetail();
  } else if (state.transport && state.transport.connected) {
    state.transport.send(frame).catch((e) => log("Send failed: " + e.message, "err"));
  } else {
    log("No active link (start simulation or connect ESP32).", "err");
  }
}

// ---- command reference / docs ---------------------------------------------
function renderDocs() {
  // Commands table
  const cmdBody = $("doc-commands");
  let html = `<table class="doc-table"><thead><tr><th>Command</th><th>Byte</th><th>Frame</th><th>Description</th><th>Source</th></tr></thead><tbody>`;
  for (const c of COMMANDS) {
    const ft = FRAME_TYPES.find((f) => f.id === c.frameType);
    html += `<tr><td>${c.label}</td><td><code>0x${c.commandType.toString(16).padStart(2, "0")}</code></td><td>${ft ? ft.name : "—"}</td><td>${c.desc}</td><td>${c.doc}</td></tr>`;
  }
  html += `</tbody></table>`;
  cmdBody.innerHTML = html;

  // Params table
  const pBody = $("doc-params");
  let ph = `<table class="doc-table"><thead><tr><th>Address</th><th>Name</th><th>Size</th><th>Default</th><th>Description</th></tr></thead><tbody>`;
  for (const p of PARAM_ADDRESSES) {
    ph += `<tr><td><code>${p.addr}</code></td><td>${p.name}</td><td>${p.size}</td><td>${p.def}</td><td>${p.desc}</td></tr>`;
  }
  ph += `</tbody></table>`;
  pBody.innerHTML = ph;

  // Status word table
  const sBody = $("doc-status");
  let sh = `<table class="doc-table"><thead><tr><th>Bit</th><th>Name</th><th>Description</th></tr></thead><tbody>`;
  for (const b of STATUS_WORD_BITS) {
    sh += `<tr><td>${b.bit}</td><td>${b.name}</td><td>${b.desc}</td></tr>`;
  }
  sh += `</tbody></table>`;
  sBody.innerHTML = sh;

  // Faults tables (one per source)
  const fBody = $("doc-faults");
  let fh = "";
  for (const [src, rows] of Object.entries(FAULT_CODES)) {
    fh += `<div class="doc-note">${src}</div>`;
    fh += `<table class="doc-table"><thead><tr><th>Code</th><th>Name</th><th>Description</th></tr></thead><tbody>`;
    for (const r of rows) {
      fh += `<tr><td><code>${r.code}</code></td><td>${r.name}</td><td>${r.desc}</td></tr>`;
    }
    fh += `</tbody></table>`;
  }
  fBody.innerHTML = fh;

  // Native RMD-X command array (vendor CAN command bytes)
  const nBody = $("doc-native");
  let nh = `<div class="doc-note">Native MyActuator RMD-X CAN command set (vendor docs). Issue any of these via the "Raw Native Command" entry in the Command Console. Motion (0xB1–0xB6), encoder-zero (0xC2), and clear-fault (0xDA) commands drive the simulation; read commands are acknowledged.</div>`;
  nh += `<table class="doc-table"><thead><tr><th>Code</th><th>Dir</th><th>Name</th><th>Description</th></tr></thead><tbody>`;
  for (const c of NATIVE_RMDX_COMMANDS) {
    nh += `<tr><td><code>${c.code}</code></td><td>${c.dir}</td><td>${c.name}</td><td>${c.desc}</td></tr>`;
  }
  nh += `</tbody></table>`;
  nBody.innerHTML = nh;

  // Tab switching
  for (const tab of document.querySelectorAll(".doc-tab")) {
    tab.onclick = () => {
      document.querySelectorAll(".doc-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const which = tab.dataset.tab;
      for (const id of ["commands", "params", "status", "faults", "native"]) {
        $("doc-" + id).classList.toggle("hidden", id !== which);
      }
    };
  }
}

// ---- legacy variants + hardware config -----------------------------------
const BOARD_PINS = {
  esp32dev: {
    label: "ESP32 30-pin DevKitC",
    pins: { PIN_ENCODER_A: 4, PIN_ENCODER_B: 5, PIN_ENCODER_Z: 16, PIN_MOTOR_PWM_A: 18, PIN_MOTOR_PWM_B: 19, PIN_CURRENT_SENSE: 34, PIN_TEMP_SENSE: 35, PIN_CAN_TX: 22, PIN_CAN_RX: 23, PIN_RS485_TX: 17, PIN_RS485_RX: 15, PIN_STATUS_LED: 2, PIN_FAULT_LED: 25 },
  },
  "esp32-s3-devkitc-1": {
    label: "ESP32-S3 DevKitC",
    pins: { PIN_ENCODER_A: 1, PIN_ENCODER_B: 2, PIN_ENCODER_Z: 3, PIN_MOTOR_PWM_A: 4, PIN_MOTOR_PWM_B: 5, PIN_CURRENT_SENSE: 6, PIN_TEMP_SENSE: 7, PIN_CAN_TX: 8, PIN_CAN_RX: 9, PIN_RS485_TX: 10, PIN_RS485_RX: 11, PIN_STATUS_LED: 12, PIN_FAULT_LED: 13 },
  },
  "esp32-c3-devkitm-1": {
    label: "ESP32-C3 DevKitM",
    pins: { PIN_ENCODER_A: 0, PIN_ENCODER_B: 1, PIN_ENCODER_Z: 2, PIN_MOTOR_PWM_A: 3, PIN_MOTOR_PWM_B: 4, PIN_CURRENT_SENSE: 5, PIN_TEMP_SENSE: 6, PIN_CAN_TX: 7, PIN_CAN_RX: 8, PIN_RS485_TX: 9, PIN_RS485_RX: 10, PIN_STATUS_LED: 11, PIN_FAULT_LED: 12 },
  },
};

function renderPinGrid() {
  const board = $("hw-board").value;
  const pins = BOARD_PINS[board].pins;
  const grid = $("hw-pins");
  grid.innerHTML = "";
  const view = livePinView(pins, state.selected);
  for (const p of view) {
    const row = document.createElement("div");
    row.className = "pin-row" + (p.active ? " active" : "");
    row.dataset.cls = p.cls;
    row.innerHTML =
      `<span class="pin-dot ${p.cls}"></span>` +
      `<label>${p.name}</label>` +
      `<span class="pin-gpio">GPIO ${p.gpio}</span>` +
      `<span class="pin-metric">${p.metric}</span>`;
    grid.appendChild(row);
  }
  renderDataFlow();
}

// Pin -> signal -> motor data-flow panel. Reflects which edges are live given
// the selected motor's state (mirrors the per-pin active logic in pins.js).
function renderDataFlow() {
  const box = $("hw-flow");
  if (!box) return;
  const m = state.selected;
  const live = (metric) => {
    if (!m) return false;
    if (metric === "torque") return m.enabled && Math.abs(m.torque) > 0.01;
    if (metric === "velocity / position" || metric === "position (homing)") return m.enabled && Math.abs(m.velocity) > 0.001;
    if (metric === "temperature") return true;
    if (metric === "command / status frames" || metric === "Modbus frames") return m.enabled;
    if (metric === "enabled state") return m.enabled;
    if (metric === "fault state") return m.fault !== 0;
    return false;
  };
  box.innerHTML = "";
  for (const e of DATA_FLOW) {
    const on = live(e.into);
    const row = document.createElement("div");
    row.className = "flow-row" + (on ? " active" : "");
    const pins = e.pin2 ? `${e.pin} + ${e.pin2}` : e.pin;
    row.innerHTML = `<span class="flow-pins">${pins}</span><span class="flow-arrow">→</span><span class="flow-via">${e.via}</span><span class="flow-arrow">→</span><span class="flow-into">${e.into}</span>`;
    box.appendChild(row);
  }
}

function setupHardware() {
  $("hw-board").onchange = () => {
    renderPinGrid();
    log(`Board set to ${BOARD_PINS[$("hw-board").value].label}`, "ok");
  };
  $("hw-apply").onclick = () => {
    const board = $("hw-board").value;
    const pins = {};
    for (const inp of $("hw-pins").querySelectorAll("input[data-pin]")) {
      pins[inp.dataset.pin] = parseInt(inp.value, 10) || 0;
    }
    state.hw = { board, pins };
    log(`Applied ${BOARD_PINS[board].label} pin map: ` + Object.entries(pins).map(([k, v]) => `${k}=${v}`).join(" "), "ok");
  };
  renderPinGrid();
}

function addLegacyVariant() {
  const key = $("legacy-select").value;
  if (!key || !LEGACY_VARIANTS[key]) return;
  const id = state.fleet.length ? Math.max(...state.fleet.map((m) => m.id)) + 1 : 1;
  const spec = legacySpec(key, id);
  const sim = new MotorSim(spec);
  state.fleet.push(sim);
  if (!state.selected) state.selected = sim;
  log(`Added legacy variant ${spec.model} (incremental encoder)`, "ok");
  renderFleet();
  renderDetail();
}

// ---- webserial -----------------------------------------------------------
async function connectSerial() {
  if (!WebSerialTransport.isSupported()) {
    log("WebSerial not supported in this browser (use Chrome/Edge).", "err");
    return;
  }
  try {
    const t = new WebSerialTransport();
    await t.connect(115200);
    t.onFrame = (f) => onSerialFrame(f);
    state.transport = t;
    state.mode = "serial";
    $("conn-status").textContent = "online";
    $("conn-status").className = "status-pill online";
    log("ESP32 connected over WebSerial.", "ok");
  } catch (e) {
    log("WebSerial connect failed: " + e.message, "err");
  }
}

function onSerialFrame(f) {
  // In simulation we mirror incoming status frames into the selected motor
  // for visualization; a real firmware parser would dispatch by motor id.
  if (f.frameType !== FrameType.STATUS_REPORT) return;
  const dv = new DataView(f.payload.buffer, f.payload.byteOffset, f.payload.byteLength);
  const pos = dv.getInt32(0, true) / 1000;
  const vel = dv.getInt32(4, true) / 1000;
  const torq = dv.getInt16(8, true) / 100;
  const temp = f.payload[10];
  const st = dv.getUint16(11, true);
  const fault = f.payload[13];
  log(`RX status m${f.motorId} pos=${pos.toFixed(2)} vel=${vel.toFixed(2)} T=${temp}°C`);
  if (state.selected && state.selected.id === f.motorId) {
    state.selected.position = pos;
    state.selected.velocity = vel;
    state.selected.torque = torq;
    state.selected.temperature = temp;
    state.selected.status = st;
    state.selected.fault = fault;
    renderDetail();
  }
}

// ---- sidebar module navigation ------------------------------------------
function showModule(name) {
  for (const m of document.querySelectorAll(".module")) {
    m.classList.toggle("hidden", m.dataset.view !== name);
  }
  for (const nav of document.querySelectorAll(".nav-item")) {
    nav.classList.toggle("active", nav.dataset.module === name);
  }
}

function setupSidebar() {
  for (const nav of document.querySelectorAll(".nav-item")) {
    nav.onclick = () => showModule(nav.dataset.module);
  }
}

// ---- boot ----------------------------------------------------------------
function boot() {
  setupSidebar();
  $("btn-sim").onclick = toggleSim;
  $("btn-connect").onclick = connectSerial;
  wireControls();
  $("btn-add-legacy").onclick = addLegacyVariant;
  setupHardware();
  renderCommandSelect();
  renderDocs();
  log("Dashboard ready. Start simulation or connect an ESP32.");
}

boot();
