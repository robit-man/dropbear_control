import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const index = fs.readFileSync(path.join(root, "index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "js", "app.js"), "utf8");
const lab = fs.readFileSync(path.join(root, "js", "gr00t_lab.js"), "utf8");
const server = fs.readFileSync(path.join(root, "serve.py"), "utf8");

let failures = 0;
function check(name, condition) {
  if (condition) console.log(`  ok  ${name}`);
  else {
    console.error(`  FAIL ${name}`);
    failures += 1;
  }
}

check(
  "GR00T navigation and view are present",
  index.includes('data-view-target="gr00t"')
    && index.includes('data-view="gr00t"'),
);
check(
  "runtime gates visibly separate CUDA, TensorRT, Isaac and hardware",
  index.includes('id="gr00t-gate-cuda"')
    && index.includes('id="gr00t-gate-trt"')
    && index.includes('id="gr00t-gate-smoke"')
    && index.includes('id="gr00t-gate-isaac"')
    && index.includes('id="gr00t-gate-hardware"'),
);
check(
  "prompt and CUDA training controls are present",
  index.includes('id="gr00t-prompt-form"')
    && index.includes('id="gr00t-training-form"')
    && index.includes('id="gr00t-devices"')
    && index.includes('id="gr00t-precision"'),
);
check(
  "dashboard initializes GR00T lab and fail-closed USD prompt preview",
  app.includes("setupGr00tLab()")
    && app.includes('"dropbear:prompt-plan"')
    && app.includes("sim.setPlay(true)")
    && app.includes("GR00T_PROMPT_PREVIEW_PRESETS")
    && app.includes("GR00T_PROMPT_PREVIEW_TURN_EPSILON_RPS")
    && app.includes("no browser preset matches")
    && app.includes("The plan was not played.")
    && !app.includes('["walk", "circle", "turn"].includes(plan.primitive)'),
);
check(
  "client uses loopback GR00T status, prompt and train APIs",
  lab.includes('requestJson("/api/gr00t/status")')
    && lab.includes('requestJson("/api/gr00t/sessions")')
    && lab.includes('requestJson("/api/gr00t/prompt"')
    && lab.includes('requestJson("/api/gr00t/train"'),
);
check(
  "both browser control clients lazily authorize JSON mutations",
  app.includes('fetch("/api/control-token"')
    && lab.includes('fetch("/api/control-token"')
    && app.includes('headers.set("X-Dropbear-Control-Token"')
    && lab.includes('headers.set("X-Dropbear-Control-Token"')
    && app.includes('credentials: "same-origin"')
    && lab.includes('credentials: "same-origin"'),
);
check(
  "runtime readiness requires hash-verified deployment evidence",
  lab.includes("gates.cudaDeploymentVerified")
    && lab.includes("CUDA RESIDUAL ENGINE BUILD VERIFIED"),
);
check(
  "server exposes the GR00T endpoints",
  server.includes('"/api/gr00t/status"')
    && server.includes('"/api/gr00t/sessions"')
    && server.includes('"/api/gr00t/prompt"')
    && server.includes('"/api/gr00t/train"'),
);
check(
  "server defaults to loopback and fail-closes control requests",
  server.includes('"DROPBEAR_DASHBOARD_HOST", "127.0.0.1"')
    && server.includes('os.environ.get("DROPBEAR_ALLOW_REMOTE") != "1"')
    && server.includes('"/api/control-token"')
    && server.includes("hmac.compare_digest")
    && server.includes("allow_nan=False")
    && server.includes("signal.SIGTERM")
    && server.includes("RL_MANAGER.stop"),
);

console.log(
  failures === 0
    ? "\nGR00T LAB TESTS PASSED"
    : `\nGR00T LAB TESTS FAILED (${failures})`,
);
process.exit(failures === 0 ? 0 : 1);
