import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  GR00T_WBC_PLAYBACK_SOURCES,
  cancelGr00tWbcPlayback,
  playGr00tWbcSource,
  waitForGr00tWbcPlaybackIdle,
} from "../js/gr00t_lab.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const index = fs.readFileSync(path.join(root, "index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "js", "app.js"), "utf8");
const lab = fs.readFileSync(path.join(root, "js", "gr00t_lab.js"), "utf8");
const server = fs.readFileSync(path.join(root, "serve.py"), "utf8");
const service = fs.readFileSync(path.join(root, "gr00t_service.py"), "utf8");

function frozenArrayBody(source, name) {
  const match = source.match(
    new RegExp(`const ${name} = Object\\.freeze\\(\\[([\\s\\S]*?)\\]\\);`),
  );
  return match?.[1] || "";
}

function frozenStringArray(source, name) {
  return [...frozenArrayBody(source, name).matchAll(/"([^"]+)"/g)]
    .map((match) => match[1]);
}

function frozenNumberArray(source, name) {
  return frozenArrayBody(source, name)
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .map(Number);
}

const playbackRequests = [];
let playbackHarnessError = null;
let dispatchedPlaybackEvents = 0;
let overlappingRequestError = null;
let replacementRequestError = null;
let replacementRequestSucceeded = false;
const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
const originalCustomEvent = globalThis.CustomEvent;
try {
  globalThis.window = {
    dispatchEvent() {
      dispatchedPlaybackEvents += 1;
    },
  };
  globalThis.CustomEvent = class {
    constructor(type, init) {
      this.type = type;
      this.detail = init?.detail;
    }
  };
  globalThis.fetch = async (url, request = {}) => {
    if (url === "/api/control-token") {
      return {
        ok: true,
        status: 200,
        json: async () => ({ token: "test-control-token" }),
      };
    }
    if (url === "/api/gr00t/retarget") {
      playbackRequests.push(JSON.parse(request.body));
      return {
        ok: true,
        status: 200,
        json: async () => ({ hardwareAuthorized: false }),
      };
    }
    throw new Error(`unexpected request: ${url}`);
  };
  await playGr00tWbcSource("g1-published-stand");
  await playGr00tWbcSource("g1-published-stand");
  await playGr00tWbcSource("sonic-release-stand");
  await playGr00tWbcSource("sonic-release-stand");
  await playGr00tWbcSource("g1-published-stand", { dispatch: false });
  let finishDeferredRequest;
  globalThis.fetch = async (url, request = {}) => {
    if (url !== "/api/gr00t/retarget") {
      throw new Error(`unexpected deferred request: ${url}`);
    }
    playbackRequests.push(JSON.parse(request.body));
    return new Promise((resolve) => {
      finishDeferredRequest = () => resolve({
        ok: true,
        status: 200,
        json: async () => ({ hardwareAuthorized: false }),
      });
    });
  };
  const pendingRequest = playGr00tWbcSource(
    "sonic-release-stand",
    { dispatch: false },
  );
  for (let attempt = 0; attempt < 5 && !finishDeferredRequest; attempt += 1) {
    await Promise.resolve();
  }
  try {
    await playGr00tWbcSource("sonic-release-stand", { dispatch: false });
  } catch (error) {
    overlappingRequestError = error;
  }
  finishDeferredRequest();
  await pendingRequest;

  let rejectCancelledRequest;
  globalThis.fetch = async (url, request = {}) => {
    if (url !== "/api/gr00t/retarget") {
      throw new Error(`unexpected replacement request: ${url}`);
    }
    playbackRequests.push(JSON.parse(request.body));
    return new Promise((resolve, reject) => {
      rejectCancelledRequest = reject;
      request.signal.addEventListener("abort", () => {
        const error = new Error("cancelled for replacement");
        error.name = "AbortError";
        reject(error);
      }, { once: true });
    });
  };
  const cancelledRequest = playGr00tWbcSource(
    "sonic-release-stand",
    { dispatch: false },
  ).catch((error) => error);
  for (let attempt = 0; attempt < 5 && !rejectCancelledRequest; attempt += 1) {
    await Promise.resolve();
  }
  cancelGr00tWbcPlayback();
  await waitForGr00tWbcPlaybackIdle();
  replacementRequestError = await cancelledRequest;
  globalThis.fetch = async (url, request = {}) => {
    if (url !== "/api/gr00t/retarget") {
      throw new Error(`unexpected successor request: ${url}`);
    }
    playbackRequests.push(JSON.parse(request.body));
    return {
      ok: true,
      status: 200,
      json: async () => ({ hardwareAuthorized: false }),
    };
  };
  await playGr00tWbcSource(
    "sonic-release-stand",
    { dispatch: false },
  );
  replacementRequestSucceeded = true;
} catch (error) {
  playbackHarnessError = error;
} finally {
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
  globalThis.CustomEvent = originalCustomEvent;
}

