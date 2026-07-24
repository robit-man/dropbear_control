import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";

const BASE = process.env.BASE_URL || "http://localhost:8000";
const POLICY_URL = process.env.POLICY_URL;
const REFERENCE_POLICY_URL = process.env.REFERENCE_POLICY_URL;
const OUT = process.env.WALK_REVIEW_OUT || "/tmp/dropbear-walk-comparison";

if (!POLICY_URL || !REFERENCE_POLICY_URL) {
  throw new Error("POLICY_URL and REFERENCE_POLICY_URL are required");
}
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1,
});
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(`console: ${message.text()}`);
});
page.on("pageerror", (error) => errors.push(`page: ${error.message}`));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.dropbearTwin?.robot?.ready === true);

async function reviewPolicy(url, label, screenshotName) {
  await page.evaluate(async ({ policyUrl, policyLabel }) => {
    const twin = window.dropbearTwin;
    await twin.policyPlayer.load(policyUrl);
    twin.policyPlayer.loop = false;
    document.querySelector("#rl-policy-title").textContent = policyLabel;
  }, { policyUrl: url, policyLabel: label });

  const duration = await page.evaluate(() => window.dropbearTwin.policyPlayer.duration);
  const samples = [];
  for (const fraction of [0.08, 0.20, 0.32, 0.44, 0.56, 0.68, 0.80, 0.92]) {
    await page.evaluate((seconds) => {
      window.dropbearTwin.policyPlayer.seek(seconds);
      window.dropbearTwin.robot.renderer.render(
        window.dropbearTwin.robot.scene,
        window.dropbearTwin.robot.camera,
      );
    }, duration * fraction);
    await page.waitForTimeout(90);
    samples.push(await page.evaluate((sampleFraction) => {
      const { robot, policyPlayer } = window.dropbearTwin;
      return {
        fraction: sampleFraction,
        elapsed: policyPlayer.elapsed,
        guide: robot.groundContact.guide,
        closureResidualMm: robot.closureResidualMm,
        legClosureResidualMm: robot.legClosureResidualMm,
        armClosureResidualMm: robot.armClosureResidualMm,
        leftFootHeightMm: robot.legTelemetry.left.footHeightMm,
        rightFootHeightMm: robot.legTelemetry.right.footHeightMm,
        leftLoadKg: (
          robot.groundContact.left.heelLoadKg
          + robot.groundContact.left.toeLoadKg
        ),
        rightLoadKg: (
          robot.groundContact.right.heelLoadKg
          + robot.groundContact.right.toeLoadKg
        ),
      };
    }, fraction));
  }

  const peak = samples.reduce((best, sample) => (
    Math.max(sample.leftFootHeightMm, sample.rightFootHeightMm)
      > Math.max(best.leftFootHeightMm, best.rightFootHeightMm)
      ? sample
      : best
  ));
  await page.evaluate((seconds) => {
    const { policyPlayer, robot } = window.dropbearTwin;
    policyPlayer.seek(seconds);
    robot.fit();
    robot.renderer.render(robot.scene, robot.camera);
  }, peak.elapsed);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${screenshotName}` });

  const policySummary = await page.evaluate(() => {
    const { policy, duration: policyDuration } = window.dropbearTwin.policyPlayer;
    const ranges = policy.jointOrder.map((name, index) => {
      const values = policy.frames.map((frame) => frame.q[index]);
      return {
        name,
        range: Math.max(...values) - Math.min(...values),
      };
    });
    return {
      source: window.dropbearTwin.policyPlayer.source,
      duration: policyDuration,
      evaluation: policy.evaluation,
      rootForwardTravelM: (
        policy.frames.at(-1).base.x - policy.frames[0].base.x
      ),
      ranges,
      frameCount: policy.frames.length,
    };
  });

  const maxClearanceMm = Math.max(
    ...samples.flatMap((sample) => [
      sample.leftFootHeightMm,
      sample.rightFootHeightMm,
    ]),
  );
  const alternatingSupport = samples.some(
    (sample) => Math.abs(sample.leftLoadKg - sample.rightLoadKg) > 8,
  );
  const checks = {
    fullUsdPolicyRoot: samples.every((sample) => sample.guide === "FREE_ROOT_POLICY"),
    closedChains: samples.every((sample) => sample.closureResidualMm < 0.5),
    visibleFootClearance: maxClearanceMm > 35,
    alternatingSupport,
    forwardTravel: policySummary.rootForwardTravelM > 0.2,
    hipsMove: policySummary.ranges
      .filter((joint) => joint.name.endsWith("hip_pitch"))
      .every((joint) => joint.range > 0.25),
    kneesMove: policySummary.ranges
      .filter((joint) => joint.name.endsWith("knee"))
      .every((joint) => joint.range > 0.25),
    armsMove: policySummary.ranges
      .filter((joint) => joint.name.endsWith("shoulder_pitch"))
      .every((joint) => joint.range > 0.3),
  };
  return {
    label,
    ...policySummary,
    maxClearanceMm,
    alternatingSupport,
    samples,
    checks,
    passed: Object.values(checks).every(Boolean),
  };
}

const reference = await reviewPolicy(
  REFERENCE_POLICY_URL,
  "Authored residual-zero reference",
  "01-authored-reference.png",
);
const trained = await reviewPolicy(
  POLICY_URL,
  "Selected 1,000-epoch PPO policy",
  "02-trained-policy.png",
);

const report = {
  schema: "dropbear-rendered-walk-review-v1",
  reference,
  trained,
  comparison: {
    rewardDelta: trained.evaluation.meanReward - reference.evaluation.meanReward,
    uprightDeltaPercent: (
      trained.evaluation.uprightPercent - reference.evaluation.uprightPercent
    ),
    torsoTiltDeltaDegrees: (
      trained.evaluation.torsoTiltMeanDegrees
      - reference.evaluation.torsoTiltMeanDegrees
    ),
    comHeightRangeDeltaM: (
      trained.evaluation.comHeightRangeM - reference.evaluation.comHeightRangeM
    ),
  },
  passed: reference.passed && trained.passed && errors.length === 0,
  browserErrors: errors,
};
writeFileSync(`${OUT}/report.json`, `${JSON.stringify(report, null, 2)}\n`);
await browser.close();

console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exit(1);
