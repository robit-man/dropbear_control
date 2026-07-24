import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:8000";
const OUT = process.env.VISUAL_OUT || "/tmp/dropbear-visual-review";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(`console: ${message.text()}`);
});
page.on("pageerror", (error) => errors.push(`page: ${error.message}`));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForFunction(() => Boolean(window.dropbearTwin?.sim));
await page.waitForFunction(() => window.dropbearTwin?.robot?.ready === true);
await page.waitForFunction(() => window.dropbearTwin?.robot?.poseVersion > 2);
await page.waitForFunction(() => window.dropbearTwin?.robot?.groundContact?.valid === true);
await page.waitForFunction(() => window.dropbearTwin?.sim?.loadCells?.reduce((sum, value) => sum + value, 0) > 41);
await page.locator("#usd-resolution").fill("150");
await page.waitForFunction(() => window.dropbearTwin.robot.resolutionScale === 1.5);
if ((await page.locator("#usd-resolution-output").textContent()) !== "150%") {
  throw new Error("USD resolution output did not update");
}
await page.evaluate(() => {
  window.dropbearTwin.robot.fit();
  window.dropbearTwin.robot.renderer.render(
    window.dropbearTwin.robot.scene,
    window.dropbearTwin.robot.camera,
  );
});
await page.waitForTimeout(250);

await page.screenshot({ path: `${OUT}/01-guarded-sim.png` });
if ((await page.locator(".joint-card").count()) !== 12) throw new Error("Expected twelve joint cards");
if ((await page.locator("#system-state").textContent())?.trim() !== "GUARDED PAUSE") throw new Error("Guarded pause missing");
if (!(await page.locator("#robot-load-status").textContent())?.includes("294,204")) throw new Error("Full USD model did not load");
const guardedContact = await page.evaluate(() => ({
  contact: window.dropbearTwin.robot.groundContact,
  markerCount: window.dropbearTwin.robot.contactMarkers.size,
  loadCellTotal: window.dropbearTwin.sim.loadCells.reduce((sum, value) => sum + value, 0),
}));
if (guardedContact.contact.guide !== "Z_ONLY") throw new Error("Expected Z-only root guide");
if (guardedContact.markerCount !== 4) throw new Error("Expected heel/toe markers for both feet");
if (Math.abs(guardedContact.loadCellTotal - 42) > 0.01) {
  throw new Error(`Contact loads do not resolve robot mass: ${guardedContact.loadCellTotal}`);
}
if (Math.min(
  guardedContact.contact.left.heelHeightMm,
  guardedContact.contact.left.toeHeightMm,
  guardedContact.contact.right.heelHeightMm,
  guardedContact.contact.right.toeHeightMm,
) < 0) {
  throw new Error("Unilateral ground constraint allowed foot penetration");
}
const initialUsdPose = await page.evaluate(() => Array.from(
  window.dropbearTwin.robot.bodyGroups
    .get("/humanoid/LL_RMD_X10_S2_MIR4__3_Stator_1").matrix.elements,
));
const initialCalfPose = await page.evaluate(() => Array.from(
  window.dropbearTwin.robot.bodyGroups
    .get("/humanoid/LL_calf_motor_driver_ext_2").matrix.elements,
));

await page.click('[data-motor-category="arms"]');
if ((await page.locator(".arm-card").count()) !== 10) throw new Error("Expected ten arm motor cards");
if ((await page.locator(".arm-card.x10").count()) !== 2) throw new Error("Expected two torso X10 shoulder-pitch drives");
const armShaftCount = await page.evaluate(() => window.dropbearTwin.robot.armMotorShafts.size);
if (armShaftCount !== 10) throw new Error(`Expected ten arm motor shafts, got ${armShaftCount}`);
if (!(await page.locator("#selected-name").textContent())?.includes("Left shoulder pitch")) {
  throw new Error("Torso shoulder-pitch motor did not select");
}
if (!(await page.locator("#selected-can").textContent())?.includes("RMD-X10")) {
  throw new Error("Torso shoulder-pitch motor is not identified as X10");
}
await page.waitForFunction(() => document.querySelector("#sel-sensor")?.textContent?.includes("CAN UNMAPPED"));
if (!(await page.locator("#sel-sensor").textContent())?.includes("CAN UNMAPPED")) {
  throw new Error("Arm inspector invented a firmware CAN assignment");
}
if (!(await page.locator("#fault-sensor").isDisabled()) || !(await page.locator("#fault-thermal").isDisabled())) {
  throw new Error("Unmapped arm fault controls should be disabled");
}
const initialShoulderPose = await page.evaluate(() => Array.from(
  window.dropbearTwin.robot.bodyGroups
    .get("/humanoid/torso_RMD_X10__1_Rotor_1").matrix.elements,
));
const armPoseVersion = await page.evaluate(() => window.dropbearTwin.robot.poseVersion);
await page.locator("#position-target").fill("18");
await page.waitForFunction((version) => window.dropbearTwin.robot.poseVersion > version, armPoseVersion);
const shoulderPoseDelta = await page.evaluate((before) => {
  const after = Array.from(
    window.dropbearTwin.robot.bodyGroups
      .get("/humanoid/torso_RMD_X10__1_Rotor_1").matrix.elements,
  );
  return after.reduce((sum, value, index) => sum + Math.abs(value - before[index]), 0);
}, initialShoulderPose);
if (!(shoulderPoseDelta > 0.0001)) throw new Error("Shoulder X10 shaft state did not move the USD arm");
await page.evaluate(() => {
  const workspace = document.querySelector(".workspace");
  if (workspace) workspace.scrollTop = 0;
  window.dropbearTwin.robot.fit();
});
await page.waitForTimeout(250);
await page.screenshot({ path: `${OUT}/01b-arm-motors.png` });
await page.locator("#position-target").fill("0");
await page.click('[data-motor-category="legs"]');
if ((await page.locator(".joint-card[data-joint-id]").count()) !== 12) {
  throw new Error("Expected twelve leg motor cards after category switch");
}
if (await page.locator("#fault-sensor").isDisabled() || await page.locator("#fault-thermal").isDisabled()) {
  throw new Error("Leg fault controls did not restore after category switch");
}

