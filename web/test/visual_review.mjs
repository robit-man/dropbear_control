// web/test/visual_review.mjs
// Playwright visual review of the MyActuator dashboard.
// Loads the page, drives the simulation through idle/driven/faulted states,
// and captures screenshots + DOM assertions for the pin grid and data-flow panel.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL || "http://localhost:8123";
const OUT = "/tmp/visual_review";
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function pinSummary(page) {
  return page.$$eval("#hw-pins .pin-row", (rows) =>
    rows.map((r) => ({
      name: r.querySelector("label")?.textContent,
      gpio: r.querySelector(".pin-gpio")?.textContent,
      cls: r.dataset.cls,
      active: r.classList.contains("active"),
      metric: r.querySelector(".pin-metric")?.textContent,
    }))
  );
}

function flowSummary(page) {
  return page.$$eval("#hw-flow .flow-row", (rows) =>
    rows.map((r) => ({
      text: r.textContent.replace(/\s+/g, " ").trim(),
      active: r.classList.contains("active"),
    }))
  );
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));

  await page.goto(BASE, { waitUntil: "networkidle" });
  await sleep(400);

  // ---- 1. Initial idle state (no sim) ----
  await page.screenshot({ path: `${OUT}/01-idle.png`, fullPage: true });
  const idlePins = await pinSummary(page);
  const idleFlow = await flowSummary(page);
  console.log("IDLE pins active:", idlePins.filter((p) => p.active).length, "/", idlePins.length);
  console.log("IDLE flow active:", idleFlow.filter((f) => f.active).length, "/", idleFlow.length);

  // ---- 2. Start simulation ----
  await page.click("#btn-sim");
  await sleep(600);
  // First motor is auto-selected by startSim(); just enable + drive it.
  await page.click("#c-enable");
  // Drive a sustained torque command so the bridge pins show real current.
  await page.selectOption("#c-mode", "torque");
  await page.fill("#c-target", "3.0");
  await page.click("#c-send");
  // Also command velocity so encoder/quad pins are clearly moving.
  await page.selectOption("#c-mode", "velocity");
  await page.fill("#c-target", "4.0");
  await page.click("#c-send");
  await sleep(1200);

  await page.screenshot({ path: `${OUT}/02-driven.png`, fullPage: true });
  const drivenPins = await pinSummary(page);
  const drivenFlow = await flowSummary(page);
  console.log("DRIVEN pins active:", drivenPins.filter((p) => p.active).length, "/", drivenPins.length);
  console.log("DRIVEN flow active:", drivenFlow.filter((f) => f.active).length, "/", drivenFlow.length);
  console.log("DRIVEN sample metrics:",
    drivenPins.slice(0, 6).map((p) => `${p.name}=${p.metric}${p.active ? "*" : ""}`).join(" | "));

  // ---- 3. Fault injection ----
  await page.click("#c-overtemp");
  await sleep(500);
  await page.screenshot({ path: `${OUT}/03-faulted.png`, fullPage: true });
  const faultPins = await pinSummary(page);
  const faultFlow = await flowSummary(page);
  console.log("FAULT pins active:", faultPins.filter((p) => p.active).length, "/", faultPins.length);
  console.log("FAULT flow active:", faultFlow.filter((f) => f.active).length, "/", faultFlow.length);
  const faultLed = faultPins.find((p) => p.name === "PIN_FAULT_LED");
  console.log("FAULT_LED active:", faultLed?.active, "metric:", faultLed?.metric);

  // ---- 4. Close-up of hardware panel only ----
  const hw = await page.$(".hardware");
  if (hw) await hw.screenshot({ path: `${OUT}/04-hardware-closeup.png` });

  // ---- 5. Switch board to S3 and re-capture ----
  await page.selectOption("#hw-board", "esp32-s3-devkitc-1");
  await sleep(300);
  await page.screenshot({ path: `${OUT}/05-s3-board.png`, fullPage: true });
  const s3Pins = await pinSummary(page);
  console.log("S3 board pins:", s3Pins.length, "first gpio:", s3Pins[0]?.gpio);

  await browser.close();

  // ---- Report ----
  const report = {
    consoleErrors: errors,
    idle: { pinsActive: idlePins.filter((p) => p.active).length, total: idlePins.length, flowActive: idleFlow.filter((f) => f.active).length },
    driven: { pinsActive: drivenPins.filter((p) => p.active).length, total: drivenPins.length, flowActive: drivenFlow.filter((f) => f.active).length },
    faulted: { pinsActive: faultPins.filter((p) => p.active).length, total: faultPins.length, flowActive: faultFlow.filter((f) => f.active).length, faultLedActive: faultLed?.active },
    s3PinCount: s3Pins.length,
  };
  console.log("\n=== REPORT ===");
  console.log(JSON.stringify(report, null, 2));
  if (errors.length) {
    console.log("\nCONSOLE ERRORS DETECTED:");
    errors.forEach((e) => console.log("  - " + e));
  } else {
    console.log("\nNo console/page errors.");
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
