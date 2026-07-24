# Dropbear PyTorch walking RL

This package provides a PPO walking lab with two selectable dynamics backends.
It uses the exact dashboard motor order—12 leg sources followed by 10 arm
sources—and exports deterministic rollouts that the full browser USD can
replay while training continues.

`mujoco-usd-proxy-v1` compiles the source-physics manifest into MuJoCo 3.6:
90 connected USD bodies, 84 tree joints, 27 retained closure constraints, 22
actuators, a free base, gravity, friction, impacts, and contact-force sensing.
Mass, COM, principal axes, inertia, joint axes, and limits come from the USD.
Collision envelopes are conservative inertia-derived ellipsoids because the
source collision groups have no finite external envelopes. They currently
collide with the floor only; self-collision is disabled until a grounded
collision-pair filter is available. The original `teaching-plant-v2` remains
available as a fast fallback. Neither replaces final Isaac/PhysX, HIL, or
hardware validation.

## CUDA compatibility controller

The `rl.sonic_*` modules are a CUDA-first compatibility PoC for validating the
Dropbear controller boundary. Install the locked x86_64 runtime into the local
environment, which must already expose a CUDA-enabled PyTorch build:

```bash
./tools/setup_gr00t_runtime.sh
```

On an A100 host, run the fail-fast training, export, runtime, ONNX CUDA, and
TensorRT numerical smoke test with:

```bash
DROPBEAR_CUDA_DEVICES=0 \
DROPBEAR_VERIFY_SESSION=a100-verify \
  ./tools/verify_gr00t_cuda.sh
```

The local model ABI is two inputs—`observation[N,90]` and
`motion_token[N,64]`—and one `motor_residual[N,22]` output in canonical
Dropbear motor order. A supplied reference is rejected unless its timeline is
exactly 50 Hz. Convert and validate dashboard motion before using
`--reference-path`:

```bash
python3 -m integrations.gr00t_wbc.motion_reference convert \
  --input web/assets/rl/dropbear-walk-reference.json \
  --output /tmp/dropbear-sonic-reference.json
```

The output is a normalized residual, not an absolute angle:

```text
target_rad[i] =
  authored_reference_rad[i]
  + clamp(motor_residual[i], -1, 1)
    * LOCAL_POLICY_ACTION_SCALE[i]
    * LOCAL_POLICY_RESIDUAL_GAIN
```

Zero therefore reproduces the time-varying authored reference. The final left
and right knee targets (indices 4 and 7) are clamped to `[0, π]` radians.
`rl.sonic_action.residual_to_reference` implements this exact
`dropbear-local-reference-residual-v1` contract; the per-axis `scale_rad`
values and joint order are serialized in every checkpoint and session
manifest. A raw residual must never be sent to a ROS position interface as
radians.

For a full A100 session followed by fail-closed deployment verification:

```bash
.gr00t-venv/bin/python -m rl.sonic_train \
  --device cuda --devices 0 \
  --amp --amp-dtype bfloat16 \
  --session-id a100-session \
  --reference-path /tmp/dropbear-sonic-reference.json

.gr00t-venv/bin/python -m rl.sonic_deploy \
  --checkpoint artifacts/rl/sonic/a100-session/sonic_policy.pt \
  --device cuda --devices 0 \
  --amp --amp-dtype bfloat16 \
  --require-tensorrt --tensorrt-fp16
```

Deployment exports a dynamic-batch ONNX graph, compares Torch with ONNX
Runtime using `CUDAExecutionProvider`, exercises runtime clamps and the stale
watchdog, builds a TensorRT 10.13 engine, and numerically compares TensorRT
with Torch. Any required-provider, build, execution, finite-value, tolerance,
or contract failure stops admission.

Pass multiple device indices to train through single-process
`torch.nn.DataParallel`; the first device is primary and is used for export
and engine verification:

```bash
.gr00t-venv/bin/python -m rl.sonic_train \
  --device cuda --devices 0,1,2 \
  --amp --amp-dtype bfloat16 \
  --session-id a100-multigpu
```

Each directory under `artifacts/rl/sonic/<session>/` contains
`sonic_policy.pt` and `session.json`. Verified deployment adds
`sonic_policy.onnx`, `sonic_policy.onnx.json`, `sonic_policy.engine`, and
`deployment-report.json`; the smoke path additionally writes
`smoke-report.json`. The reports record hashes, device selection, ABI,
reference metadata, numerical errors, and tolerances.

