# MyActuator — ESP32 Motor Controller + Host Tooling

Brownfield control-stack project for MyActuator servo drives (RMD-X, RH, CEM,
RMD-H, RMD-L, FL/FLO), spanning ESP32, host, simulation and Dropbear
integration. Most legacy paths remain prototype scaffolding. Files in
`contracts/` document that legacy intent and are non-authoritative. The
official-source RMD classic-CAN V4.4 offline codec and its vectors live in
`host/myactuator_lib/rmd_v44.py`,
`firmware/esp32/src/protocols/rmd_v44_codec.*`, and `tests/protocol/`. A
fail-closed exact-tuple evidence registry, protocol-state SIL emulator, and
canonical non-enableable Dropbear migration schema now provide the next
offline integration layer; none of them establishes physical applicability.
The live vendor-index snapshot and unified 145-subject evidence queue make
source drift, human review and physical holds executable rather than implicit.
The companion 97-packet CAD/plant intake package expands that queue into all
2,361 exact review and extraction tasks without inventing evidence.
A version-locked, page-coordinate-preserving product-spec extractor now binds
15 official manual occurrences and 215 pages to one exact table for each of
the 44 catalog models. Its 531 values are review candidates, not plant facts;
all 406 mapped candidates are linked to exact handoff tasks and acceptance
remains zero.
A positive-capable review lifecycle now requires immutable assigned-human
extractor submissions and independent ordered review events before it can
materialize an active V2 source fact; the tracked baseline has zero
submissions, events and facts.
A deterministic exact-set assembler is now the only path from those active
facts to a qualified plant set. It requires all 34 scalar parameters, four ranged
operating envelopes and an accepted exact protocol tuple, binds every
fact/decision/generation hash, and removes the set on revocation. A separate
V1 runtime adapter accounts for all 38 source semantics and requires an
independently reviewed exact execution profile before producing a hash-bound
typed plant contract. It rejects noise, timing, direction or torque semantics
the fixed-step core cannot represent instead of approximating them. Synthetic
positive tests pass. A distinct V2 event-scheduled engine and adapter now
represent rational multirate capture/interpolation, arbitrary delay,
counter-based noise/jitter, directional efficiency, one-shot peak torque,
separate thermal limits, command deadlines/order and complete replay state.
Aggregate registry V4 forbids two active adapter generations for one plant,
and the session/trace layers retain exact V2 contract provenance. The tracked
44-model baseline remains at zero sets, profiles, contracts and loadable
models.
A separate transactional twelve-axis V2 bank now exercises synchronized
all-actuator batches, aggregate current admission, rollback, thermal
fail-stop, complete snapshot/restore and deterministic replay across the 12
observed Dropbear-shaped actuator slots. It is permanently synthetic and
models no canonical graph, rigid body, shared power bus or exact motor.
A separate source-bound coverage dashboard joins requirements, tests, work
packages, gates, all 44 models and all 53 configurations so trace coverage,
implemented evidence and remaining production gaps stay distinct.
The WP-170 Python/native authorization core adds a closed post-authentication
role/action and bounded audit boundary while keeping physical and remote
actuation disabled by default; it provides no credential verification,
endpoint binding or motion authority.
An exact security-platform intake now binds the active PlatformIO/Arduino/IDF
configuration and proves that the tracked `esp32dev` profile is not a
production trust root. A separate Python/native artifact transaction core
defines verifier-assertion, rollback, durable commit and reboot semantics
without implementing cryptography or persistence.

## Repository layout

