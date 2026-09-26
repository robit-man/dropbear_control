// Live-server smoke verification for the Dropbear engineering dashboard.
// Run from the repository root while web/serve.py is active.
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import http from "node:http";
import { promisify } from "node:util";

const execFileP = promisify(execFile);
const base = process.env.DASHBOARD_BASE || "http://localhost:8000";

function request(url, method = "GET") {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => resolve({
        status: res.statusCode,
        headers: res.headers,
        body: Buffer.concat(chunks).toString("utf8"),
      }));
    });
    req.on("error", reject);
    req.end();
  });
}

let failures = 0;
function check(name, condition) {
  if (condition) console.log(`ok   ${name}`);
  else {
    console.log(`FAIL ${name}`);
    failures += 1;
  }
}

const index = await request(`${base}/`);
check("index served", index.status === 200);
check(
  "three focused live-state views exposed",
  (index.body.match(/data-view-target=/g) || []).length === 3
    && !index.body.includes('data-view-target="cad"')
    && !index.body.includes('data-view-target="firmware"')
    && !index.body.includes('data-view-target="rl"')
    && !index.body.includes('data-view-target="gr00t"')
    && !index.body.includes('data-view-target="evidence"'),
);
check(
  "ESP32 device console and guarded firmware workflow are exposed",
  index.body.includes('data-view-target="devices"')
    && index.body.includes('id="esp-raw-output"')
    && index.body.includes('id="esp-compile"')
    && index.body.includes('id="esp-compile-status"')
    && index.body.includes('id="esp-upload"'),
);
check(
  "leg state inspection, calibration, and configuration suite are exposed",
  index.body.includes('id="esp-motor-state"')
    && index.body.includes('id="esp-sensor-state"')
    && index.body.includes('id="esp-calibrate"')
    && index.body.includes('id="esp-apply-controller-config"')
    && index.body.includes('id="esp-apply-joint-config"')
    && index.body.includes("CAPTURE + SAVE ALL 5 SENSOR OFFSETS"),
);
check("full Dropbear USD simulation present", index.body.includes("Dropbear closed-loop articulation"));
check("USD robot viewport replaces schematic", index.body.includes('id="robot-canvas"') && !index.body.includes('id="robot-svg"'));
check("STEP-derived CAD viewport present", index.body.includes('id="cad-canvas"'));
check("live controller functional schematic present", index.body.includes('id="controller-diagnostics"'));
check("firmware terminal present", index.body.includes('id="terminal-form"'));
check(
  "authoritative Dropbear kinematic revision shown",
  index.body.includes("KINEMATICS") && index.body.includes("a397be8"),
);
check("separate dropbear_firmware repository is absent", !index.body.includes("dropbear_firmware"));
check("deprecated decorative brand mark removed", !index.body.includes('class="brand-mark"'));
check("Hyperspawn identity applied", index.body.includes("HYPERSPAWN<em>_</em>"));
check("configurable USD resolution control present", index.body.includes('id="usd-resolution"'));
check(
  "passive observation and three-stage control UI are present",
  index.body.includes('id="hardware-observation-toggle"')
    && index.body.includes('id="hardware-control-lock"')
    && index.body.includes('id="hardware-arm-stage2"')
    && index.body.includes('id="hardware-arm-stage3"')
    && (index.body.match(/data-safety-ack=/g) || []).length === 5,
);
check(
  "browser-only zero and dual-angle recording controls are present",
  index.body.includes('id="hardware-zero-torso"')
    && index.body.includes('id="hardware-zero-current"')
    && index.body.includes('id="hardware-record-toggle"')
    && index.body.includes('id="hardware-record-download"')
    && index.body.includes("MOTOR NATIVE UNAVAILABLE"),
);
check("paired foot and X8 telemetry present", index.body.includes('id="left-foot-height"') && index.body.includes('id="right-calf-pair"'));
const belowStageIndex = index.body.indexOf('class="robot-below-stage"');
check(
  "USD status, source verification, and leg telemetry are below the 3D canvas",
  belowStageIndex > index.body.indexOf('id="robot-canvas"')
    && index.body.indexOf('id="robot-load-status"') > belowStageIndex
    && index.body.indexOf('id="physics-runtime-status"') > belowStageIndex
    && index.body.indexOf('class="leg-telemetry"') > belowStageIndex,
);
check(
  "geometry contact telemetry present",
  index.body.includes('id="left-foot-contact"')
    && index.body.includes('id="right-foot-contact"')
    && index.body.includes('id="root-z-offset"'),
);
check(
  "force-contact physics status is visible",
  index.body.includes('id="physics-runtime-status"')
    && index.body.includes("<b>117</b> PHYSICS JOINTS")
    && index.body.includes("<b>56.23</b> KG"),
);
check(
  "separate leg and arm motor categories present",
  index.body.includes('data-motor-category="legs"')
    && index.body.includes('data-motor-category="arms"'),
);
check(
  "browser training labs are unexposed",
  index.body.includes('id="playback-mode"')
    && index.body.includes('id="sim-training-toggle" class="button subtle" aria-expanded="false" hidden')
    && !index.body.includes('data-view-target="rl"')
    && !index.body.includes('data-view-target="gr00t"'),
);
const dashboardStyle = await request(`${base}/css/style.css`);
check(
  "firmware compile progress has a visible animated state",
  dashboardStyle.body.includes("@keyframes esp-compile-spin")
    && dashboardStyle.body.includes(".esp-compile-status.compiling")
    && index.body.includes("aria-live=\"polite\""),
);
const playbackStyle = dashboardStyle.body
  .match(/(?:^|\n)\.playback-mode-button \{([^}]*)\}/)?.[1] || "";