When training is launched with `--deploy`, its manifest remains
`deployment_pending` until ONNX CUDA and the requested TensorRT gate finish.
A failed or interrupted deployment is never indexed as complete. Runtime
admission requires exact physical action-contract equality and matching
checkpoint/session/sidecar hashes; it also rejects nonfinite, stale, replayed,
or excessively future-dated input frames.

The repository's checked A100 record is
`artifacts/rl/sonic-smoke/cuda-verified-20260724-r3/smoke-report.json`:
2,048 samples, 100% upright, 0% falls, `5.22e-8 m` maximum closure residual,
`1.14e-8` ONNX CUDA error, and `3.39e-8` TensorRT 10.13.3.9 FP16 error.

This PoC is deliberately not NVIDIA SONIC: it is incompatible with NVIDIA
GR00T-WholeBodyControl's native 784-value decoder ABI and released G1 weights.
Its 64-value tokens are deterministic reference-state tokens, not
natural-language embeddings, and it provides neither prompt inference nor a
persistent TensorRT motion service. The generated engine is a verified
artifact, not a continuously scheduled ROS or hardware deployment. Native
prompt-to-motion still requires the pinned upstream overlay, Dropbear
prompt-labelled data, Isaac Lab/PhysX training, a learned prompt/token
adapter, a persistent inference service, and separate SIL/HIL admission.

## Modelled state

- 22 motor positions, velocities, and actions;
- optional free-root height, vertical velocity, forward/lateral velocity,
  yaw/yaw rate, torso roll/pitch, and angular rates;
- left/right heel and toe contact weights and load;
- the authored baseline walking phase;
- two leg closed-chain projections;
- two USD-sampled elbow linkages; and
- whole-body center-of-mass height, lateral excursion, and vertical velocity.

The knee is never treated as an independent open-chain shortcut.
`FourBarLeg` projects the adjacent hip-pitch and knee actuator coordinates
through the leg closure. Browser `180°` maps to policy/ROS `0 rad` at knee
lock, and the plant clamps both knees to `0`–`π rad`.

The elbow input is likewise the actuator, not the conveniently named passive
joint:

```text
LH/RH_Revolute41 motor
  → five passive revolute coordinates
  → three retained USD closure constraints
  → passive LH/RH_elbow_joint output
```

`ArmElbowLoop` is interpolated from the browser closure solver across the
validated motor range. It exposes the resulting passive elbow angle and
closure residual to training.

## Reward hierarchy

The reward is led by:

1. low torso roll/pitch and low torso angular rate;
2. low center-of-mass height/lateral variation and vertical COM speed;
3. a smooth reference-motion bias toward the hand-authored alternating walk;
4. target forward speed/turn rate, half-cycle gait symmetry, and heel/toe
   timing;
5. controlled leg swing, knee contraction, and contralateral arm swing; and
6. low lateral/dorsal tilt, energy, action variation, and closure residual.

The baseline gait is a bias, not a hard script. PPO can depart from it when
that improves torso and COM stability. The actor mean is zero-initialized, so
the deterministic update-zero policy is exactly that baseline. Every live
preview is ranked on the same seed, and the final checkpoint restores the
best stable preview after all requested updates finish.

All 15 top-level coefficients are configurable and serialized into each policy
as `config.rewardWeights`: torso, COM, gait/contact, asynchronous symmetry,
speed/turn, leg swing, height, lateral tilt, dorsal tilt, knee contraction,
arm swing, energy, smoothness, closure, and fall. Reward coefficients favor
their behavior; penalty coefficients suppress their error. Zero disables a
term.

The dashboard ships two complete parameter profiles:

- **Gentle forward** — `0.26 m/s`, no commanded turn, strong asynchronous
  symmetry and upright/COM control, moderate leg swing, shallow-knee bias, and
  `250 × 4 = 1,000` policy epochs.
- **Circle walk · left** — `0.22 m/s`, `0.28 rad/s` turn rate (nominal
  `0.79 m` radius), inner/outer stride scaling, hip-yaw bias, stronger
  speed/turn tracking, and a reduced symmetry weight to preserve the required
  curved-gait asymmetry.

For a reproducible fine-tune, add:

```bash
--init-checkpoint artifacts/rl/experiments/<source>/checkpoint.pt
```