| Path | What it is |
|------|------------|
| `firmware/esp32/` | ESP32 Arduino/PlatformIO firmware: Protocol Abstraction Layer (PAL), per-motor drivers, and CAN / RS485 / EtherCAT transports |
| `host/myactuator_lib/` | Python library (transport / device / protocol / ROS bridge) with a self-test harness |
| `ros2_control/myactuator_dropbear_hardware/` | Pinned Jazzy C++ semantic core and fail-closed `SystemInterface` plugin |
| `schemas/` | Canonical Dropbear configuration schema, semantic validator, and explicitly incomplete observed migration input |
| `contracts/` | Draft protocol and per-series notes; these require reconciliation with current official manuals |
| `assets/myactuator/` | Pinned official product/CAD catalog and reproducible source-asset workflow |
| `generated/myactuator/evidence_review/` | Hash-bound 145-subject reviewer queue and local workbench |
| `generated/myactuator/evidence_intake/` | Source-bound 53-CAD/44-plant generated human handoff drafts |
| `generated/myactuator/plant/spec_candidates/` | Page/table/hash-bound 44-model product-spec review candidates; never runtime facts |
| `generated/myactuator/plant/candidate_decisions/` | Replayed human decision registry and lifecycle-materialized active V2 source facts |
| `generated/myactuator/plant/parameter_sets/` | Deterministic all-38-fact plus accepted-tuple plant-set assembly registry and generated sets |
| `assets/myactuator/plant_runtime_profiles/` | Controlled independently reviewed execution-profile submissions; empty in the tracked baseline |
| `assets/myactuator/plant_runtime_profiles_v2/` | Controlled V2 execution-profile submissions for event-scheduled sourced plants; empty in the tracked baseline |
| `generated/myactuator/plant/runtime_adapters/` | Hash-bound exact V1 runtime contracts and 44-model admission registry |
| `generated/myactuator/plant/runtime_adapters_v2/` | Hash-bound exact V2 runtime contracts and 44-model admission registry |
| `host/myactuator_lib/multi_actuator_plant_v2.py` | Transactional twelve-axis synthetic V2 composition; no robot/physical fidelity |
| `generated/myactuator/coverage_dashboard/` | Machine JSON and network-free HTML for exact program coverage and blockers |
| `generated/security_platform_intake/` | Exact source-bound ESP32 security capability/selection denial status |
| `web/` | In-progress WebSerial dashboard and synthetic browser simulator |
| `docs/` | Completeness audit, Dropbear findings, and target control/simulation architecture |

## Current status

- **Firmware** — builds for `esp32`, but the active family drivers and generic
  transports do not yet communicate with MYACTUATOR hardware. A successful
  build is not evidence of motor support.
- **Host library** — the loopback self-test passes (`HOSTLIB_OK`). The exact
  six-field support registry keeps catalog identity separate from support,
  and the V4.4 protocol-state emulator provides deterministic multi-node
  timing/fault/replay tests. The bounded host-link V1 Python reference and
  allocation-free C++11 mirror add typed config/lease/SI/state/disposition
  messages, shared vectors, anti-replay policy and bounded stream recovery.
  The deterministic host session and fake-transport native scheduler exercise
  reconnect, last-moment config/safety admission, queue budgets and response
  correlation. A seven-role/ten-action post-authentication core adds exact
  generation, replay, lease/safety, physical-default-denial and digest-only
  audit checks; a pass means only “evaluate the next gate.” A 48-case
  Python/native artifact core separately enforces exact key purpose, target,
  verifier assertions, monotonic versions, staged durable commit/audit and
  fail-disabled reboot reconstruction. These components have no credential,
  crypto, persistent-storage, physical adapter or motion authority. A pinned
  Jazzy C++ package now builds, loads and matches the Python semantic core, but
  its authority provider and concrete session adapter intentionally deny
  configuration. Physical devices/transports remain incomplete.
- **Protocol applicability** — the V2 registry supports positive exact
  installed-unit decisions only with reviewed inventory, source and
  command-response evidence plus three independent humans. Synthetic positive
  tests pass; the real controlled directory remains empty and all 44 models
  remain unsupported.
- **Dropbear configuration** — the schema captures all 12 semantic leg joints,
  10 observed external encoder roles, legacy command-ID observations,
  provenance and safety admission. Unknown motor tuples, bus ownership,
  limits, calibrations and CAD bindings keep the example non-enableable.
  Deterministic firmware/host/ROS/UI/simulator projections share its digest;
  the native config guard rejects this incomplete projection for motion.
  Positive-capable source and structured graph V2 lifecycle registries now
  support independently approved accept/reject/revoke/supersede transitions.
  Their tracked baselines contain zero active decisions, and live registry
  generation changes invalidate host sessions and joint handles.
- **CAN adapter intake** — an exact no-I/O manifest contract covers board,
  controller, transceiver, clock, pins, driver identity, 1-Mbit/s timing,
  TX-disable, timestamp/loss bounds and error-state behavior. Neither TWAI nor
  MCP2515 is selected, and the physical factory is disabled pending installed
  evidence and separate authorization.
- **ESP32 security intake** — one exact observed `esp32dev` profile binds
  PlatformIO 7.0.1, the Arduino-ESP32 package, ESP-IDF 4.4.7, SDK flags and
  partition table. Secure Boot, flash encryption, boot anti-rollback, NVS
  encryption and secure-element use are disabled; TLS 1.0/1.1 remain compiled.
  There are zero reviewed/selected profiles, trust anchors, key assignments or
  production security adapters.
- **Web frontend** — an in-progress dashboard and toy simulator exist in the
  working tree. The existing six STEP placeholders are empty and the generic
  Three.js model path is not integrated.