await page.click("#run-demo");
await page.waitForTimeout(900);
await page.waitForFunction(
  () => Math.max(
    window.dropbearTwin.robot.legTelemetry.left.footHeightMm,
    window.dropbearTwin.robot.legTelemetry.right.footHeightMm,
  ) > 45,
  null,
  { timeout: 6000 },
);
const runState = (await page.locator("#system-state").textContent())?.trim();
const canLoad = Number.parseFloat(await page.locator("#can-load").textContent());
if (runState !== "CONTROL ACTIVE") throw new Error(`Unexpected run state: ${runState}`);
if (!(canLoad > 10)) throw new Error(`CAN load did not become active: ${canLoad}`);
const usdPoseDelta = await page.evaluate((before) => {
  const after = Array.from(
    window.dropbearTwin.robot.bodyGroups
      .get("/humanoid/LL_RMD_X10_S2_MIR4__3_Stator_1").matrix.elements,
  );
  return after.reduce((sum, value, index) => sum + Math.abs(value - before[index]), 0);
}, initialUsdPose);
if (!(usdPoseDelta > 0.0001)) throw new Error("CAN state did not move the USD articulation");
const calfPoseDelta = await page.evaluate((before) => {
  const after = Array.from(
    window.dropbearTwin.robot.bodyGroups
      .get("/humanoid/LL_calf_motor_driver_ext_2").matrix.elements,
  );
  return after.reduce((sum, value, index) => sum + Math.abs(value - before[index]), 0);
}, initialCalfPose);
if (!(calfPoseDelta > 0.0001)) throw new Error("Outer calf CAN state did not move the X8 driver");
const closureResidualMm = await page.evaluate(() => window.dropbearTwin.robot.closureResidualMm);
if (!(closureResidualMm < 0.5)) throw new Error(`Calf linkage did not close: ${closureResidualMm} mm`);
const legTelemetry = await page.evaluate(() => ({
  left: window.dropbearTwin.robot.legTelemetry.left,
  right: window.dropbearTwin.robot.legTelemetry.right,
  leftMode: window.dropbearTwin.sim.gait.left.mode,
  rightMode: window.dropbearTwin.sim.gait.right.mode,
}));
if (legTelemetry.leftMode === legTelemetry.rightMode) throw new Error("Alternating gait legs are in the same phase");
if (!(Math.max(legTelemetry.left.footHeightMm, legTelemetry.right.footHeightMm) > 40)) {
  throw new Error(`Swing foot did not clear: ${JSON.stringify(legTelemetry)}`);
}
if (!(await page.locator("#left-calf-pair").textContent())?.includes("/")) {
  throw new Error("Live paired X8 telemetry missing");
}
await page.screenshot({ path: `${OUT}/02-running-sim.png` });

await page.locator(".joint-card").nth(4).click();
if (await page.locator("#position-target").getAttribute("min") !== "180") {
  throw new Error("Knee lock did not set the 180° browser lower bound");
}
await page.locator("#position-target").fill("210");
await page.click("#fault-sensor");
await page.waitForFunction(() => document.querySelector("#fault-sensor")?.textContent === "RELEASE SENSOR");

await page.click('[data-view-target="cad"]');
await page.waitForFunction(() => document.querySelector("#cad-status")?.textContent?.includes("96,640"));
if (!(await page.locator("#cad-lines").isChecked())) throw new Error("Technical CAD lines should default on");
await page.locator("#cad-explode").check({ force: true });
await page.locator("#cad-angle").fill("215");
await page.waitForTimeout(350);
await page.screenshot({ path: `${OUT}/03-step-cad.png` });

await page.click('[data-view-target="controller"]');
await page.waitForTimeout(400);
if ((await page.locator("#pin-map .pin-row").count()) !== 19) throw new Error("Expected nineteen controller routes");
await page.screenshot({ path: `${OUT}/04-controller-overview.png` });
await page.locator("#pin-map .pin-row").filter({ hasText: "GPIO5" }).click();
if (!(await page.locator("#pin-title").textContent())?.includes("GPIO5")) throw new Error("Pin focus did not update");
await page.waitForTimeout(250);
await page.screenshot({ path: `${OUT}/05-controller-pin-focus.png` });

await page.click('[data-view-target="firmware"]');
await page.locator("#terminal-command").fill("torque left hip_yaw 125");
await page.locator("#terminal-form").press("Enter");
if (!(await page.locator("#terminal-output").textContent())?.includes("set to 125")) throw new Error("Firmware command did not execute");
await page.click("#fault-can");
await page.waitForFunction(() => document.querySelector("#fault-can")?.textContent === "RESTORE CAN");
await page.screenshot({ path: `${OUT}/06-firmware-console.png` });
await page.click("#fault-can");

await page.click('[data-view-target="evidence"]');
await page.locator('[data-view="evidence"] h1').waitFor({ state: "visible" });
await page.waitForTimeout(350);
if (!(await page.locator('[data-view="evidence"]').textContent())?.includes("Actual Dropbear USD")) throw new Error("USD provenance missing");
await page.screenshot({ path: `${OUT}/07-evidence.png` });

await browser.close();

if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`VISUAL REVIEW PASSED · screenshots: ${OUT}`);
