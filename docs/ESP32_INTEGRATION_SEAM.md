# ESP32 no-loss integration seam

Status: `OFFLINE-ADAPTER-FOUNDATION`; not connected to powered hardware.

This document defines how the preserved ESP32 prototype can be migrated to the
canonical host-link, configuration, safety, gateway and native-protocol cores
without silently dropping fields or creating another command owner. It is an
integration specification and test boundary, not permission to upload or move
an actuator.

## Current executable paths and ownership

| Path | Current behavior | Evidence / risk | Migration disposition |
|---|---|---|---|
| `main.cpp -> ProtocolAbstractionLayer::processCommands()` | Polls CAN/RS485/EtherCAT prototype transports | Generic CAN `sendFrame()` returns success without I/O; parsers do not decode command values | Keep compiling, never bind to physical output; remove from the production loop only after captured behavior tests exist |
| `main.cpp -> SerialBridge::update() -> MotorController` | Parses the user-authored 64-byte browser frame and directly selects position/velocity/torque states | No session, negotiation, exact config, lease, final safety check or disposition; current is reported in the torque field | Preserve as a toy/diagnostic prototype; disable physical driver binding before any production runtime is enabled |
| `MotorController -> IMotorDriver` | Calls a family driver from controller state | Family drivers and tuple applicability are unverified; no response correlation | Retain for migration comparison only; do not adapt into the canonical gateway |
| `ProtocolAbstractionLayer -> CANBus` | Prototype generic transport | 500 kbit/s comments, extended-ID claims and success stub conflict with official V4.4 evidence | Replace rather than wrap |
| `MCP2515CAN` | Calls the Watterott MCP2515 library | Uses 500 kbit/s default and `0x100 + ID`; receive loses the native frame contract; filters/interrupt configuration report success without implementation | Hardware hypothesis only; a new adapter must use standard DLC-8 frames, explicit clock/bitrate and real error outcomes |
| `hostlink_v1` | Allocation-free, versioned typed frame/message codec | Offline only; not bound to a UART/USB task | Production ingress candidate after authenticated session policy exists |
| `security_authorization_core` | Allocation-free post-auth role/action, generation, replay and bounded audit policy | Consumes trusted identity/integrity assertions; performs no authentication, signature verification or I/O | Required between authenticated transport and typed command ingress; disconnected from `main.cpp` |
| `artifact_trust_core` | Allocation-free exact verifier-assertion, rollback, stage/commit/abort/reboot semantics | Performs no cryptography, persistence, OTA, audit I/O or motion; current security profile is unselected | Required around signed config/calibration/firmware/evidence activation after vetted adapters exist; disconnected from `main.cpp` |
| `config_identity_guard` | Atomic staged identity/generation admission | Loader and authenticated expectation remain external | Required in every production command path |
| `safety_supervisor` | Lease/state/fault/shutdown intent | Hardware interlock and trusted motor-off acknowledgement absent | Required, but cannot substitute for independent power removal |
| `fault_evidence` / `fault_monitor` | Bounded restart latch plus deterministic config/bus/response/drive/limit/feedback arbitration | Storage, UTC/audit and trusted ESP32 observation adapter absent | Required before normal service; current portable cores cannot prove a physical safe state |
| `gateway_core` | One-owner route, bounded queues, final config/safety checks, response correlation | Routes are synthetic; no installed tuple evidence | Production scheduling candidate after generated routes are complete |
| `gateway_transport_runtime` | Bounded native RX/TX pump, distinct bus-off and consecutive-response budget over an injected adapter | Fake/native-host tested; no ESP32 hardware or fault-context adapter | First isolated integration slice; remains disconnected from `main.cpp` |
| `host_command_ingress` | Owns Host Link session acceptance and maps an exact static binding into a gateway submission | Synthetic CURRENT_Q path tested; no installed tuple/route/limit evidence | M2 offline core; remains disconnected from `main.cpp` and supports no physical actuator |
| `host_gateway_egress` | Correlates gateway events/native observations into typed Host Link dispositions/state | Native tests cover total phase/code/safety maps, stale time and response field closure; no serial task | M2 offline return path; IQ remains distinct from absent effort and response is not mechanics |
| `can_adapter_contract` | Requires exact purpose/mode/filter/timing/state/loss/TX capabilities from an injected controller driver | Scripted fake-driver conformance only; listen-only TX is structurally disabled | M3 contract and capture format exist; no concrete ESP32 controller adapter or physical capture |
| generated Dropbear firmware view | Twelve explicit but incomplete observations | `kMotionEnableAllowed == false`; model, ownership, native IDs, limits and calibrations unknown | May be compiled/read for diagnostics only; cannot generate routes or arm |