- **Official CAD inventory** — all 44 current product packages and 53 STEP
  variants are cataloged. Run `tools/sync_myactuator_cad.sh` to populate the
  ignored local source cache; `tools/sync_myactuator_docs.sh` pulls the nine
  pinned series protocol/manual source sets. All 53 exact STEP variants now
  pass bounded Part 21 inspection and import with the pinned CadQuery 2.8.0 /
  OpenCascade 7.9.3.1 stack. Forty-eight variants contain closed solids; both
  X6-8 copies, CEM-25, CEM-45 and FL-85-23 are shell-only. The strict review
  ledger remains 0/44 because no real housing/output/axis review is complete.
- **Evidence review** — one queue partitions 44 protocol, 53 CAD, 44 plant and
  four Dropbear/physical governance subjects. Forty-one CAD subjects are
  packet-reviewable, 12 need better geometry/partition evidence, and all 17
  human roles remain unassigned. The intake package materializes 97 exact
  CAD/plant drafts with 689 CAD questions and 1,672 plant requirements. The
  plant drafts additionally reference 406 exact mapped product-spec
  candidates; 125 other extracted values are deliberately unmapped. Queue,
  candidate and intake status grant no physical action. The independent plant
  candidate lifecycle is implemented and adversarially tested, but its real
  extractor/reviewer assignments and controlled record directories remain
  empty.
- **Program coverage** — all 77 requirements are structurally traced, while
  the catalog separately reports 105 implemented-offline, 28 planned and seven
  physical-hold verification items. Only 3/15 full-objective criteria are met;
  the dashboard asserts no requirement completion, gate pass, release,
  support or motion authority.
- **Fault evidence** — a portable allocation-free core records bounded
  command/feedback/bus fault context, rejects missing or corrupt restart
  snapshots and permits only an explicit evidence-gated reset back to BOOT.
  Durable storage/audit integration and physical safe-action evidence remain
  open.
- **Fault arbitration** — a portable allocation-free monitor deterministically
  composes configuration, bus-off, response-budget, critical-drive,
  local-limit and required-feedback failures into that latch. Six-source
  preemption, exact context, malformed-input denial, sanitizers, Clang and
  allocation checks pass; the trusted ESP32 observation/persistence adapter
  and physical stop proof remain open.
- **Composed safety exploration** — 4,789 deterministic sequences and 272,451
  injected events exercise the final gateway boundary. Normal IQ frames appear
  only with simultaneous state, lease, owner, session, sequence, deadline,
  route and current-configuration authority; software STOP/SHUTDOWN remains
  explicitly nonphysical.
- **Safety** — not ready for powered robot use. See the assessment before doing
  unloaded, current-limited bench work.

## Offline verification

Run the complete no-hardware P0–P1 gate from the repository root:

```bash
python3 -m pip install -r requirements-test.txt
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cad-lock.txt
sudo apt-get install ros-jazzy-ros2-control python3-colcon-common-extensions
tools/test_all.sh
```

It validates the tracked vendor evidence, legacy host regression, shared
Python/C++ V4.4 vectors, exact-tuple evidence policy, deterministic
safety/lease/config-admission models, protocol-state emulator, Dropbear
structural/semantic configuration, source/graph lifecycle replay, structured
graph V2, lifecycle-aware projection/API revocation, exact no-I/O adapter
intake and generated-view parity, bounded host-link Python/native parity, fake
gateway scheduling, host session lifecycle and a native-to-protocol-emulator
steel thread. It also validates all 53 STEP source identities, the
exact-configuration/44-model fail-closed review ledger, 26 assembly candidate
packets, 27 flattened topology inventories, pinned CAD toolchain, synthetic
two-link articulation, a fail-closed real X12 candidate split/articulation
pilot and real-source import evidence before web, traceability and ESP32
compile checks. The same entry runs the post-auth Python/native role matrix,
37 shared authorization vectors, the exact security platform intake, 48
shared artifact-transaction vectors, bounded audit-lane adversaries and native
sanitizers. It also re-hashes all 97 CAD/plant handoff packets and their
2,361 null-valued tasks, re-extracts all 215 product-spec pages into 531
non-authoritative candidates, replays the reviewed fact/set chain, accounts
for every sourced plant semantic through the fail-closed runtime adapter, and
checks the source-bound
requirement/model/gate coverage dashboard. A pass proves
specification-level offline conformance only; it
does not prove physical motor-off, HIL behavior, exact model/firmware
applicability, real transport delivery/retry/bus-off behavior, actuator plant
fidelity, or reviewed simulation-ready vendor CAD. The browser's procedural
geometry and dynamics are executable toy evidence only; the generated exact
CAD registry currently exposes 0/53 configurations.

