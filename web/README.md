# Dropbear Low-Level-Control Digital Twin

This is a browser engineering dashboard for the current Dropbear low-level
controller. It is grounded in the ESP32 source at
`Control System/Low Level Control` revision
`13cf5ecaa39b8b89c794fe905dcea0490cfa7726` and the actual Dropbear RL/USD
robot at revision `3c37aedce6d445205671d5714d05ae28b8c90e2c`.

The dashboard starts in a guarded pause even though the observed firmware
sets `playMode=true` during setup. It is a deterministic, source-grounded
simulation—not ESP32 instruction-set emulation and not a validated rigid-body
plant. Do not use it as the sole safety basis for powered hardware.

## What is included

- **Robot Sim** — the tracked `dropbear.usd`, adapted into a 294,204-triangle
  browser cache while retaining source manifests for 93 rigid bodies, 93
  authored masses/inertias, 93 collision groups, 117 physical joints, 29
  force drives, and 27 retained loop-closure constraints. All 12 RMD CAN axes (`0x141`
  through `0x14C`) bind to their actual USD joints and anchors. Eight
  non-calf motors and four X8 calf cranks drive browser forward kinematics;
  the retained passive rods and ankle/foot pivots are projected against the
  true USD closure anchors. A separate arm category exposes ten installed
  shafts: eight RMD-X8 arm motors and the two torso-mounted RMD-X10
  shoulder-pitch motors. Arm firmware IDs remain unmapped rather than guessed.
  Heel and toe patches derived from the rendered foot bodies feed either the
  Z guide or a free-root, force-based vertical contact solver using the exact
  authored 56.229 kg total mass and four load-cell channels. Isaac/PhysX
  remains authoritative for full-body dynamics.
  The alternating-step demo uses explicit loading, stance, extended rearward
  push-off, moderated knee lift, continued forward advance during knee
  extension, peak forward hip pitch at near-lock heel placement, and a loaded
  backward stance pull rather than phase-shifted sine waves. Live per-leg
  cards correlate foot-pivot clearance and solved ankle angle with the
  outer/inner X8 positions.
- **Actuator CAD** — selected-axis-aware RMD-X8-25 Pro V2 and RMD-X10-100 S2
  V3 housing/output solids derived from the exact cached STEP sources, with
  correct source shaft axes, technical edges, articulation, and exploded
  output. Full-resolution STEP files stay downloadable.
- **Controller Lab** — a nominal 51.5 × 28.5 mm ESP32 DevKit V1 model with
  active CAN, SPI, ADC, I2C, UART, and optional HX711 routes. The 19-route pin
  table distinguishes values stated in source from inferred default VSPI pins.
- **Firmware** — two-controller serial console, exact command grammar,
  1 kHz/100 Hz task telemetry, five-value CSV stream, and CAN/serial/IMU
  fault controls.
- **RL Lab** — local 22-action PPO configuration, ten independent reward and
  penalty coefficients, live update replay on Robot Sim, persistent sessions,
  exact parameter recall, checkpoint warm-start, and prior-policy replay.
- **Evidence** — firmware and RL/USD revisions, CAD provenance, license and
  attribution, simulation boundaries, and observed firmware hazards.

## CAN to USD articulation

| CAN | Firmware axis | USD joint | Browser path |
|---|---|---|---|
| `0x141` | left outer calf X8 | `LL_Revolute81` | motor driver axis |
| `0x142` | left inner calf X8 | `LL_Revolute67` | motor driver axis |
| `0x143` | right inner calf X8 | `RL_Revolute67` | motor driver axis |
| `0x144` | right outer calf X8 | `RL_Revolute81` | motor driver axis |
| `0x145` | left knee | `LL_knee_actuator_joint` | forward kinematics |
| `0x146` | left hip pitch | `LL_hip_joint` | forward kinematics |
| `0x147` | right hip pitch | `RL_hip_joint` | forward kinematics |
| `0x148` | right knee | `RL_knee_actuator_joint` | forward kinematics |
| `0x149` | left hip yaw | `PG_left_leg_roll` | forward kinematics |
| `0x14A` | left hip roll | `PG_left_leg_pitch` | forward kinematics |
| `0x14B` | right hip roll | `PG_right_leg_pitch` | forward kinematics |
| `0x14C` | right hip yaw | `PG_right_leg_roll` | forward kinematics |

Each calf mapping is solved as a three-point linkage in the browser:
X8 motor crank → tie-rod pivot → ankle closure, with the ankle/foot bearing as
the rocker pivot. The retained USD anchor residual is shown live in the robot
viewport. The right outer X8 has an explicit mirrored-axis adaptation because
this source USD revision authors `RL_Revolute81` as X while its mirrored mate
and the other calf motor axes are Z; the authored X axis cannot close the
linkage.

The last four USD names preserve the source model’s naming. The mapping uses
the physical world-space axes and body locations: the `*_leg_pitch` USD axes
are physical hip roll, while the `*_leg_roll` axes are physical hip yaw.

## Arm motor to USD articulation

