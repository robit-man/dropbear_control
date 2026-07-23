// Standalone dashboard verification: proves the live server serves the
// dashboard with the new features, and that the sim-layer harness passes.
// Run from the project root: node web/test/verify_dashboard.mjs
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import http from "node:http";

const execFileP = promisify(execFile);

function get(url) {
  return new Promise((resolve, reject) => {
    http
      .get(url, (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => resolve({ status: res.statusCode, body: data }));
      })
      .on("error", reject);
  });
}

let failures = 0;
function check(name, cond) {
  if (cond) console.log("ok   " + name);
  else {
    console.log("FAIL " + name);
    failures++;
  }
}

const base = process.env.DASHBOARD_BASE || "http://localhost:8000";

const idx = await get(base + "/");
check("serve index HTTP 200", idx.status === 200);
check("index has legacy-select picker", idx.body.includes("legacy-select"));
check("index has hw-board selector", idx.body.includes("hw-board"));
check("index has AS5600 toggle", idx.body.includes("c-as5600"));
check("index has Calibrate button", idx.body.includes("c-calibrate"));
check("index has pin grid", idx.body.includes("hw-pins"));

const motors = await get(base + "/js/motors.js");
check("motors.js has LEGACY_VARIANTS", motors.body.includes("LEGACY_VARIANTS"));

const sim = await get(base + "/js/sim.js");
check("sim.js has calibrate()", sim.body.includes("calibrate"));

const css = await get(base + "/css/style.css");
check("css has BTX theme color (facc15)", css.body.includes("facc15"));

// Sidebar-driven module layout (replaces the old 5-column cramped grid).
check("index has sidebar nav", idx.body.includes('class="sidebar"'));
check("index has shell grid layout", idx.body.includes('class="shell"'));
check("index has module views", idx.body.includes('class="module"'));
check("index has 6 nav modules", (idx.body.match(/data-module="/g) || []).length >= 6);
check("css has sidebar styles", css.body.includes(".sidebar"));
check("css has module view styles", css.body.includes(".module"));
check("css no longer uses 5-col layout", !css.body.includes("240px 1fr 240px 320px 300px"));

const app = await get(base + "/js/app.js");
check("app.js wires sidebar nav", app.body.includes("setupSidebar"));
check("app.js has showModule switcher", app.body.includes("function showModule"));

// Command catalog: the dashboard must serve the full MyActuator command array
// (COMMANDS + NATIVE_RMDX_COMMANDS 0x30–0xDA) so operators can issue commands.
const commands = await get(base + "/js/commands.js");
check("commands.js served", commands.status === 200);
check("commands.js has COMMANDS catalog", commands.body.includes("export const COMMANDS"));
check("commands.js has native RMD-X array", commands.body.includes("export const NATIVE_RMDX_COMMANDS"));
check("commands.js native array spans 0x30–0xDA", commands.body.includes("0x30") && commands.body.includes("0xDA"));

// Run the sim-layer harness as a child process.
try {
  const { stdout } = await execFileP("node", ["web/test/harness.test.mjs"], {
    cwd: process.cwd(),
  });
  check("harness tests passed", stdout.includes("HARNESS TESTS PASSED"));
} catch (e) {
  check("harness tests passed", false);
  console.log((e.stdout || "") + (e.stderr || ""));
}

if (failures > 0) {
  console.log(`DASHBOARD VERIFY FAILED: ${failures} check(s)`);
  process.exit(1);
}
console.log("DASHBOARD VERIFY PASSED");
console.log("OMNIUS_VERIFICATION_RESULT: PASSED");
