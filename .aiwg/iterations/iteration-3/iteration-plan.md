# Iteration 3 dual-track plan — canonical config propagation and host link

- Iteration status: `COMPLETE-OFFLINE`
- Phase context: P1 / Elaboration
- Delivery scope: WP-030-T05/T06, WP-060-T01..06 and offline config-admission
  portions of WP-070/WP-170
- Discovery horizon: real ESP32 adapter/scheduler and host lifecycle in WP-080
  and WP-110
- Safety boundary: no hardware I/O, physical applicability, remote actuation,
  runtime firmware replacement, or motion enable

## Iteration intent

Create the first coherent configuration and messaging boundary between
Dropbear’s high-level/host layers and a future ESP32 gateway. Every layer must
consume the same canonical configuration identity, while malformed, stale,
replayed or mismatched inputs fail before admission or native transmission.
The existing 64-byte browser/serial prototype remains a migration input, not
the new authority.

## Delivery acceptance matrix

| ID | Outcome | Principal checks | Evidence class |
|---|---|---|---|
| I3-D01 | One documented host-link V1 envelope and typed message set | version/length/type/session/sequence/time/config hash/CRC round-trip; strict bounds | OFFLINE-UNIT |
| I3-D02 | Bounded incremental stream recovery | fragmented/concatenated/noisy/corrupt input resynchronizes within declared memory/work bounds and emits no invalid message | OFFLINE-UNIT |
| I3-D03 | Typed command/state/disposition contracts | identity/config/lease/mode/SI command fields; state age/validity/health/fault/safety; separate lifecycle dispositions | OFFLINE-UNIT |
| I3-D04 | Fail-closed compatibility and replay policy | major/capability/rate mismatch, duplicate/reorder and prior session reject before command exposure | OFFLINE-UNIT |
| I3-D05 | Deterministic generated views | firmware/host/ROS/UI/simulator views reproduce from one validated input and carry identical digest/identity | OFFLINE-STATIC |
| I3-D06 | Unknown-state preservation | generation never fills native IDs, owners, tuples, limits, calibration, CAD or enable authority and never turns motion on | OFFLINE-UNIT |
| I3-D07 | Atomic config identity guard | no config at boot; exact staged/commit token; invalid update rollback; revoke/stale/hash/revision mismatch denies | OFFLINE-NATIVE |
| I3-D08 | Safety composition | missing or invalid config cannot arm/enable/pass TX and an accepted config never auto-enables | OFFLINE-NATIVE |
| I3-D09 | Unified evidence | all new suites run from `tools/test_all.sh`; trace/test/WP claims match actual coverage | OFFLINE-BUILD |

## Discovery questions

1. Which fields and semantics in the legacy 64-byte serial frame must be
   retained only as migration fixtures, and which are unsafe or ambiguous?
2. Where will host-link V1 framing terminate on ESP32: USB CDC, UART, TCP or a
   transport-neutral byte-stream adapter?
3. Which generated view is consumed by each future firmware/host/ROS/UI/sim
   component, and how is its canonical digest compared at startup?
4. How will the link session and safety lease relate without allowing a link
   reconnect to recreate command authority?
5. Which gateway scheduler dispositions can be observed offline, and which
   require SIL/HIL native transport evidence?

## Definition of Done

- [x] All I3-D01..I3-D09 outcomes have executable evidence.
- [x] The host-link parser is bounded and fuzz/property tested without external
  hardware.
- [x] The command contract contains exact source, configuration and lease context; raw
  vendor frames are not a public command type.
- [x] Generated views reproduce without drift and retain the incomplete input’s
  non-enableable state.
- [x] The config identity guard composes with the safety core and cannot
  auto-enable.
- [x] Existing user firmware/web/serial work is preserved.
- [x] Documentation calls the new link and guard reference/offline components,
  not physical or production release evidence.
- [x] The unified gate, traceability linter and whitespace checks pass.

## Explicit non-goals

- Binding V1 to real USB/UART/CAN hardware.
- Changing the user’s current `SerialBridge` or browser frame implementation.
- Selecting physical node IDs, exact motor tuples, limits or calibration.
- Implementing torque conversion, a motor plant, ROS 2 plugin or rigid-body
  simulation.
- Authenticating remote operators or authorizing remote actuation.
- Claiming powered support from generated configuration or passing tests.