| Side | Physical axis | USD joint | Motor | Firmware map |
|---|---|---|---|---|
| Left | Shoulder pitch | `LH_yaw` | RMD-X10 | Unmapped |
| Left | Shoulder yaw | `LH_pitch` | RMD-X8 | Unmapped |
| Left | Shoulder roll | `LH_roll` | RMD-X8 | Unmapped |
| Left | Elbow pitch | `LH_elbow_joint` | RMD-X8 | Unmapped |
| Left | Wrist roll | `LH_wrist_roll` | RMD-X8 | Unmapped |
| Right | Shoulder pitch | `RH_yaw` | RMD-X10 | Unmapped |
| Right | Shoulder yaw | `RH_pitch` | RMD-X8 | Unmapped |
| Right | Shoulder roll | `RH_roll` | RMD-X8 | Unmapped |
| Right | Elbow pitch | `RH_elbow_joint` | RMD-X8 | Unmapped |
| Right | Wrist roll | `RH_wrist_roll` | RMD-X8 | Unmapped |

The physical shoulder-pitch identification comes from the torso-mounted X10
drives. The USD authors those root joints as `LH_yaw` and `RH_yaw`; both names
are shown in the inspector so the physical semantic correction stays
auditable. Selecting an arm card or shaft allows the corresponding USD axis to
be exercised without implying low-level CAN authority.

## Foot contact model

The guided mode uses `VerticalGroundConstraint`; free-root mode uses
`ForceGroundContact`. Both sample the lowest heel and toe vertices after
forward kinematics. The free-root solver integrates authored gravity, computes
unilateral spring/damper normal force in newtons, applies it to the exact
56.2289776 kg source-USD mass, and routes per-patch force-derived loads to the
left-heel, left-toe, right-heel, and right-toe channels. A final position
projection is retained only as a no-penetration safety barrier.

This is real vertical force interaction at the browser root, not a 93-body
rigid-body solve. It does not model friction, tangential impulses,
self-collision, or authoritative center-of-pressure dynamics. The
`/api/physics/status` endpoint keeps this boundary explicit and admits the
source USD to Isaac/PhysX only when that runtime is actually installed.

## Run it

From the repository root:

```bash
python3 web/serve.py 8000
```

Open <http://localhost:8000>. The small server also exposes local Three.js
modules, the exact generated CAD candidates, and the optimized browser caches
without a frontend build step. The `USD RES` slider changes the actual renderer
pixel density from 50–200% and persists the local selection.

## Verify

```bash
cd web
npm test
npm run verify:dashboard
npm run test:visual
```

`npm test` covers the existing protocol/plant checks plus the source-grounded
leg and arm maps, vertical ground constraint, and runtime. The dashboard smoke
and Playwright visual checks require the server to be running on port 8000.
Set `DASHBOARD_BASE`, `BASE_URL`, or `VISUAL_OUT` to override their defaults.

## Key files

| Path | Purpose |
|---|---|
| `index.html` | Six-view engineering workspace |
| `js/dropbear.js` | Source map, task scheduler, serial grammar, load-cell state, and simplified joint plant |
| `js/dropbear_usd.js` | Auditable 12-leg-CAN and 10-arm-motor USD binding maps |
| `js/vertical_ground_constraint.js` | Heel/toe sensing, gravity settling, and Z-only no-penetration projection |
| `js/force_ground_contact.js` | Free-root gravity and unilateral normal-force integration |
| `js/robot_3d.js` | Full USD body renderer, leg/arm motor shafts, contact patches, and browser forward kinematics |
| `js/board_3d.js` | Interactive dimensional ESP32 controller and signal routes |
| `js/cad_viewer.js` | STEP-derived GLB rendering and articulation |
| `js/app.js` | Dashboard interaction and live telemetry wiring |
| `rl_service.py` | Loopback-only persistent PPO-session process manager |
| `physics_service.py` | Verified source-USD and backend-admission status |
| `assets/robot/dropbear-physics-manifest.json` | Source-extracted masses, inertias, joints, collision groups, and drives |
| `assets/cad/*.glb` | Optimized browser caches derived from the exact candidate solids |
| `assets/robot/dropbear-usd-browser.glb` | Decimated visual cache of the actual Dropbear USD |
| `assets/robot/dropbear-articulation.json` | Body, joint, closure, source, leg-CAN, and arm-motor binding manifest |
| `test/dropbear.test.mjs` | Low-level source-map, leg/arm inventory, and runtime regression |
| `test/vertical_ground_constraint.test.mjs` | Ground-contact plant regression |
| `test/visual_review.mjs` | Critical interactive journey, shaft motion, contact, and screenshot review |

## Dropbear USD license

The source `dropbear.usd` comes from
<https://github.com/Hyperspawn/dropbear_rl> and is licensed
CC-BY-NC-SA-4.0. Attribution: Hyperspawn Robotics — Priyanshu Pareek and Cole
Myers. The local GLB is an adapted, decimated browser rendering; source
revision, SHA-256, license, attribution, and adaptation notes are retained in
`assets/robot/dropbear-articulation.json` and
`assets/robot/ATTRIBUTION.md`.