The checkpoint must match the 90-observation, 22-action dimensions and exact
joint order. Its deterministic corrected-plant rollout becomes protected
update zero before the requested optimization epochs begin.

## Dashboard training

Start the dashboard:

```bash
python3 web/serve.py 8000
```

Open <http://localhost:8000>, select **RL Lab**, configure updates, rollout
steps, parallel environments, epochs, and the expandable reward profile, then
start training. The same tuning controls are available in the Robot Sim
training drawer. Training accepts up to 10,000 updates; the process-control
endpoints accept mutations only from loopback and require a same-origin,
token-authenticated JSON request. The browser handles that token automatically.

Every PPO update atomically exports a deterministic live policy. With
**AUTO-REPLAY EACH UPDATE** enabled, **WATCH TRAINING LIVE** replays the newest
rollout on the complete browser USD and overlays reward, upright rate, torso
tilt, COM variation, speed, and falls. Final experiments are written beneath
`artifacts/rl/experiments/` and are intentionally ignored by Git.

Each experiment is also a persistent `dropbear-rl-session-v1`. The
`/api/rl/sessions` index survives dashboard restarts and exposes only
experiment-scoped artifacts. From the RL Lab, a stored run can be selected to:

- replay its exported policy on the browser USD;
- copy its exact training and reward parameters into the form; or
- warm-start a new run from its dimension- and joint-order-checked checkpoint.

Starting a new run never overwrites or deletes an older session. Session
configuration records `physicsBackend`, `motionProfile`, and
`targetTurnRate`; replay and warm-start preserve the selected run's contract.

## Command line

```bash
python3 -m rl.train_walk \
  --updates 250 --steps 128 --envs 8 --epochs 4 \
  --motion-profile gentle-forward \
  --physics-backend mujoco-usd-proxy-v1 \
  --target-speed 0.26 --target-turn-rate 0 \
  --reward-torso 1.75 --reward-com 1.20 \
  --reward-gait-contact 0.90 --reward-gait-symmetry 1.10 \
  --reward-speed 0.55 --reward-leg-swing 0.28 \
  --penalty-height 8.0 --penalty-lateral-tilt 5.0 \
  --penalty-dorsal-tilt 4.5 --penalty-knee-contraction 0.18 \
  --penalty-arm-swing 0.35 --penalty-energy 0.018 \
  --penalty-smoothness 0.065 --penalty-closure 300 \
  --penalty-fall 7 --device cpu \
  --no-vertical-constraint \
  --arm-swing
```

This example performs exactly 1,000 policy optimization epochs.
The trainer writes a PyTorch checkpoint, browser policy JSON, and metrics
JSON. Use `--live-policy-out` to request an atomic intermediate rollout after
every update.

Run the deterministic same-seed acceptance comparison with:

```bash
python3 -m rl.validate_walk \
  artifacts/rl/experiments/<experiment>/policy.json \
  --reference-policy-out \
    artifacts/rl/experiments/<experiment>/authored-reference.json \
  --out artifacts/rl/experiments/<experiment>/validation.json \
  --expected-policy-epochs 1000
```

The validator checks exact epoch count, 22-motor order, free-root/arm-swing
configuration, forward target-speed tracking, closed-chain residuals, and
non-regression against the authored gait’s combined stability score. Both
policies remain playable in the browser for visual review.

## Tracked reference result

`web/assets/rl/dropbear-walk-reference.json` is the selected update `188` from
a completed 200-update, five-epoch-per-update CUDA experiment: exactly 1,000
additional policy epochs with seed `23`. Its deterministic free-root
evaluation remained upright for 100% of 7.98 seconds with no fall, averaged
`0.256 m/s`, held mean/peak torso tilt to `8.66°`/`11.02°`, and limited COM
height range to `0.044 m`.

Against the same-seed authored zero-residual walk, it improved reward by
`0.355`, upright time by `53.90` percentage points, mean torso tilt by `9.58°`,
peak tilt by `30.41°`, and COM height range by `0.217 m`. The full browser USD
review passed every rendered-motion gate and measured maximum sampled leg and
arm closure residuals of `0.465 mm` and `0.154 mm`.

The paired authored policy, numerical acceptance report, and rendered A/B
report are checked in beside the policy under `web/assets/rl/`.

This remains a research baseline. Before hardware passthrough, validate a
policy in the Isaac/PhysX Dropbear USD, replay the intended trajectory through
the ROS 2 controller SIL, and retain the existing fail-closed admission path.