check(
  "playback source reserves locomotion policy mode",
  dashboardStyle.status === 200
    && playbackStyle.includes("background: var(--cyan)")
    && playbackStyle.includes("border: 1px solid var(--cyan)")
    && index.body.includes('id="playback-mode" class="playback-mode-button"')
    && index.body.includes('dropbear-locomotion policy playback')
    && index.body.includes('id="playback-family" class="playback-mode-button"')
    && index.body.includes('data-family="classic" aria-pressed="false" aria-label="Legacy playback family" hidden')
    && !index.body.includes('type="checkbox" id="playback-mode"')
    && !index.body.includes('type="checkbox" id="playback-family"'),
);
check(
  "controller schematic covers live and locked paths",
  index.body.includes("Observation and control boundaries")
    && index.body.includes("TX 0 BYTES")
    && index.body.includes("READ-ONLY HARDWARE / FUNCTIONAL STATUS"),
);
check(
  "persistent RL session controls are present",
  index.body.includes('id="rl-session-list"')
    && index.body.includes('id="rl-session-new"')
    && index.body.includes('id="rl-session-copy"')
    && index.body.includes('id="rl-session-replay"')
    && index.body.includes('id="rl-session-warm-start"'),
);
check(
  "GR00T prompt, CUDA training, and deployment gates are present",
  index.body.includes('data-view="gr00t"')
    && index.body.includes('id="gr00t-prompt-form"')
    && index.body.includes('id="gr00t-training-form"')
    && index.body.includes('id="gr00t-gate-cuda"')
    && index.body.includes('id="gr00t-gate-trt"')
    && index.body.includes('id="gr00t-gate-smoke"')
    && index.body.includes('id="gr00t-gate-isaac"')
    && index.body.includes('id="gr00t-gate-hardware"'),
);

const dropbear = await request(`${base}/js/dropbear.js`);
check("Dropbear simulator module served", dropbear.status === 200);
check("simulator declares exact CAN range", dropbear.body.includes("0x141") && dropbear.body.includes("0x14C"));
check("simulator declares guarded pause", dropbear.body.includes("guarded PAUSE"));
check("simulator implements firmware serial parser", dropbear.body.includes("command(text"));
check(
  "alternating gait has staged contact and swing profile",
  dropbear.body.includes("high knee")
    && dropbear.body.includes("heel prepare")
    && dropbear.body.includes("push off")
    && dropbear.body.includes("calfDiff"),
);

