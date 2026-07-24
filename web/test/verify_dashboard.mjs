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
check("five engineering views present", (index.body.match(/data-view="/g) || []).length === 5);
check("full Dropbear USD simulation present", index.body.includes("Dropbear closed-loop articulation"));
check("USD robot viewport replaces schematic", index.body.includes('id="robot-canvas"') && !index.body.includes('id="robot-svg"'));
check("STEP-derived CAD viewport present", index.body.includes('id="cad-canvas"'));
check("1:1 controller viewport present", index.body.includes('id="board-canvas"'));
check("firmware terminal present", index.body.includes('id="terminal-form"'));
check("current Dropbear source revision shown", index.body.includes("13cf5ec"));
check("separate dropbear_firmware repository is absent", !index.body.includes("dropbear_firmware"));
check("deprecated decorative brand mark removed", !index.body.includes('class="brand-mark"'));
check("Hyperspawn identity applied", index.body.includes("HYPERSPAWN<em>_</em>"));
check("configurable USD resolution control present", index.body.includes('id="usd-resolution"'));
check("paired foot and X8 telemetry present", index.body.includes('id="left-foot-height"') && index.body.includes('id="right-calf-pair"'));
check(
  "geometry contact telemetry present",
  index.body.includes('id="left-foot-contact"')
    && index.body.includes('id="right-foot-contact"')
    && index.body.includes('id="root-z-offset"'),
);
check(
  "separate leg and arm motor categories present",
  index.body.includes('data-motor-category="legs"')
    && index.body.includes('data-motor-category="arms"'),
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
check("dashboard instantiates CAD viewer", app.body.includes("new CadViewer"));
check("dashboard instantiates controller viewer", app.body.includes("new Board3D"));
check("dashboard instantiates full USD robot viewer", app.body.includes("new Robot3D"));
check("dashboard exposes inspectable twin", app.body.includes("window.dropbearTwin"));
check("dashboard exposes inspectable arm motor state", app.body.includes("armMotorBindings: DROPBEAR_ARM_MOTOR_BINDINGS"));
check("USD resolution persists and updates renderer", app.body.includes("dropbear-usd-resolution") && app.body.includes("setResolutionScale"));
check("geometry contact feeds the load-cell simulator", app.body.includes("sim.setFootContactState(robot.groundContact)"));

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
  "robot viewer builds arm shafts and vertical ground contact",
  robotModule.body.includes("_buildArmMotorShafts")
    && robotModule.body.includes("VerticalGroundConstraint")
    && robotModule.body.includes("_rawFootPatches"),
);

const groundConstraint = await request(`${base}/js/vertical_ground_constraint.js`);
check(
  "Z-only unilateral ground constraint served",
  groundConstraint.status === 200
    && groundConstraint.body.includes('guide: "Z_ONLY"')
    && groundConstraint.body.includes("heelLoadKg")
    && groundConstraint.body.includes("toeLoadKg"),
);

const robotGlb = await request(`${base}/assets/robot/dropbear-usd-browser.glb`, "HEAD");
const robotManifestResponse = await request(`${base}/assets/robot/dropbear-articulation.json`);
check("optimized Dropbear USD cache served", robotGlb.status === 200 && Number(robotGlb.headers["content-length"]) > 2_500_000);
let robotManifest;
try {
  robotManifest = JSON.parse(robotManifestResponse.body);
} catch {
  robotManifest = null;
}
check("USD articulation manifest is valid JSON", robotManifestResponse.status === 200 && Boolean(robotManifest));
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
check("ground-truth RL revision retained", robotManifest?.source?.commit === "3c37aedce6d445205671d5714d05ae28b8c90e2c");

const housing = await request(`${base}/assets/cad/housing-step-preview.glb`, "HEAD");
const output = await request(`${base}/assets/cad/output-step-preview.glb`, "HEAD");
check("housing STEP preview cache served", housing.status === 200 && Number(housing.headers["content-length"]) > 1_000_000);
check("output STEP preview cache served", output.status === 200 && Number(output.headers["content-length"]) > 400_000);

const housingStep = await request(`${base}/cad-candidate/step-e7d99e7e0d9683017c1a/housing-candidate.step`, "HEAD");
const outputStep = await request(`${base}/cad-candidate/step-e7d99e7e0d9683017c1a/output-candidate.step`, "HEAD");
check("full housing STEP cache served", housingStep.status === 200 && Number(housingStep.headers["content-length"]) > 0);
check("full output STEP cache served", outputStep.status === 200 && Number(outputStep.headers["content-length"]) > 0);

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
