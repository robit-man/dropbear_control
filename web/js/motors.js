// web/js/motors.js
//
import { BROWSER_TOY_BACKEND } from "./plant_backends.generated.js";

// Motor catalog derived from the per-series contracts in contracts/.
// Spec values (power range, gearbox type, reduction ratios) come from the
// MOTOR_*.md files; control limits (maxTorque / maxVelocity / inertia) are
// representative defaults for the simulation engine, not measured datasheet
// values. The executable evidence fields below prevent them from being treated
// as a physical actuator plant or support claim.

export const TOY_PLANT_EVIDENCE = Object.freeze({
  simulationBackendId: BROWSER_TOY_BACKEND.backend_id,
  simulationBackendKind: BROWSER_TOY_BACKEND.kind,
  simulationEvidenceClass: BROWSER_TOY_BACKEND.evidence_class,
  simulationSubstitutionScope: BROWSER_TOY_BACKEND.substitution_scope,
  simulationParameterSetId: BROWSER_TOY_BACKEND.parameter_set_id,
  physicalPlantSupported: false,
  physicalParameterSource: null,
  physicalValidationEvidence: null,
});

export function assertToySimulationSpec(spec) {
  if (
    !spec
    || spec.simulationBackendId !== BROWSER_TOY_BACKEND.backend_id
    || spec.simulationBackendKind !== "toy_demo"
    || spec.simulationSubstitutionScope !== "browser-visualization-only"
    || spec.simulationParameterSetId !== null
  ) {
    throw new Error("EXACT_TOY_BACKEND_IDENTITY_REQUIRED");
  }
  if (!spec || spec.simulationEvidenceClass !== TOY_PLANT_EVIDENCE.simulationEvidenceClass) {
    throw new Error("SIMULATION_EVIDENCE_CLASS_REQUIRED");
  }
  if (
    BROWSER_TOY_BACKEND.models_physical_dynamics !== false
    || BROWSER_TOY_BACKEND.physically_validated !== false
    || spec.physicalPlantSupported !== false
    || spec.physicalParameterSource !== null
    || spec.physicalValidationEvidence !== null
  ) {
    throw new Error("UNSUPPORTED_PHYSICAL_PLANT_CLAIM");
  }
  for (const field of ["maxTorque", "maxVelocity", "inertia"]) {
    if (!Number.isFinite(spec[field]) || spec[field] <= 0) {
      throw new Error(`INVALID_TOY_PARAMETER_${field}`);
    }
  }
  return true;
}

export const MOTOR_SERIES = {
  "RMD-X": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-X",
    gearbox: "Planetary",
    power: "10W – 2kW",
    reductionRatios: [5, 10, 20, 25, 50, 100, 125, 200, 250, 500],
    // --- simulation parameters (not datasheet-measured) ---
    maxTorque: 12, // N·m
    maxVelocity: 25, // rad/s
    inertia: 0.02, // kg·m²
  },
  RH: {
    ...TOY_PLANT_EVIDENCE,
    name: "RH",
    gearbox: "Harmonic",
    power: "50W – 1.5kW",
    reductionRatios: [50, 80, 100, 120, 160],
    maxTorque: 30,
    maxVelocity: 15,
    inertia: 0.05,
  },
  CEM: {
    ...TOY_PLANT_EVIDENCE,
    name: "CEM",
    gearbox: "Cycloid",
    power: "100W – 1.2kW",
    reductionRatios: [30, 50, 80, 100],
    maxTorque: 40,
    maxVelocity: 10,
    inertia: 0.08,
  },
  "RMD-H": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-H",
    gearbox: "Direct Drive (Hollow)",
    power: "200W – 2kW",
    reductionRatios: [1],
    maxTorque: 50,
    maxVelocity: 20,
    inertia: 0.1,
  },
  "RMD-L": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-L",
    gearbox: "Direct Drive",
    power: "100W – 1.5kW",
    reductionRatios: [1],
    maxTorque: 18,
    maxVelocity: 30,
    inertia: 0.03,
  },
  FL: {
    ...TOY_PLANT_EVIDENCE,
    name: "FL",
    gearbox: "Linear",
    power: "50W – 1kW",
    reductionRatios: [1],
    maxTorque: 25,
    maxVelocity: 8,
    inertia: 0.04,
  },
};