let firstTokenHarnessError = null;
let firstTokenAbortError = null;
let firstTokenSharedFetchSurvived = false;
let firstTokenSuccessorSucceeded = false;
let firstTokenFetchCount = 0;
const firstTokenRetargetRequests = [];
try {
  const isolatedLab = await import(
    `../js/gr00t_lab.js?first-token-abort=${Date.now()}`
  );
  let finishTokenFetch;
  let sharedTokenSignal;
  globalThis.fetch = async (url, request = {}) => {
    if (url === "/api/control-token") {
      firstTokenFetchCount += 1;
      sharedTokenSignal = request.signal;
      return new Promise((resolve) => {
        finishTokenFetch = () => resolve({
          ok: true,
          status: 200,
          json: async () => ({ token: "shared-test-control-token" }),
        });
      });
    }
    if (url === "/api/gr00t/retarget") {
      firstTokenRetargetRequests.push(JSON.parse(request.body));
      return {
        ok: true,
        status: 200,
        json: async () => ({ hardwareAuthorized: false }),
      };
    }
    throw new Error(`unexpected first-token request: ${url}`);
  };
  const callerController = new AbortController();
  const cancelledFirstTokenPlayback = isolatedLab.playGr00tWbcSource(
    "sonic-release-stand",
    {
      dispatch: false,
      signal: callerController.signal,
    },
  ).catch((error) => error);
  for (let attempt = 0; attempt < 5 && !finishTokenFetch; attempt += 1) {
    await Promise.resolve();
  }
  callerController.abort();
  await isolatedLab.waitForGr00tWbcPlaybackIdle();
  firstTokenAbortError = await cancelledFirstTokenPlayback;
  firstTokenSharedFetchSurvived = sharedTokenSignal?.aborted === false;
  finishTokenFetch();
  await isolatedLab.playGr00tWbcSource(
    "sonic-release-stand",
    { dispatch: false },
  );
  firstTokenSuccessorSucceeded = true;
} catch (error) {
  firstTokenHarnessError = error;
} finally {
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
  globalThis.CustomEvent = originalCustomEvent;
}

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
  "visible G1-to-Dropbear bridge exposes decoded-pose and pinned-token previews",
  index.includes("G1 → DROPBEAR USD MOTOR BRIDGE")
    && index.includes('id="gr00t-preview-g1-pose"')
    && index.includes('id="gr00t-preview-sonic-token"')
    && index.includes("fixture—not a VLA token")
    && index.includes("STATIC SOFTWARE-IN-THE-LOOP PREVIEW · NO MOTOR AUTHORITY"),
);
check(
  "playback source has adjacent matching text-only mode and family toggles",
  index.includes('id="playback-mode" class="playback-mode-button"')
    && index.includes('id="playback-family" class="playback-mode-button"')
    && index.includes('data-family="classic"')
    && index.includes('aria-label="Toggle playback family between classic and GR00T WBC"')
    && index.includes(">CLASSIC</button>")
    && !index.includes('id="playback-family" type="checkbox"'),
);
check(
  "GR00T family exposes only the two truthful playable bridge sources",
  JSON.stringify(GR00T_WBC_PLAYBACK_SOURCES.map(({ value, readiness }) => (
    { value, readiness }
  ))) === JSON.stringify([
    { value: "g1-published-stand", readiness: "decodedG1PoseReady" },
    { value: "sonic-release-stand", readiness: "nvidiaTokenReady" },
  ])
    && !GR00T_WBC_PLAYBACK_SOURCES.some(
      ({ value }) => /live|vla|server/i.test(value),
    ),
);
check(
  "per-page GR00T sessions are regex-safe and advance contiguous sequences",
  playbackHarnessError === null
    && playbackRequests.length === 8
    && /^[A-Za-z0-9._:-]+$/.test(playbackRequests[0].sessionId)
    && /^[A-Za-z0-9._:-]+$/.test(playbackRequests[2].sessionId)
    && playbackRequests[0].sessionId === playbackRequests[1].sessionId
    && playbackRequests[2].sessionId === playbackRequests[3].sessionId
    && playbackRequests[0].sessionId !== playbackRequests[2].sessionId
    && playbackRequests[0].sequence === 0
    && playbackRequests[1].sequence === 1
    && playbackRequests[2].sequence === 0
    && playbackRequests[3].sequence === 1
    && playbackRequests[2].source.sequenceStart === 0
    && playbackRequests[3].source.sequenceStart === 1
    && playbackRequests[5].sessionId === playbackRequests[2].sessionId
    && playbackRequests[5].sequence === 2
    && playbackRequests[5].source.sequenceStart === 2
    && playbackRequests[6].sessionId === playbackRequests[2].sessionId
    && playbackRequests[6].sequence === 3
    && playbackRequests[6].source.sequenceStart === 3
    && playbackRequests[7].sessionId !== playbackRequests[2].sessionId
    && playbackRequests[7].sequence === 0
    && playbackRequests[7].source.sequenceStart === 0
    && dispatchedPlaybackEvents === 4
    && /already in flight/.test(overlappingRequestError?.message || ""),
);
check(
  "cancelled preview releases the module lock before its replacement request",
  replacementRequestError?.name === "AbortError"
    && replacementRequestSucceeded
    && lab.includes("waitForGr00tWbcPlaybackIdle"),
);
check(
  "first-token cancellation is caller-local and a fresh SONIC stream can continue",
  firstTokenHarnessError === null
    && firstTokenAbortError?.name === "AbortError"
    && firstTokenSharedFetchSurvived
    && firstTokenSuccessorSucceeded
    && firstTokenFetchCount === 1
    && firstTokenRetargetRequests.length === 1
    && firstTokenRetargetRequests[0].sequence === 0
    && firstTokenRetargetRequests[0].source.sequenceStart === 0
    && /^[A-Za-z0-9._:-]+$/.test(firstTokenRetargetRequests[0].sessionId),
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
  "bridge posts strict q29 and release-token source contracts",
  lab.includes('requestJson("/api/gr00t/retarget"')
    && lab.includes('kind: "decoded-g1-pose"')
    && lab.includes('schema: "unitree-g1-body-position-v1"')
    && lab.includes('producer: "nvidia-gear-sonic-published-g1-stand-fixture"')
    && lab.includes("nvidiaVlaDerived: false")
    && lab.includes('kind: "nvidia-sonic-release-token-fixture"')
    && lab.includes('schema: "nvidia-gr00t-sonic-motion-token-64d-v1"')
    && lab.includes('producer: "nvidia-gear-sonic-release"')
    && lab.includes("NVIDIA_RELEASE_DECODER_CHECKPOINT"),
);
check(
  "published G1 fixture has the canonical 29-axis body order and pose",
  frozenStringArray(lab, "G1_BODY_JOINT_ORDER").length === 29
    && frozenNumberArray(lab, "G1_PUBLISHED_STAND_Q").length === 29
    && frozenStringArray(lab, "G1_BODY_JOINT_ORDER")[0] === "left_hip_pitch_joint"
    && frozenStringArray(lab, "G1_BODY_JOINT_ORDER")[28] === "right_wrist_yaw_joint"
    && frozenNumberArray(lab, "G1_PUBLISHED_STAND_Q").every(Number.isFinite),
);
check(
  "pinned NVIDIA SONIC release fixture is exactly 64D and never labeled VLA output",
  frozenNumberArray(lab, "NVIDIA_RELEASE_INITIAL_TOKEN").length === 64
    && frozenNumberArray(lab, "NVIDIA_RELEASE_INITIAL_TOKEN").every(Number.isFinite)
    && lab.includes("This is an official SONIC fixture, not output from a VLA request.")
    && service.includes('"nvidiaVlaDerivedClaim": not release_fixture')
    && service.includes('"checkpointSpecificReleaseFixture": release_fixture'),
);
check(
  "both browser control clients lazily authorize JSON mutations",
  app.includes('fetch("/api/control-token"')
    && lab.includes('fetch("/api/control-token"')
    && app.includes('headers.set("X-Dropbear-Control-Token"')
    && lab.includes('"X-Dropbear-Control-Token",')
    && lab.includes("await getGr00tControlToken(options.signal)")
    && lab.includes("awaitWithCallerSignal(fetchControlToken(), signal)")
    && app.includes('credentials: "same-origin"')
    && lab.includes('credentials: "same-origin"'),
);
check(
  "runtime readiness requires hash-verified deployment evidence",
  lab.includes("gates.cudaDeploymentVerified")
    && lab.includes("CUDA RESIDUAL ENGINE BUILD VERIFIED"),
);
check(
  "playback state machine has exactly classic preset, classic trained, and GR00T trained",
  app.includes('playbackFamily: "classic"')
    && app.includes('ui.playbackFamily = "classic"')
    && app.includes('ui.playbackFamily = family === "gr00t" ? "gr00t" : "classic"')
    && app.includes('ui.playbackMode = "rl"')
    && app.includes("preventing a meaningless PRESET + GR00T pair")
    && app.includes('setPlaybackFamily("gr00t")')
    && app.includes('setPlaybackFamily("classic")'),
);
check(
  "the unified Play button dispatches GR00T and fails closed on decoder readiness",
  app.includes('const visibleFamily = $("playback-family").dataset.family')
    && app.includes("await playGr00tWbcSource(")
    && app.includes("dispatch: false,")
    && app.includes("await waitForGr00tWbcPlaybackIdle()")
    && app.includes("ui.gr00tAvailability[source.readiness] !== true")
    && app.includes("required decoder gate is closed")
    && app.includes("ui.gr00tPlayBusy")
    && app.includes('playButton.setAttribute("aria-busy", "true")')
    && lab.includes('"dropbear:gr00t-runtime"')
    && lab.includes('"dropbear:retargeted-pose"'),
);
check(
  "async policy and live-preview completions are generation guarded",
  app.includes("let playbackSelectionGeneration = 0")
    && app.includes("isCurrentPlaybackSelection(generation)")
    && app.includes('ui.playbackFamily !== "classic"')
    && app.includes('$("scenario").value !== "live"')
    && app.includes("policyPlayer.setPolicy(policy, url)")
    && !app.includes("await policyPlayer.load(`${status.livePolicyUrl}"),
);
check(
  "standalone previews and stored-session replay reject stale async completion",
  lab.includes("let previewGeneration = 0")
    && lab.includes("generation !== previewGeneration")
    && lab.includes('button.dataset.ready !== "1"')
    && lab.includes("cancelPreviewRequest()")
    && app.includes("async function replaySelectedRLSession()")
    && app.includes("const configured = await configurePlaybackSource(source, { generation })")
    && app.includes("if (!configured || !isCurrentPlaybackSelection(generation)) return;"),
);
check(
  "GR00T readiness closes on unknown state and status-poll failure",
  app.includes("ui.gr00tAvailability[source.readiness] !== true")
    && lab.includes('status: "offline"')
    && lab.includes("decodedG1PoseReady: false")
    && lab.includes("nvidiaTokenReady: false"),
);
const expectedDropbearOrder = [
  "left_outer_calf",
  "left_inner_calf",
  "right_inner_calf",
  "right_outer_calf",
  "left_knee",
  "left_hip_pitch",
  "right_hip_pitch",
  "right_knee",
  "left_hip_yaw",
  "left_hip_roll",
  "right_hip_roll",
  "right_hip_yaw",
  "left_shoulder_pitch",
  "left_shoulder_yaw",
  "left_shoulder_roll",
  "left_elbow_pitch",
  "left_wrist_roll",
  "right_shoulder_pitch",
  "right_shoulder_yaw",
  "right_shoulder_roll",
  "right_elbow_pitch",
  "right_wrist_roll",
];
check(
  "browser applies only the exact 22-axis Dropbear action contract",
  JSON.stringify(frozenStringArray(app, "DROPBEAR_RETARGET_ACTION_ORDER"))
    === JSON.stringify(expectedDropbearOrder)
    && app.includes('window.addEventListener("dropbear:retargeted-pose"')
    && app.includes("payload.hardwareAuthorized !== false")
    && app.includes("frame.retarget?.hardwareAuthorized !== false")
    && app.includes("order.every(")
    && app.includes("positions.every(Number.isFinite)")
    && app.includes("renderLive()"),
);
check(
  "token chunks are bounded to 40 frames and scheduled on a drift-corrected nominal 20 ms timeline",
  service.includes("source.motionTokenChunk must contain 1..40 token frames")
    && service.includes("maximum_frames=40")
    && app.includes("const nextDeadline = startedAt + (index + 1) * 20")
    && app.includes("Math.max(0, nextDeadline - performance.now())")
    && app.includes("nominal 20 ms USD preview"),
);
check(
  "server exposes the GR00T endpoints",
  server.includes('"/api/gr00t/status"')
    && server.includes('"/api/gr00t/sessions"')
    && server.includes('"/api/gr00t/prompt"')
    && server.includes('"/api/gr00t/train"')
    && server.includes('"/api/gr00t/retarget"'),
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