There are currently at least two active prototype command owners in
`main.cpp`: PAL processing and the WebSerial bridge/controller path. The
canonical gateway runtime is deliberately not a third owner. Production mode
must be a mutually exclusive build/runtime selection with only the canonical
gateway able to reach a physical transport.

## Required one-way data path

```text
authenticated host transport bytes
  -> selected platform root/profile and vetted peer authenticator
  -> bounded Host Link V1 parser
  -> negotiated session + monotonic sequence/replay check
  -> post-auth role/action policy + audit (`PASS_TO_NEXT_GATE` only)
  -> typed Command (canonical actuator/config/source/lease/mode/SI values)
  -> exact generated actuator/route lookup
  -> command-mode-specific native V4.4 encoder
  -> GatewayCore::enqueue
  -> final ConfigIdentityGuard check
  -> final SafetySupervisor lease/state check
  -> GatewayCore::pollTransmit
  -> NativeCanTransport::tryTransmit
  -> explicit SENT / WOULD_BLOCK / BUS_OFF / IO_ERROR / INVALID_FRAME result
  -> native response with bus + receive timestamp
  -> GatewayCore response correlation
  -> typed state/validity/age/health observation
  -> Host Link State + Disposition/Fault output
```

No arrow may be skipped. Browser, ROS, diagnostics, replay and controllers all
terminate at the same typed command ingress. None receives an `IMotorDriver`,
PAL, MCP2515 or raw native-frame reference.

The M2 ingress core is now implemented as
`runtime/host_command_ingress`. It owns `SessionReceiver`, so a decoded command
cannot be passed around it into native translation. A reviewed static binding,
not host input, supplies route, bus, node, owner, safety configuration,
translation kind, 0.01 A/LSB evidence and raw-current bounds. The initial
surface supports only CURRENT_Q and rejects every other valid Host Link mode.
It rejects off-grid values, overflow and sub-millisecond deadlines rather than
rounding, clamping or extending a lease. Its successful steel thread is
synthetic protocol evidence only.

The inverse M2 core is implemented as `runtime/host_gateway_egress`. Every
gateway phase and rejection code has a stable Host Link disposition. State
requires an exact transaction/route/node/owner/session/safety-sequence/command-
generation match plus an explicit `OBSERVED` native-state handoff. Motion
responses expose output angle, speed, q-axis current and temperature; status-1
responses expose voltage/error evidence. No response populates effort, a
correlated response alone leaves bus health unknown, and no typed message is a
claim of mechanical execution.

## No-loss field mapping

| Host/config fact | Gateway/native destination | Rule |
|---|---|---|
| canonical actuator ID | exact generated actuator row and route token | Unique exact match; never numeric list index or family fallback |
| config ID/revision/SHA-256 | `ConfigReference` and frame envelope digest | All representations must agree with the active atomic generation |
| source identity | static owner ID policy | Client cannot select priority or another owner |
| lease ID/owner/sequence/expiry | negotiated session plus `MessageStamp` and deadline | Expired, reordered, cross-session or over-horizon command is rejected before encode/TX |
| mode and presence mask | one admitted native opcode/encoder | Position, velocity, effort, q-axis current and impedance are not interchangeable; unsupported modes reject |
| SI position/velocity | checked V4.4 quantization | Apply reviewed motor-to-joint sign/ratio exactly once; reject overflow |
| SI effort | no native field until torque constant/transmission evidence exists | Never relabel q-axis current as torque |
| q-axis current | V4.4 `0xA1`, 0.01 A/LSB | Only an exact tuple with current-mode applicability and limits may encode |
| absolute command deadline | gateway submission deadline | Rechecked immediately before transport exposure |
| native bus/node | generated route and standard CAN arbitration ID | Client-supplied bus/node values are forbidden |
| TX result | disposition | `SENT` is distinct from adapter failure, native response and mechanical observation |
| RX frame/bus/timestamp | correlated response slot | Wrong bus/node/opcode, malformed, duplicate and late responses remain distinct |
| drive sample | typed state with time/validity/connectivity/health | Echo or response receipt never fabricates position, effort or motor-off |

## Transport adapter contract implemented offline

`runtime/gateway_transport_runtime` is C++11, exception-free, RTTI-free,
allocation-free and Arduino-independent. Each service call has configured hard
bounds of at most 16 RX frames and 16 TX attempts. It:

1. services safety time/lease expiry;
2. starts one monotonic gateway cycle;
3. expires native-response deadlines, accumulates the bounded consecutive
   streak and faults before transmit polling when the configured budget is
   exceeded;
4. drains no more than the RX budget and preserves bus/timestamp/frame;
5. exposes no more than the TX budget after the gateway's final checks;
6. records a real adapter failure, clears its response slot and latches an
   external safety fault;
7. distinguishes bus-off from other send failures; and
8. retries a failed safety action on a later cycle after transport recovery.

