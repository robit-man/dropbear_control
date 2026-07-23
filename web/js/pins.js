// web/js/pins.js
//
// Live pin / signal model for the ESP32 30-pin DevKitC hardware view.
//
// The dashboard's Hardware panel shows the physical pin map. This module turns
// that static map into a *live* signal view: each pin gets a signal class
// (PWM / quadrature / analog / digital / comms), an "active" predicate, and a
// per-pin metric string derived from the selected motor's simulation state.
//
// It is intentionally decoupled from the simulation physics (sim.js) — it only
// *reads* MotorSim telemetry and maps it onto pins. That keeps the hardware
// view honest: a pin is "active" only when the signal it carries is actually
// moving, and the metric reflects the real value on that wire.

// Signal classes drive both the color coding and the metric formatter.
export const SignalClass = {
  PWM: "pwm",           // motor phase / bridge drive (active when torque != 0)
  QUAD: "quad",         // quadrature encoder A/B/Z (active when |vel| > 0)
  ANALOG: "analog",     // current / temperature sense (always live)
  COMMS: "comms",       // CAN / RS485 / EtherCAT transceivers
  LED: "led",           // status / fault indicators
  BTN: "btn",           // enable / fault-reset buttons (UI only)
};

// Per-pin metadata. `cls` is the SignalClass; `signal` is the human label of
// what the wire carries; `metric` names the telemetry field it maps to.
const PIN_META = {
  PIN_MOTOR_PWM_A:  { cls: SignalClass.PWM,    signal: "Motor bridge A (PWM)",     metric: "torque" },
  PIN_MOTOR_PWM_B:  { cls: SignalClass.PWM,    signal: "Motor bridge B (PWM)",     metric: "torque" },
  PIN_ENCODER_A:    { cls: SignalClass.QUAD,   signal: "Encoder A (quad)",         metric: "velocity" },
  PIN_ENCODER_B:    { cls: SignalClass.QUAD,   signal: "Encoder B (quad)",         metric: "velocity" },
  PIN_ENCODER_Z:    { cls: SignalClass.QUAD,   signal: "Encoder Z (index)",        metric: "position" },
  PIN_CURRENT_SENSE:{ cls: SignalClass.ANALOG, signal: "Current sense (ADC)",      metric: "torque" },
  PIN_TEMP_SENSE:   { cls: SignalClass.ANALOG, signal: "Temp sense (ADC)",         metric: "temperature" },
  PIN_CAN_TX:       { cls: SignalClass.COMMS,  signal: "CAN TX",                   metric: "comm" },
  PIN_CAN_RX:       { cls: SignalClass.COMMS,  signal: "CAN RX",                   metric: "comm" },
  PIN_RS485_TX:     { cls: SignalClass.COMMS,  signal: "RS485 TX (DE)",            metric: "comm" },
  PIN_RS485_RX:     { cls: SignalClass.COMMS,  signal: "RS485 RX",                 metric: "comm" },
  PIN_RS485_DE_RE:  { cls: SignalClass.COMMS,  signal: "RS485 DE/RE",              metric: "comm" },
  PIN_STATUS_LED:   { cls: SignalClass.LED,    signal: "Status LED",               metric: "state" },
  PIN_FAULT_LED:    { cls: SignalClass.LED,    signal: "Fault LED",                metric: "fault" },
  PIN_ENABLE_BTN:   { cls: SignalClass.BTN,    signal: "Enable button",            metric: "enabled" },
  PIN_FAULT_RESET_BTN:{ cls: SignalClass.BTN,  signal: "Fault-reset button",       metric: "fault" },
};

// Build the ordered pin list for a board preset (from app.js BOARD_PINS).
export function buildPinList(boardPins) {
  return Object.entries(boardPins).map(([name, gpio]) => ({
    name,
    gpio,
    ...(PIN_META[name] || { cls: "unknown", signal: name, metric: null }),
  }));
}

// Decide whether a pin is "active" given the selected motor's sim state.
function isActive(pin, m) {
  if (!m) return false;
  switch (pin.cls) {
    case SignalClass.PWM:
      // Bridge is driven whenever the motor is enabled and producing torque.
      // In torque mode the sim holds torque even at zero velocity, so gate on
      // torque only (not velocity) to keep the bridge lit under static load.
      return m.enabled && Math.abs(m.torque) > 0.01;
    case SignalClass.QUAD:
      return m.enabled && Math.abs(m.velocity) > 0.001;
    case SignalClass.ANALOG:
      return true; // sense lines are always live while powered
    case SignalClass.COMMS:
      return m.enabled; // link is exercised whenever the motor is driven
    case SignalClass.LED:
      if (pin.metric === "fault") return m.fault !== 0;
      return m.enabled && m.fault === 0; // status LED lit when enabled & healthy
    case SignalClass.BTN:
      if (pin.metric === "enabled") return m.enabled;
      return m.fault !== 0;
    default:
      return false;
  }
}

// Format the per-pin metric string from the sim state.
function metricText(pin, m) {
  if (!m) return "—";
  switch (pin.metric) {
    case "torque":
      return (Math.abs(m.torque)).toFixed(2) + " N·m";
    case "velocity":
      return m.velocity.toFixed(2) + " rad/s";
    case "position":
      return (m.position % (Math.PI * 2)).toFixed(2) + " rad";
    case "temperature":
      return m.temperature.toFixed(0) + " °C";
    case "comm":
      return m.enabled ? "tx/rx" : "idle";
    case "state":
      return m.enabled ? "on" : "off";
    case "fault":
      return m.fault !== 0 ? "FAULT" : "ok";
    case "enabled":
      return m.enabled ? "held" : "released";
    default:
      return "—";
  }
}

// Produce the live view model consumed by app.js render functions.
// Returns an array of { name, gpio, cls, signal, active, metric }.
export function livePinView(boardPins, motor) {
  return buildPinList(boardPins).map((pin) => ({
    name: pin.name,
    gpio: pin.gpio,
    cls: pin.cls,
    signal: pin.signal,
    active: isActive(pin, motor),
    metric: metricText(pin, motor),
  }));
}

// Data-flow edges: pin -> signal -> motor state field. Used by the
// "Signal / Data Flow" panel to draw the wiring from physical pins up into
// the motor model.
export const DATA_FLOW = [
  { pin: "PIN_MOTOR_PWM_A", pin2: "PIN_MOTOR_PWM_B", via: "H-bridge PWM", into: "torque" },
  { pin: "PIN_ENCODER_A", pin2: "PIN_ENCODER_B", via: "Quadrature decode", into: "velocity / position" },
  { pin: "PIN_ENCODER_Z", pin2: null, via: "Index pulse", into: "position (homing)" },
  { pin: "PIN_CURRENT_SENSE", pin2: null, via: "ADC sample", into: "torque (feedback)" },
  { pin: "PIN_TEMP_SENSE", pin2: null, via: "ADC sample", into: "temperature" },
  { pin: "PIN_CAN_TX", pin2: "PIN_CAN_RX", via: "CAN bus", into: "command / status frames" },
  { pin: "PIN_RS485_TX", pin2: "PIN_RS485_RX", via: "RS485 (DE/RE)", into: "Modbus frames" },
  { pin: "PIN_STATUS_LED", pin2: null, via: "GPIO", into: "enabled state" },
  { pin: "PIN_FAULT_LED", pin2: null, via: "GPIO", into: "fault state" },
];