const app = await request(`${base}/js/app.js`);
check(
  "live motor cards separate direct CAN and AS5600 channels",
  app.body.includes('data-field="motor-angle"')
    && app.body.includes('data-field="sensor-angle"')
    && app.body.includes("NO 0x92 REPLY")
    && index.body.includes("DIRECT CAN + AS5600"),
);
check(
  "firmware compile progress reports ready, running, pass, and failure states",
  app.body.includes('compiling: "COMPILING"')
    && app.body.includes('passed: "COMPILE PASSED"')
    && app.body.includes('failed: "COMPILE FAILED"'),
);
check(
  "dashboard calibration and configuration use guarded host endpoints",
  app.body.includes('requestJson("/api/hardware/calibration"')
    && app.body.includes('requestJson("/api/hardware/configuration/inspect"')
    && app.body.includes('requestJson("/api/hardware/configuration/apply"')
    && app.body.includes("calibration-result-v1")
    && app.body.includes("config-records-v1"),
);
const hardwareCalibration = await request(`${base}/js/hardware_calibration.js`);
check(
  "neutral viewer starts with locked knees and an upright torso datum",
  dropbear.body.includes("knee: 0")
    && index.body.includes('id="hardware-zero-torso" type="number" min="-45" max="45" step="0.5" value="0"')
    && hardwareCalibration.body.includes("torsoForwardDeg = 0")
    && app.body.includes("dropbear.control.softwareZero.v6"),
);
check(
  "validated right knee, hip pitch, and yaw hardware-to-USD signs are explicit",
  hardwareCalibration.status === 200
    && hardwareCalibration.body.includes("HARDWARE_TO_USD_DIRECTION")
    && hardwareCalibration.body.includes("hip_pitch: -1")
    && hardwareCalibration.body.includes("knee: -1")
    && hardwareCalibration.body.includes("hip_yaw: -1"),
);
check("dashboard instantiates CAD viewer", app.body.includes("new CadViewer"));
check(
  "dashboard renders controller diagnostics without a second WebGL context",
  app.body.includes("renderControllerDiagnostics") && !app.body.includes("new Board3D"),
);
check("dashboard instantiates full USD robot viewer", app.body.includes("new Robot3D"));
check("dashboard exposes inspectable twin", app.body.includes("window.dropbearTwin"));
check("dashboard exposes inspectable arm motor state", app.body.includes("armMotorBindings: DROPBEAR_ARM_MOTOR_BINDINGS"));
check(
  "dashboard applies only validated passive hardware observations",
  app.body.includes('requestJson("/api/hardware/control/advance"')
    && app.body.includes('requestJson("/api/hardware/command"')
    && app.body.includes("validateHardwareObservation")
    && app.body.includes("applyHardwareObservation"),
);
const softwareViewers = await request(`${base}/js/software_viewers.js`);
check(
  "measured-state fallback is served when WebGL2 is unavailable",
  softwareViewers.status === 200
    && app.body.includes("supportsWebGL2")
    && softwareViewers.body.includes("DROPBEAR MEASURED-STATE VIEW · 2D FALLBACK")
    && softwareViewers.body.includes("UNOBSERVED"),
);
check("USD resolution persists and updates renderer", app.body.includes("dropbear-usd-resolution") && app.body.includes("setResolutionScale"));
check("geometry contact feeds the load-cell simulator", app.body.includes("sim.setFootContactState(robot.groundContact)"));
check(
  "browser policy player maps free-root state onto the USD",
  app.body.includes("new RLPolicyPlayer")
    && app.body.includes("setExternalRootPose")
    && app.body.includes('sim.scenario = "rl-policy"')
    && app.body.includes("policyEpochsComplete"),
);
check(
  "dashboard submits the selected reward profile",
  app.body.includes("rewardWeightDefaults")
    && app.body.includes('rewardWeights: readRewardWeights("rl")')
    && app.body.includes('rewardWeights: readRewardWeights("sim-rl")'),
);
check(
  "dashboard can recall, warm-start, and replay stored sessions",
  app.body.includes('requestJson("/api/rl/sessions")')
    && app.body.includes("applyRLSessionConfig")
    && app.body.includes("warmStartConfig")
    && app.body.includes("replaySelectedRLSession"),
);
check(
  "dashboard initializes GR00T lab and fail-closed prompt preview",
  app.body.includes("setupGr00tLab")
    && app.body.includes('"dropbear:prompt-plan"')
    && app.body.includes("GR00T_PROMPT_PREVIEW_PRESETS")
    && app.body.includes("GR00T_PROMPT_PREVIEW_TURN_EPSILON_RPS")
    && app.body.includes("no browser preset matches")
    && app.body.includes("The plan was not played.")
    && !app.body.includes('["walk", "circle", "turn"].includes(plan.primitive)'),
);