// Decode an EPS model number per the contract format:
//   EPS-{SERIES}-{PowerClass}-{Ratio/Bore/Stroke}-{Brake}-{DriveType}-{Comm}-{EncoderBits}
// Returns null if the string is not a recognizable EPS model.
export function decodeModel(model) {
  const parts = String(model).trim().split("-");
  if (parts.length < 8 || parts[0] !== "EPS") return null;
  const series = parts[1];
  if (!MOTOR_SERIES[series]) return null;
  return {
    series,
    powerClass: parts[2],
    ratio: parts[3],
    brake: parts[4] === "1",
    driveType: parts[5],
    comm: parts[6],
    encoderBits: parts[7],
  };
}

// Build a default fleet: one motor per series, with a representative model
// number and motor id (1..6). Used to seed the dashboard in simulation mode.
export function defaultFleet() {
  const series = Object.keys(MOTOR_SERIES);
  return series.map((s, i) => {
    const spec = MOTOR_SERIES[s];
    const ratio = spec.reductionRatios[spec.reductionRatios.length - 1];
    const model = `EPS-${s}-3-${ratio}-0-M-C-17`;
    return {
      id: i + 1,
      series: s,
      model,
      encoderType: "absolute",
      encoderResolution: 17,
      ...spec,
    };
  });
}

// Legacy RMD-X variants (past hardware revisions) that shipped with
// INCREMENTAL encoders only — no absolute encoder. The current RMD-X contract
// (MOTOR_RMD_X_CONTRACT.md §3.3) lists only 14/17/18-bit ABSOLUTE encoders,
// so these older units are modeled separately here. The dashboard's
// "Legacy Variants" picker adds them to the fleet so they can still be
// configured and AS5600-calibrated.
//
// encoderResolution for incremental units is given in PPR (pulses/rev).
export const LEGACY_VARIANTS = {
  "RMD-X6": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-X6 (Legacy)",
    series: "RMD-X",
    gearbox: "Planetary",
    model: "EPS-RMD-X-3-20-0-M-C-INC",
    encoderType: "incremental",
    encoderResolution: 1000, // PPR (incremental quadrature)
    power: "100W – 300W",
    reductionRatios: [20, 25, 50],
    maxTorque: 6,
    maxVelocity: 22,
    inertia: 0.025,
  },
  "RMD-X8": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-X8 (Legacy)",
    series: "RMD-X",
    gearbox: "Planetary",
    model: "EPS-RMD-X-5-50-0-M-C-INC",
    encoderType: "incremental",
    encoderResolution: 2000,
    power: "300W – 500W",
    reductionRatios: [50, 100, 125],
    maxTorque: 9,
    maxVelocity: 20,
    inertia: 0.03,
  },
  "RMD-X10": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-X10 (Legacy)",
    series: "RMD-X",
    gearbox: "Planetary",
    model: "EPS-RMD-X-8-100-0-M-C-INC",
    encoderType: "incremental",
    encoderResolution: 2000,
    power: "700W – 1kW",
    reductionRatios: [100, 125, 200],
    maxTorque: 12,
    maxVelocity: 18,
    inertia: 0.04,
  },
  "RMD-X10Pro": {
    ...TOY_PLANT_EVIDENCE,
    name: "RMD-X10 Pro (Legacy)",
    series: "RMD-X",
    gearbox: "Planetary",
    model: "EPS-RMD-X-10-100-0-M-C-INC",
    encoderType: "incremental",
    encoderResolution: 4000,
    power: "1kW – 1.2kW",
    reductionRatios: [100, 125, 200, 250],
    maxTorque: 16,
    maxVelocity: 16,
    inertia: 0.05,
  },
};

// Build a motor spec for a legacy variant with a caller-assigned id.
export function legacySpec(key, id) {
  const v = LEGACY_VARIANTS[key];
  if (!v) return null;
  return { id, series: v.series, model: v.model, ...v };
}