The native ROS stage verifies an exact Ubuntu 24.04 / Jazzy 4.45.2 ABI lock,
builds and loads the C++17 plugin, and compares descriptor, lifecycle,
read/write and revocation vectors byte-for-byte with the live Python core. It
uses no physical hardware and the installed plugin has no successful backend.

The vendor-index live probe is intentionally not part of the offline gate:

```bash
python3 tools/manage_myactuator_download_index.py --probe
```

The tracked snapshot is checked offline. Live additions/removals open source
change control and do not mutate the baseline.

## Quick start

### Firmware (PlatformIO)

```bash
cd firmware/esp32
pio run -e esp32            # build
pio run -e esp32 -t upload  # flash
pio device monitor -b 115200
```

Select motor series / protocol / encoder resolution via the `build_flags` in
`platformio.ini` (see `firmware/esp32/README.md` for details).

### Host library

```bash
cd host
PYTHONPATH=. python3 myactuator_lib/_verify.py   # expect: HOSTLIB_OK
```

The library exposes layered `transport`, `device`, `protocol`, and `ros`
packages; see `host/myactuator_lib/__init__.py` for the public surface.

## Documentation

- `docs/MYACTUATOR_LIBRARY_ASSESSMENT.md` — evidence-based completeness and gap assessment
- `docs/DROPBEAR_CONTROL_STACK_NOTES.md` — audit of the current Dropbear low-level prototype
- `docs/CONTROL_STACK_TARGET.md` — target low-to-high architecture and staged delivery gates
- `docs/MYACTUATOR_ROS2_CONTROL_HANDOFF.md` — exact Jazzy package, API/lifecycle contract and remaining authority/adapter work
- `docs/MYACTUATOR_EVIDENCE_REVIEW_QUEUE.md` — 145-subject review queue, role assignments and dependency order
- `docs/MYACTUATOR_COVERAGE_DASHBOARD.md` — exact requirement/test/model/gate coverage and objective blockers
- `docs/SECURITY_AUTHORIZATION_BOUNDARY.md` — post-auth role/action, degraded-mode and audit contract plus explicit open authentication work
- `docs/ESP32_SECURITY_PLATFORM_INTAKE.md` — exact installed security profile, promotion contract and current provisioning blockers
- `docs/ARTIFACT_TRUST_CORE.md` — verifier-neutral stage/commit/abort/reboot and durable receipt semantics
- `docs/PLANT_SPEC_CANDIDATE_EXTRACTION.md` — exact PDF extraction boundary, review workflow and non-promotion rules
- `docs/PLANT_CANDIDATE_REVIEW_LIFECYCLE.md` — immutable human submission/event replay, provenance and V2 fact materialization contract
- `docs/PLANT_RUNTIME_ADAPTER.md` — conservative V1 sourced-plant adapter and exact representability boundary
- `docs/PLANT_RUNTIME_ADAPTER_V2.md` — event-scheduled V2 adapter, runtime/session/trace integration and current denial state
- `docs/PLANT_DYNAMICS_V2_SPEC.md` — exact V2 dynamics, scheduling, noise/jitter, deadline and snapshot semantics
- `.aiwg/iterations/iteration-16/iteration-plan.md` — granular 44-model plant/CAD/twin review and admission campaign
- `.aiwg/iterations/iteration-14/iteration-plan.md` — granular reviewed-evidence, canonical-integration and physical-entry gates
- `.aiwg/iterations/iteration-2/iteration-plan.md` — canonical configuration iteration results and next ready backlog
- `.aiwg/iterations/iteration-4/iteration-plan.md` — native-link, fake-gateway and host-session steel-thread scope
- `.aiwg/iterations/iteration-5/iteration-plan.md` — exact STEP inspection, semantic output-member review and conversion scope
- `.aiwg/iterations/iteration-6/iteration-plan.md` — exact geometry-configuration review, partition, export and articulation campaign
- `.aiwg/iterations/iteration-11/iteration-plan.md` — positive authority lifecycles, structured graph V2, adapter intake and physical hold
- `schemas/dropbear-config.schema.json` — strict canonical Dropbear configuration contract
- `schemas/myactuator-cad-review.schema.json` — strict exact-configuration selector and per-variant housing/output/axis/artifact review contract
- `assets/myactuator/README.md` — official STEP catalog, cache, and conversion requirements
- `firmware/esp32/README.md` — firmware build, configuration, and PAL API
- `contracts/PROTOCOLS_CONTRACT.md` — draft wire-protocol notes (not yet authoritative)
- `contracts/MOTOR_*.md` — draft per-series notes (not yet authoritative)

## License

Proprietary — MyActuator.