const gr00tStatusResponse = await request(`${base}/api/gr00t/status`);
let gr00tStatus;
try {
  gr00tStatus = JSON.parse(gr00tStatusResponse.body);
} catch {
  gr00tStatus = null;
}
check(
  "GR00T CUDA and safety gate status API served",
  gr00tStatusResponse.status === 200
    && gr00tStatus?.schema === "dropbear-gr00t-runtime-v1"
    && gr00tStatus?.safety?.hardwareCommandsEnabled === false
    && Boolean(gr00tStatus?.training),
);

const hardwareObservationResponse = await request(`${base}/api/hardware/observation`);
const hardwareObservation = JSON.parse(hardwareObservationResponse.body);
check(
  "hardware observation API keeps motion output locked",
  hardwareObservationResponse.status === 200
    && hardwareObservation.schema === "dropbear-hardware-observation-v2"
    && hardwareObservation.mode === "read_only_with_diagnostic_queries"
    && hardwareObservation.writeCapable === false
    && hardwareObservation.motionWriteCapable === false,
);
const hardwareControlResponse = await request(`${base}/api/hardware/control/status`);
const hardwareControl = JSON.parse(hardwareControlResponse.body);
check(
  "hardware control API stays physically locked",
  hardwareControlResponse.status === 200
    && hardwareControl.schema === "dropbear-frontend-control-gate-v1"
    && hardwareControl.hardwareOutputEnabled === false
    && hardwareControl.physicalTransport === "not_installed",
);

const rlStatus = await request(`${base}/api/rl/status`);
let rlState;
try {
  rlState = JSON.parse(rlStatus.body);
} catch {
  rlState = null;
}
check(
  "local RL training status API served",
  rlStatus.status === 200
    && Boolean(rlState)
    && Array.isArray(rlState.events),
);
const rlSessionsResponse = await request(`${base}/api/rl/sessions`);
let rlSessions;
try {
  rlSessions = JSON.parse(rlSessionsResponse.body);
} catch {
  rlSessions = null;
}
check(
  "persistent RL session index API served",
  rlSessionsResponse.status === 200
    && rlSessions?.schema === "dropbear-rl-session-index-v1"
    && Array.isArray(rlSessions.sessions),
);
const rlPolicy = await request(`${base}/js/rl_policy.js`);
check(
  "policy interpolation runtime served",
  rlPolicy.status === 200
    && rlPolicy.body.includes("dropbear-walk-policy-v2")
    && rlPolicy.body.includes("interpolateFrame"),
);

const usdBindings = await request(`${base}/js/dropbear_usd.js`);
const armBindingSource = usdBindings.body.split("export const DROPBEAR_ARM_MOTOR_BINDINGS")[1]?.split("export function dropbearUsdBinding")[0] || "";
check("USD binding module served", usdBindings.status === 200);
check(
  "arm map declares eight X8 and two torso X10 drives",
  (armBindingSource.match(/motor: "RMD-X8"/g) || []).length === 8
    && (armBindingSource.match(/motor: "RMD-X10"/g) || []).length === 2
    && (armBindingSource.match(/mount: "torso"/g) || []).length === 2,
);
check(
  "shoulder-pitch source semantics remain explicit",
  usdBindings.body.includes('semanticJoint: "shoulder_pitch", usdJoint: "LH_yaw"')
    && usdBindings.body.includes('semanticJoint: "shoulder_pitch", usdJoint: "RH_yaw"'),
);

