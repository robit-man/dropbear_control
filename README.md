# Dropbear Control

Source-grounded low-level control, browser digital twin, ROS 2 trajectory
passthrough, and constrained walking-RL tooling for the Dropbear humanoid.

![Dropbear walking in the browser USD digital twin](docs/images/dropbear-control-walking.png)

> [!IMPORTANT]
> This repository is currently a software-in-the-loop engineering system. It
> does not authorize powered-robot motion, establish actuator suitability, or
> replace Isaac/PhysX, HIL, calibration, limit, and physical safety validation.

## Overview

`dropbear_control` joins four previously separate concerns into one auditable
workspace:

- the observed two-ESP32 Dropbear low-level-control behavior and 12-node CAN
  map;
- the actual Dropbear USD structure, adapted into a browser-renderable cache
  while retaining its rigid bodies, physical joints, and loop closures;
- a ROS 2 Jazzy `joint_trajectory_controller` software-in-the-loop path; and
- a 22-motor PyTorch PPO teaching plant with free-root balance, contact,
  center-of-mass, arm-swing, leg-closure, and elbow-closure state.

The browser dashboard is the primary interactive surface. It renders the
Dropbear USD, drives the exact CAN-to-USD joint bindings, projects passive calf
and ankle joints against the retained closure anchors, exposes ten arm-motor
shafts, solves both five-link elbow assemblies, and resolves each heel/toe
patch against a unilateral ground plane.
Live telemetry covers motor state, foot contact and load, ankle state, CAN,
sensors, linkage closure, root attitude, policy reward, and live training
progress.

## Current state

| Area | Implemented now | Boundary |
|---|---|---|
| Browser USD twin | 90 rendered bodies from a 294,204-triangle cache; the source-physics manifest retains 93 rigid bodies, 93 masses/inertias, 93 collision groups, 117 physical joints, 29 force drives, and 27 retained closures | Browser articulation is kinematic; full-body dynamics remain an external backend |
| Leg motor map | Twelve low-level CAN nodes, `0x141`–`0x14C`, bound to the corresponding USD motor axes | Source-grounded simulation; no physical CAN authority |
| Arm motor map | Ten selectable USD shafts: eight RMD-X8 arm drives and two torso-mounted RMD-X10 shoulder-pitch drives | Arm CAN IDs are not present in the observed leg firmware and remain deliberately unmapped |
| Elbow linkage | `LH/RH_Revolute41` actuator input drives five passive joints against three retained loop constraints on each arm | Kinematic DLS closure; Isaac/PhysX remains dynamics-authoritative |
| Calf/ankle linkage | Four X8 crank axes, tie rods, ankle contacts, foot pivot, and damped least-squares closure projection | Isaac/PhysX remains dynamics-authoritative |
| Foot-ground contact | Actual foot-body bounds produce four patches; free-root mode integrates gravity and compliant unilateral normal force using the USD-authored `56.229 kg` mass, reports newtons/load, and enforces a non-penetration barrier | Force-based root contact is real but is not a 93-body collision solve; friction, self-collision, and full PhysX dynamics remain external |
| Root modes | Switchable Z guide plus free-root gravity/policy playback with visible height, roll, and pitch failure | Simplified browser free body; not a rigid-body solver |
| Knee safety datum | Both knees are limited to encoder `180°`–`360°`; ROS/RL use `0`–`π` rad from the same lock datum | Software constraint; not a certified physical stop |
| Walking demo | Forward alternating gait with loading, rearward push-off, early swing, moderated knee lift, advance, and placement | Demonstration trajectory, not a learned or dynamically stable gait |
| Actuator CAD | Automatic X8/X10 selection from the active Dropbear axis; exact source STEP-derived housing/output previews articulate coaxially about X8 `+Y` and X10 `+Z`, with technical lines, explode control, and original STEP downloads | Visual B-Rep partitions, not calibrated dynamics/support authority |
| Controller lab | Dimensional ESP32 DevKit reference with 19 source/inferred signal routes | Board-level visualization, not circuit simulation |
| Firmware console | Source-shaped serial grammar, task cadence, CAN traffic, sensor stream, and fault injection | Clean-room behavioral twin, not instruction-set emulation |
| ROS 2 | Jazzy bringup, `joint_trajectory_controller`, mock hardware, action/topic demo, validation, and local WebSocket bridge | ROS side is SIL; the dashboard does not yet auto-switch to WebSocket state |
| Walking RL | Local 22-action/88-observation PPO experiments launched from Robot Sim or RL Lab; up to 10,000 training updates, ten adjustable reward/penalty coefficients, persistent run sessions, exact parameter recall, checkpoint warm-start, prior-policy replay, update-by-update USD replay, site-wide epoch/state telemetry, free-root balance, contacts, four closed-chain mechanisms, and a tracked 1,000-epoch reference policy | Teaching plant and policy-generation lab; every session identifies its backend and is not promoted to Isaac/PhysX validation |
| Physical hardware path | Existing host, firmware, evidence, and fail-closed admission scaffolding | Deliberately disabled pending reviewed hardware evidence and HIL gates |

