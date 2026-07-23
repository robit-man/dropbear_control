# Exact CAN adapter manifest intake

The adapter intake records enough evidence to decide between an installed
ESP32 TWAI peripheral and an external MCP2515. It contains no concrete driver,
does not modify the preserved ESP32 runtime and cannot perform I/O.

## Exact manifest tuple

Every reviewed manifest binds:

- purpose: `listen_only_capture` or `runtime_gateway`;
- canonical configuration and installed-inventory submission;
- robot asset and controller location;
- controller kind/part/silicon, board model/revision and integrated/SPI
  connection;
- transceiver part/revision, controller clock/source, voltages, termination
  and every CAN/SPI/interrupt/standby GPIO;
- PlatformIO environment, framework, exact driver/version and source,
  binary and configuration hashes;
- one calculated 1-Mbit/s timing tuple: clock divider, time segments, SJW,
  total time quanta, sample point and bitrate error;
- controller-enforced listen-only state separately from an observed
  independent transceiver-standby, isolator or power-removal mechanism;
- bounded RX/TX queues, explicit overflow policy, loss-counter widths,
  timestamp clock/resolution/wrap and monotonicity;
- warning, error-passive, bus-off, manual recovery and fresh-session policy;
  and
- independent competent human review and evidence references.

The validator recalculates bitrate, sample point and error. It also enforces
non-overlapping GPIOs and exact controller/connection/driver combinations:
TWAI uses the integrated CAN TX/RX pins and `esp-idf-twai`; MCP2515 uses SPI,
chip-select and interrupt pins and `autowp-mcp2515`.

## Purpose non-substitution

A listen-only manifest requires controller listen-only mode and a zero-depth
TX queue. A runtime manifest requires normal controller mode and a nonzero
bounded TX queue. Both require a separately observed, default-disabled
physical TX mechanism.

The two purposes cannot substitute for each other. A reviewed manifest also
remains unselected: separate installed-hardware and purpose-selection
decisions are still required.

## Fail-closed host factory

`CanAdapterIntakeRegistry.describe_no_io()` returns only an immutable
descriptor with `physical_io`, support and physical-motion authority false.
`create_physical()` always raises, even for a structurally valid synthetic
manifest. No default, first-match, controller-family or purpose fallback
exists.

## Current baseline

- reviewed manifests: 0;
- TWAI manifests: 0;
- MCP2515 manifests: 0;
- listen-only selections: 0;
- runtime selections: 0;
- physical factory enabled: false; and
- support/motion: false.

## Commands

```sh
python3 tools/manage_can_adapter_intake.py --generate
python3 tools/manage_can_adapter_intake.py --check
tests/can_adapter_intake/run_tests.sh
```

Synthetic TWAI/MCP2515 and listen-only/runtime fixtures prove schema and
semantic behavior only. They are not installed observations and are never
written to the tracked intake namespace.