const robotModule = await request(`${base}/js/robot_3d.js`);
check(
  "robot viewer builds arm shafts, elbow closures, and switchable root modes",
  robotModule.body.includes("_buildArmMotorShafts")
    && robotModule.body.includes("VerticalGroundConstraint")
    && robotModule.body.includes("_rawFootPatches")
    && robotModule.body.includes("setVerticalConstraintEnabled")
    && robotModule.body.includes('"FREE_ROOT_POLICY"')
    && robotModule.body.includes('"FREE_ROOT_FORCE_CONTACT"'),
);

const groundConstraint = await request(`${base}/js/vertical_ground_constraint.js`);
check(
  "Z-only unilateral ground constraint served",
  groundConstraint.status === 200
    && groundConstraint.body.includes('guide: "Z_ONLY"')
    && groundConstraint.body.includes("heelLoadKg")
    && groundConstraint.body.includes("toeLoadKg"),
);
const forceContact = await request(`${base}/js/force_ground_contact.js`);
check(
  "free-root force contact integrates gravity and unilateral normal force",
  forceContact.status === 200
    && forceContact.body.includes("stiffnessNpm")
    && forceContact.body.includes("normalForceN")
    && forceContact.body.includes("verticalAccelerationMps2")
    && forceContact.body.includes("correctionZ"),
);

const physicsStatusResponse = await request(`${base}/api/physics/status`);
let physicsStatus;
try {
  physicsStatus = JSON.parse(physicsStatusResponse.body);
} catch {
  physicsStatus = null;
}
check(
  "verified source-USD physics admission status served",
  physicsStatusResponse.status === 200
    && physicsStatus?.sourceUsd?.verified === true
    && physicsStatus?.groundTruth?.rigidBodies === 93
    && physicsStatus?.groundTruth?.authoredMasses === 93
    && physicsStatus?.groundTruth?.collisionGroups === 93
    && physicsStatus?.groundTruth?.physicsJoints === 117
    && physicsStatus?.groundTruth?.forceDrives === 28,
);