## Ground-truth revisions

The browser control twin is pinned to:

| Source | Revision | Use |
|---|---|---|
| [`Hyperspawn/Dropbear`](https://github.com/Hyperspawn/Dropbear/tree/main/Control%20System/Low%20Level%20Control) | `13cf5ecaa39b8b89c794fe905dcea0490cfa7726` | ESP32 task, pin, serial, sensor, and CAN behavior |
| [`Hyperspawn/dropbear_rl`](https://github.com/Hyperspawn/dropbear_rl) | `3c37aedce6d445205671d5714d05ae28b8c90e2c` | `dropbear.usd`, articulation topology, visual meshes, and closed-loop leg geometry |

The 421,104,436-byte source USD is locally cached at
`artifacts/usd/dropbear.usd` and ignored by Git. Its SHA-256 is verified at
runtime. The tracked GLB is a decimated visual cache;
`web/assets/robot/dropbear-articulation.json` retains browser kinematics, while
`web/assets/robot/dropbear-physics-manifest.json` is extracted directly from
the source USD and retains its mass, inertia, collision, gravity, joint, and
force-drive contract.

Rebuild the local cache and tracked physics manifest with:

```bash
python3 tools/cache_dropbear_usd.py
python3 -m venv .physics-venv
.physics-venv/bin/pip install -r requirements-physics-lock.txt
.physics-venv/bin/python tools/export_dropbear_physics_manifest.py \
  artifacts/usd/dropbear.usd \
  web/assets/robot/dropbear-physics-manifest.json
```

## System architecture

```mermaid
flowchart LR
    FW[Dropbear ESP32 source] --> BT[Browser low-level twin]
    BT --> CAN[12-axis CAN state]
    CAN --> USD[Dropbear USD articulation]
    ARM[10 arm shafts: 8 X8 + 2 X10] --> USD
    USD --> CLS[Leg and elbow closure solvers]
    CLS --> GND[Heel/toe force contact and switchable root mode]
    GND --> UI[Contact, load, ankle, motor and residual telemetry]

    ROS[ROS 2 joint trajectory controller] --> WS[Loopback WebSocket bridge]
    WS -. browser adapter pending .-> CAN

    PPO[22-motor PyTorch PPO] --> LIVE[Per-update policy rollout]
    LIVE --> USD
    PPO -. Isaac/PhysX validation required .-> USD
```

The browser and ROS/RL paths use the same knee-lock convention and twelve
semantic joint names, but they are not presented as equivalent physics
engines.

## CAN-to-USD map

| CAN | Low-level axis | USD joint | Motor/path role |
|---|---|---|---|
| `0x141` | Left outer calf | `LL_Revolute81` | RMD-X8 outer crank |
| `0x142` | Left inner calf | `LL_Revolute67` | RMD-X8 inner crank |
| `0x143` | Right inner calf | `RL_Revolute67` | RMD-X8 inner crank |
| `0x144` | Right outer calf | `RL_Revolute81` | RMD-X8 outer crank |
| `0x145` | Left knee | `LL_knee_actuator_joint` | Knee actuator |
| `0x146` | Left hip pitch | `LL_hip_joint` | Hip pitch actuator |
| `0x147` | Right hip pitch | `RL_hip_joint` | Hip pitch actuator |
| `0x148` | Right knee | `RL_knee_actuator_joint` | Knee actuator |
| `0x149` | Left hip yaw | `PG_left_leg_roll` | Physical hip yaw |
| `0x14A` | Left hip roll | `PG_left_leg_pitch` | Physical hip roll |
| `0x14B` | Right hip roll | `PG_right_leg_pitch` | Physical hip roll |
| `0x14C` | Right hip yaw | `PG_right_leg_roll` | Physical hip yaw |

The final four USD names are retained from the source asset. Their semantic
mapping is based on the authored world-space axes and body placement.

Each calf side is evaluated as:

```text
X8 motor crank → tie-rod pivot → ankle contact → foot rocker pivot
```

The right outer X8 uses an explicit mirrored-Z browser adaptation because this
USD revision authors `RL_Revolute81` as X while the mirrored mechanism and the
other three calf shafts are Z-aligned. The adaptation and its rationale are
recorded in the articulation manifest.

## Arm-motor-to-USD map

The arm category adds one inspectable shaft at each remaining authored arm
axis. The two shoulder-pitch motors attached to the torso are RMD-X10 units,
matching the hip-yaw motor class; all remaining arm motors are RMD-X8 units.

| Side | Physical axis | USD joint | Motor | Mount |
|---|---|---|---|---|
| Left | Shoulder pitch | `LH_yaw` | RMD-X10 | Torso |
| Left | Shoulder yaw | `LH_pitch` | RMD-X8 | Arm |
| Left | Shoulder roll | `LH_roll` | RMD-X8 | Arm |
| Left | Elbow pitch | `LH_Revolute41` | RMD-X8 | Arm |
| Left | Wrist roll | `LH_wrist_roll` | RMD-X8 | Arm |
| Right | Shoulder pitch | `RH_yaw` | RMD-X10 | Torso |
| Right | Shoulder yaw | `RH_pitch` | RMD-X8 | Arm |
| Right | Shoulder roll | `RH_roll` | RMD-X8 | Arm |
| Right | Elbow pitch | `RH_Revolute41` | RMD-X8 | Arm |
| Right | Wrist roll | `RH_wrist_roll` | RMD-X8 | Arm |

The source USD calls the torso-root axes `LH_yaw` and `RH_yaw`; the dashboard
keeps those authored names visible while applying the physical shoulder-pitch
semantic supplied for the installed robot. No arm CAN IDs are invented. The
arm inspector therefore reports `AUX · CAN UNMAPPED` until an authoritative
firmware or wiring map is added.

The two elbow motor rows are closed-loop inputs. `LH_elbow_joint` and
`RH_elbow_joint` are passive members, not motor commands. Each `Revolute41`
input is solved together with `Revolute42`, the passive elbow, `Revolute32`,
`Revolute33`, and `Revolute44` against `Revolute123`, `Revolute125`, and
`Revolute127`. The viewer reports arm and leg residuals independently.

## Foot contact and vertical constraint

The browser derives heel and toe patches from the lowest vertices of each
actual foot body in the current USD pose. Free-root contact then:

1. integrates the USD-authored `9.80665 m/s²` gravity;
2. solves compliant unilateral spring/damper normal forces at each patch;
3. uses the exact `56.2289776 kg` sum of all 93 authored body masses;
4. converts normal force to four inspectable load-cell values; and
5. applies a final non-penetration safety barrier so no rendered foot can pass
   through the floor.

Those four patch loads feed the dashboard’s optional load-cell channels, and
the root-Z offset and contact state remain inspectable in the robot view. This
lets a retracting foot settle naturally onto the rendered floor while the
walking motion continues.

The Z guide is switchable. With **RL policy playback** selected and the guide
disabled, the root enters a simple free-body mode: gravity is integrated,
feet retain unilateral floor contact, and the torso is free to lose height,
roll, and pitch. An untrained or failed policy therefore falls instead of
being held upright. Exported policies can drive the same root state from their
recorded height/attitude/contact sequence.

This root-contact kernel is force based, but it still does not solve all 93
rigid bodies, authored collision meshes, friction, tangential impulses, or
self-collision. `/api/physics/status` therefore reports the verified source
USD and browser force contact separately from the high-fidelity
`isaac-physx-usd` backend. The latter is admitted only when Isaac Sim is
installed; it is currently offline on the bundled local Python runtime.

## Walking demonstration

The `Alternating step` scenario is a staged forward trajectory rather than a
set of phase-shifted sine waves. Each leg transitions through:

1. heel strike and loading;
2. mid-stance;
3. toe-off and an extended rearward push-off;
4. early swing;
5. moderated knee lift with greater forward hip pitch;
6. continued swing advance while the knee extends toward lock;
7. peak forward hip pitch at heel placement, followed by a loaded backward
   pull through stance.

The current target envelope never commands below the `180°` knee lock,
reaches that lock at heel strike, and limits peak gait knee demand to `232°`.
Hip pitch extends to approximately `25°` rearward during push-off, then
continues forward to `34°` as the knee reaches its heel-contact target. The leg
begins pulling backward only after contact becomes dominant. The viewport
correlates outer/inner X8 positions with solved ankle angle and foot-pivot
height, while the lower strip reports the worst retained-anchor residual.

This gait is useful for inspecting sign conventions, clearances, closure
behavior, and control timing. It is not evidence of balance or walk stability.

## Run the dashboard

Prerequisites are Python 3, Node.js, and npm.

```bash
git clone git@github.com:robit-man/dropbear_control.git
cd dropbear_control

cd web
npm ci
cd ..

python3 web/serve.py 8000
```

Open <http://localhost:8000>.

The dashboard starts in guarded pause even though the observed source firmware
sets `playMode=true` during setup. Choose either **Presets** or **RL Policies**
in the Robot Sim source switch, select one source, and use the single top-bar
**Play/Stop** control. Selecting a source arms it without starting motion.
The Robot Sim training drawer can launch PPO and replay each completed update
on the same full USD stage; the global training strip retains experiment,
epoch, reward, and upright state while navigating among views.
The RL Lab’s **Training sessions** panel indexes every retained experiment.
Select any run to copy its exact optimizer, curriculum, guide, arm, and reward
parameters; optionally warm-start from its checkpoint; or replay its policy.
**New run** clears only the selection—stored history is never deleted.

The six engineering views are:

- **Robot Sim** — complete USD visualization, motor selection, live gait and
  linkage/contact telemetry, separate leg and arm motor categories, faults,
  and configurable 50–200% render resolution;
- **Actuator CAD** — Dropbear-bound RMD-X8-25 Pro V2 and RMD-X10-100 S2 V3
  source STEP solids, correct source shaft axes, automatic selected-motor
  switching, technical lines, and articulation controls;
- **Controller Lab** — ESP32 board and pin/signal inspection;
- **Firmware** — two-controller serial/CAN behavioral console;
- **RL Lab** — advanced local PPO configuration and experiment diagnostics;
  source selection and playback remain unified on Robot Sim; and
- **Evidence** — source revisions, provenance, adaptations, and limitations.

## ROS 2 Jazzy SIL

The ROS package provides a twelve-axis
`joint_trajectory_controller/JointTrajectoryController` backed by
`mock_components/GenericSystem`.

```bash
sudo ros2_control/setup_ros2_jazzy.sh
source /opt/ros/jazzy/setup.bash

colcon build --symlink-install \
  --base-paths ros2_control/dropbear_trajectory_bringup \
  --build-base /tmp/dropbear_ros2_build \
  --install-base /tmp/dropbear_ros2_install \
  --log-base /tmp/dropbear_ros2_log

source /tmp/dropbear_ros2_install/setup.bash
ros2 launch dropbear_trajectory_bringup dropbear_trajectory.launch.py
```

Send a monitored example goal:

```bash
ros2 run dropbear_trajectory_bringup trajectory_demo \
  --amplitude 0.18 \
  --duration 3.0
```

The bridge exposes `ws://127.0.0.1:9091`, validates the exact joint set and
trajectory timing, and rejects negative knee coordinates. The current browser
dashboard uses its internal simulator; attaching its state/command path to the
bridge remains an explicit integration step.

See
[`ros2_control/dropbear_trajectory_bringup/README.md`](ros2_control/dropbear_trajectory_bringup/README.md)
for endpoints, inspection commands, and the hardware boundary.

## PyTorch walking lab

Use **Train RL** on Robot Sim for a compact live run, or **RL Lab** for the
complete experiment configuration. Both feed the same site-wide training state
and update-by-update full-USD replay. For a command-line run:

```bash
python3 -m rl.train_walk \
  --updates 200 --steps 256 --envs 128 --epochs 5 \
  --device cuda --no-vertical-constraint --arm-swing
```

The environment has 22 motor actions and 88 observations. Its leading reward
terms hold torso attitude/angular rate stable and minimize COM height/lateral
variation; the authored alternating walk supplies a smooth reference bias.
Speed, contact timing, contralateral arm swing, energy, action smoothness, and
all leg/elbow closure residuals remain explicit secondary terms.
The dashboard accepts `1`–`10,000` training updates. Expand **Reward / Penalty
Bias** on either training form to set the ten coefficients independently:
torso, COM, gait/contact, speed, height, arm swing, energy, smoothness, closure,
and fall. The current proven coefficients remain the defaults, zero disables a
term, and the exact profile is written into the experiment state, checkpoint,
and exported browser policy.

The same profile is available from the CLI, for example:

```bash
python3 -m rl.train_walk \
  --updates 1000 --steps 256 --envs 128 --epochs 5 \
  --reward-torso 1.5 --reward-com 1.0 \
  --reward-gait-contact 0.7 --reward-speed 0.8 \
  --penalty-arm-swing 0.65 --penalty-energy 0.015 \
  --device cuda --no-vertical-constraint --arm-swing
```

The actor mean is initialized to zero residual, so update zero is exactly the
working authored gait instead of a random corruption of it. Each deterministic
preview is evaluated on the same seed. The final checkpoint restores the
highest combined stability score observed during the complete run, while
retaining the selected update and completed-update count in its metadata.
`--init-checkpoint` supports an audited warm start and evaluates/protects that
state as update zero before optimization. The loopback dashboard service
accepts warm starts only from existing `.pt` files beneath
`artifacts/rl/experiments/`.

The local dashboard service exports a deterministic rollout after every PPO
update. **WATCH TRAINING LIVE** replays each new rollout on the full USD with
reward, upright rate, torso tilt, COM variation, speed, and fall telemetry.
Experiment checkpoints and policies live under `artifacts/rl/experiments/`.
**LOAD AUTHORED BASELINE** and **LOAD PPO REFERENCE** provide an immediate
same-view A/B replay after training.

Validate a completed 200 × 5 run against the authored residual-zero walk:

```bash
python3 -m rl.validate_walk \
  artifacts/rl/experiments/<experiment>/policy.json \
  --reference-policy-out \
    artifacts/rl/experiments/<experiment>/authored-reference.json \
  --out artifacts/rl/experiments/<experiment>/validation.json \
  --expected-policy-epochs 1000
```

### Tracked 1,000-epoch reference

The checked-in PPO reference is the stability-selected update `188` from a
complete `200 updates × 5 PPO epochs` CUDA run (`1,000` policy epochs, seed
`23`). Its deterministic eight-second free-root evaluation achieved:

| Metric | Authored walk | PPO reference | Change |
|---|---:|---:|---:|
| Upright time | 46.10% | 100.00% | +53.90 points |
| Mean torso tilt | 18.24° | 8.66° | −9.58° |
| Peak torso tilt | 41.43° | 11.02° | −30.41° |
| COM height range | 0.261 m | 0.044 m | −0.217 m |
| Mean forward speed | 0.336 m/s | 0.256 m/s | −0.080 m/s |
| Mean reward | 2.656 | 3.012 | +0.355 |

The subsequent full-USD browser A/B review also passed forward travel,
alternating support, foot clearance, free-root playback, hip/knee/arm motion,
and all browser loop-closure gates. The trained rollout travelled `2.044 m`;
its worst sampled leg and arm closure residuals were `0.465 mm` and
`0.154 mm`, respectively.

The reproducible artifacts are
[`dropbear-walk-reference.json`](web/assets/rl/dropbear-walk-reference.json),
[`dropbear-authored-reference.json`](web/assets/rl/dropbear-authored-reference.json),
[`dropbear-walk-validation.json`](web/assets/rl/dropbear-walk-validation.json),
and
[`dropbear-rendered-walk-review.json`](web/assets/rl/dropbear-rendered-walk-review.json).
Load the two policies with **LOAD PPO REFERENCE** and

### Natural-language whole-body control direction

GR00T/SONIC is planned as a high-level task and motion teacher rather than a
direct source of Dropbear motor commands. The released runtime targets the
Unitree G1; Dropbear needs constrained pose retargeting, a native 22-axis
embodiment, and a whole-body ROS interface before language-conditioned output
can safely reach its controller. The staged architecture, closed-loop
retargeting objective, runtime boundary, and acceptance gates are documented in
[`docs/GR00T_WBC_INTEGRATION.md`](docs/GR00T_WBC_INTEGRATION.md).
**LOAD AUTHORED BASELINE** for the same-view comparison.

This is a research baseline only. A policy must be trained and evaluated in
the full Isaac/PhysX Dropbear environment, then replayed through the ROS 2 SIL
path before any separate HIL or physical admission work.

See [`rl/README.md`](rl/README.md) for the model boundary.

## Verification

With the dashboard server running:

```bash
cd web
npm test
npm run verify:dashboard
npm run test:visual
```

For a rendered trained-versus-authored review, pass the two server-relative
policy URLs to `npm run test:walk-policy`. It samples both trajectories on the
full USD, checks forward travel, alternating support, foot clearance, arm/leg
motion, free-root playback, and closure residuals, and captures both poses.
The committed review report records the exact acceptance result for the
tracked pair.

The web suite checks the source map, all twelve leg CAN bindings, all ten arm
shafts and their 8× X8 / 2× X10 split, both three-constraint elbow linkages,
heel/toe contact loads, guided and free-root behavior, live policy playback,
knee lock, staged gait, STEP/GLB availability, closure behavior, control
protocols, and the critical Playwright journey.

Run the ROS protocol and RL unit tests from the repository root:

```bash
PYTHONPATH=.:ros2_control/dropbear_trajectory_bringup \
python3 -m pytest -q \
  ros2_control/dropbear_trajectory_bringup/test/test_protocol.py \
  tests/rl/test_dropbear_ppo.py \
  tests/rl/test_rl_service.py
```

For the much broader offline evidence, firmware, host, native, CAD, and safety
gate:

```bash
tools/test_all.sh
```

A passing software suite proves only the tested software boundary. It does not
prove physical motor-off behavior, HIL timing, exact actuator applicability,
plant fidelity, or safe powered operation.

## Repository layout

| Path | Purpose |
|---|---|
| `web/` | Six-view browser engineering dashboard, USD twin, and local RL service |
| `web/assets/robot/` | Optimized Dropbear GLB, articulation manifest, and attribution |
| `web/assets/cad/` | STEP-derived actuator browser caches |
| `rl/` | 22-motor free-root PyTorch PPO teaching plant and policy exporter |
| `ros2_control/dropbear_trajectory_bringup/` | ROS 2 Jazzy trajectory-controller SIL and dashboard bridge |
| `ros2_control/myactuator_dropbear_hardware/` | Existing fail-closed physical hardware plugin boundary |
| `firmware/esp32/` | ESP32/PAL and motor-driver scaffolding |
| `host/myactuator_lib/` | Host protocols, emulators, evidence, session, and safety tooling |
| `assets/` | Controlled source, CAD, calibration, graph, and review inputs |
| `generated/` | Reproducible evidence, CAD, plant, coverage, and review outputs |
| `schemas/` | Canonical configuration, evidence, plant, and admission contracts |
| `docs/` | Architecture, assessment, evidence, safety, and integration documents |
| `tools/` | Export, validation, generation, and complete-gate entry points |

Internal `myactuator` package and asset names are retained where they identify
the motor-vendor protocol/library domain; the GitHub repository itself is
`dropbear_control`.

## Evidence and safety boundary

The broader repository contains exact-source registries, deterministic
emulators, configuration admission, authorization, fault, audit, CAD, and
plant-review tooling. These are intentionally fail-closed:

- unreviewed motor tuples and plant facts do not become physical support;
- the tracked ROS hardware plugin does not acquire motion authority;
- synthetic positive tests are not treated as installed-unit evidence;
- browser closure quality is not rigid-body or contact validation; and
- software STOP/SHUTDOWN behavior is not claimed as a physical safe action.

Start with:

- [`web/README.md`](web/README.md) — dashboard, USD map, and browser boundary;
- [`docs/DROPBEAR_CONTROL_STACK_NOTES.md`](docs/DROPBEAR_CONTROL_STACK_NOTES.md)
  — observed low-level source audit;
- [`docs/CONTROL_STACK_TARGET.md`](docs/CONTROL_STACK_TARGET.md) — staged
  target architecture;
- [`docs/MYACTUATOR_ROS2_CONTROL_HANDOFF.md`](docs/MYACTUATOR_ROS2_CONTROL_HANDOFF.md)
  — fail-closed ROS hardware handoff; and
- [`docs/MYACTUATOR_LIBRARY_ASSESSMENT.md`](docs/MYACTUATOR_LIBRARY_ASSESSMENT.md)
  — host/firmware completeness assessment.

## License and attribution

Repository code and documents remain proprietary unless a file states
otherwise.

The Dropbear USD source is attributed to Hyperspawn Robotics — Priyanshu
Pareek and Cole Myers — and is licensed
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The tracked browser GLB is an adapted, decimated rendering cache. Source hash,
revision, license, attribution, and transformation notes are retained in
`web/assets/robot/ATTRIBUTION.md` and the articulation manifest.