`NoIoCanTransport` remains the only unconditional fail-only adapter.
`ConformingNativeCanAdapter` is a tested wrapper around an injected driver, but
there is no concrete ESP32 driver implementing that port. Its listen-only
purpose can never call transmit; its runtime purpose returns `SENT` only after
driver-confirmed controller acceptance. The legacy `CANBus` success stub is
not an implementation of either interface.

The gateway's `NATIVE_TX` disposition currently means the finally admitted
frame was exposed to the adapter for an immediate attempt. A following
`TRANSPORT_TX_FAILED` or `TRANSPORT_BUS_OFF` disposition retracts any response
expectation and latches safety. Future hardware timing evidence may justify a
separate prepared/accepted/on-wire phase; until then a response remains the
only evidence that a drive received a frame, and neither event is mechanical
execution evidence.

## Migration sequence and gates

| Stage | Mutation allowed | Exit evidence | Powered output |
|---|---|---|---|
| M0 — preserved baseline | Compile user PAL/WebSerial work and isolated canonical cores | Unified offline gate; this inventory | Forbidden |
| M1 — fake adapter | Compose generated synthetic route, config guard, safety, gateway and bounded transport runtime | Native sanitizers; send/bus-off/response/deadline/fairness tests | Forbidden |
| M2 — host-link ingress | Translate V1 typed commands into gateway submissions with exact mapping and dispositions | Golden cross-language vectors, fuzz/replay tests, no raw escape | Forbidden |
| M3 — ESP32 listen-only adapter | Initialize exact controller/clock/bitrate, receive and timestamp only; TX electrically/software disabled | Controller error-state/filter/timestamp captures and target timing | Forbidden |
| M4 — TX loopback/HIL | Enable adapter TX only into isolated analyzer/emulator; verify IDs/DLC/data/outcomes/bus-off | Logic-analyzer/CAN capture plus fault-injection evidence | No motor connected |
| M5 — one unloaded motor | Exact hardware tuple, current-limited supply, independent cut, verified stop/brake, reviewed route/limits/sign | Bench protocol capture, watchdog/stop latency and thermal procedure | Explicit supervised bench only |
| M6 — one six-actuator leg | Unique ownership, utilization, sensors/calibration and HIL stop paths | Six-route HIL matrix and endurance | Explicit supervised HIL only |
| M7 — Dropbear physical backend | Common ROS lifecycle, full canonical robot config, estimator/controller cross-backend tests | Robot release evidence and operations approval | Release policy only |

Advancement is monotonic. Failing a stage does not authorize a fallback to PAL,
WebSerial direct control, a family driver, open-loop Gazebo, or browser toy
dynamics.

## Required adapter work before M3

- choose the actual ESP32 CAN peripheral/controller and transceiver for each
  controller revision;
- record oscillator, SPI/pin wiring, standard-ID filtering and 1 Mbit/s timing;
- implement controller reset/listen-only/normal states and explicit
  arbitration-lost, TX error, RX overflow, error-passive and bus-off outcomes;
- timestamp RX at the adapter boundary with a monotonic clock;
- define bounded queue ownership and WCET/stack budgets;
- prove that diagnostic load cannot starve a safety action;
- generate routes only from a complete verified Dropbear configuration;
- remove or build-exclude every competing physical writer; and
- route logs away from the framed machine channel.

## Current hard holds

- Dropbear configuration is incomplete and motion admission is false.
- All 12 installed motor model/hardware/firmware/protocol tuples are unknown.
- Bus ownership, native node IDs, limits, signs, calibration and hip-yaw
  feedback are unresolved.
- No installed-actuator current limit/applicability or current-to-torque
  conversion is accepted; only the explicitly synthetic 0.01 A/LSB IQ test
  binding exists.
- Brake applicability and safe motor-off behavior are unverified.
- No independent power-removal input/contactor is integrated.
- No real CAN adapter implements `NativeCanTransport`.
- No authenticated ESP32 byte transport or production runtime task owns and
  feeds the offline Host Link V1 parser/ingress core.
- No credential/bootstrap/key mechanism produces the trusted identity and
  integrity assertions consumed by `security_authorization_core`, and the core
  is not yet composed into the gateway call path.
- The exact current `esp32dev` profile has Secure Boot, flash encryption, boot
  anti-rollback, encrypted NVS and secure-element use disabled, compiles legacy
  TLS 1.0/1.1 and has no dedicated security-state partition.
- No vetted verifier, encrypted persistent replay store, durable audit sink or
  OTA installer produces the assertions/receipts consumed by
  `artifact_trust_core`; its successful tests are transaction semantics only.

Therefore the production integration remains fail-closed and offline despite
the successful compile and fake-transport tests.