const robotGlb = await request(`${base}/assets/robot/dropbear-usd-browser.glb`, "HEAD");
const robotManifestResponse = await request(`${base}/assets/robot/dropbear-articulation.json`);
const physicsManifestResponse = await request(`${base}/assets/robot/dropbear-physics-manifest.json`);
check("optimized Dropbear USD cache served", robotGlb.status === 200 && Number(robotGlb.headers["content-length"]) > 2_500_000);
let robotManifest;
try {
  robotManifest = JSON.parse(robotManifestResponse.body);
} catch {
  robotManifest = null;
}
check("USD articulation manifest is valid JSON", robotManifestResponse.status === 200 && Boolean(robotManifest));
const physicsManifest = JSON.parse(physicsManifestResponse.body);
check(
  "source-USD mass, inertia, collision, drive contract is retained",
  physicsManifestResponse.status === 200
    && physicsManifest.statistics.totalAuthoredMassKg > 56.22
    && physicsManifest.bodies.length === 93
    && physicsManifest.joints.length === 117
    && physicsManifest.admission.exactCollisionGeometryRequired === true,
);
check(
  "USD topology statistics retained",
  robotManifest?.statistics?.rigidBodies === 93
    && robotManifest?.statistics?.physicsJoints === 116
    && robotManifest?.statistics?.closureConstraints === 27,
);
check("all 12 CAN motors bind to USD joints", robotManifest?.canBindings?.length === 12);
check(
  "all ten arm motors bind to existing USD joints without invented CAN IDs",
  robotManifest?.armMotorBindings?.length === 10
    && robotManifest.armMotorBindings.every(
      (binding) => binding.firmwareCanId === null
        && robotManifest.joints.some((joint) => joint.name === binding.usdJoint),
    ),
);
check(
  "arm manifest retains eight X8 and two torso X10 drives",
  robotManifest?.armMotorBindings?.filter((binding) => binding.motor === "RMD-X8").length === 8
    && robotManifest?.armMotorBindings?.filter(
      (binding) => binding.motor === "RMD-X10" && binding.mount === "torso",
    ).length === 2,
);
check(
  "both elbow motors drive retained three-constraint closed loops",
  robotManifest?.browserKinematics?.armLinkages?.length === 2
    && robotManifest.browserKinematics.armLinkages.every(
      (linkage) => linkage.elbowMotor?.endsWith("Revolute41")
        && linkage.passiveJoints?.length === 5
        && linkage.closureConstraints?.length === 3,
    )
    && robotManifest.armMotorBindings.filter((binding) => binding.closedLoop).length === 2,
);
check(
  "four calf CAN nodes bind to X8 driver axes",
  JSON.stringify(robotManifest?.canBindings?.slice(0, 4).map((binding) => binding.usdJoint))
    === JSON.stringify(["LL_Revolute81", "LL_Revolute67", "RL_Revolute67", "RL_Revolute81"]),
);
check(
  "three-point calf linkage topology retained",
  robotManifest?.browserKinematics?.calfLinkages?.length === 2
    && robotManifest.browserKinematics.calfLinkages.every(
      (linkage) => linkage.inner?.motorCrank && linkage.outer?.motorCrank && linkage.footPivot,
    ),
);
check(
  "corrected locomotion USD revision retained",
  robotManifest?.source?.commit === "a397be863fed2d328c2e8f62c3db2f1e23575eb1"
    && robotManifest?.source?.sha256 === "45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f",
);

const motorCadManifestResponse = await request(`${base}/assets/cad/dropbear-motor-cad.json`);
const motorCadManifest = JSON.parse(motorCadManifestResponse.body);
check(
  "X8 and X10 Dropbear motor CAD manifest served",
  motorCadManifestResponse.status === 200
    && motorCadManifest.motors["x8-pro"].axis === "y"
    && motorCadManifest.motors["x10-s2"].axis === "z",
);
for (const key of ["x8-pro", "x10-s2"]) {
  const housing = await request(`${base}/assets/cad/${key}/housing.glb`, "HEAD");
  const output = await request(`${base}/assets/cad/${key}/output.glb`, "HEAD");
  check(`${key} housing/output STEP previews served`, housing.status === 200
    && output.status === 200
    && Number(housing.headers["content-length"]) > 50_000
    && Number(output.headers["content-length"]) > 10_000);
}
const x8Step = await request(`${base}/cad-source/dropbear-x8-pro.step`, "HEAD");
const x10Step = await request(`${base}/cad-source/dropbear-x10-s2.step`, "HEAD");
check("full X8/X10 source STEP caches served", x8Step.status === 200
  && x10Step.status === 200
  && Number(x8Step.headers["content-length"]) > 0
  && Number(x10Step.headers["content-length"]) > 0);

const three = await request(`${base}/node_modules/three/build/three.module.js`, "HEAD");
check("local Three.js dependency served", three.status === 200);

try {
  const testPath = fileURLToPath(new URL("./dropbear.test.mjs", import.meta.url));
  const { stdout } = await execFileP(process.execPath, [testPath], { cwd: process.cwd() });
  check("Dropbear source-map and runtime tests pass", stdout.includes("DROPBEAR DIGITAL TWIN TESTS PASSED"));
} catch (error) {
  check("Dropbear source-map and runtime tests pass", false);
  console.log(`${error.stdout || ""}${error.stderr || ""}`);
}

if (failures) {
  console.log(`DASHBOARD VERIFY FAILED: ${failures} check(s)`);
  process.exit(1);
}
console.log("DASHBOARD VERIFY PASSED");
