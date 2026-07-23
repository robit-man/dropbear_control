# Fault evidence and restart-latch core

[`fault_evidence.h`](../firmware/esp32/src/safety/fault_evidence.h) and
[`fault_evidence.cpp`](../firmware/esp32/src/safety/fault_evidence.cpp) provide
the allocation-free offline core for `SAF-006` and `TST-SAF-006`. They extend
the deterministic safety supervisor with bounded fault context, integrity
checking, restart restoration and explicit guarded reset. They perform no
storage, clock, bus, actuator or cryptographic I/O.

## Boundary

The core never treats a software request as physical motor-off evidence. A
future vetted persistence adapter must:

1. provision the initial clean snapshot exactly once;
2. serialize every named snapshot field canonically;
3. durably replace the prior snapshot after each fault event and accepted
   reset;
4. supply the most recent snapshot before normal boot processing;
5. fail the platform boot if durable write or read cannot be proven; and
6. bind records to the platform boot/session and artifact/configuration
   identities outside this storage-free core.

Calling `createInitialCleanSnapshot()` after a previous run would discard a
possible fault latch and violates the integration contract. The function is a
first-provisioning mechanism, not a restart fallback.

## Captured record

One fault generation retains up to eight complete ordered events and counts
additional bounded overflow. The first event remains the primary cause.
Every stored event contains:

- an immutable boot identity, monotonic time and pre-fault supervisor state;
- an explicit optional command context with owner, session, sequence,
  deadline, configuration generation/digest, route, bus, node, opcode and
  requested/admitted native values;
- explicit feedback validity bits plus generation, sample/receive times,
  position, velocity, q-axis current, output effort, temperature, voltage and
  following error in fixed integer units; and
- bus-off state, frame/error/timeout/recovery counters and last receive time.

Absent command or feedback context is encoded as a canonical zero-valued
record, rather than an invented observation. Invalid or contradictory live
context itself becomes `FAULT_EVIDENCE_INVALID` and faults closed.

## Persistence semantics

`PersistentFaultSnapshot` is a named-field container, not a raw struct-layout
storage ABI. Its CRC32C covers every semantic field in a fixed little-endian
order. Recovery rejects:

- missing snapshots;
- wrong magic or schema version;
- checksum drift;
- impossible clean/latched counters;
- generation mismatch;
- unknown reasons, states or feedback bits;
- malformed command or feedback presence; and
- hidden data in unused event slots.

A missing or corrupt recovery snapshot creates a new
`FAULT_EVIDENCE_INVALID` latch and moves the supervisor to `FAULT`. Restoring a
valid latched snapshot also moves a fresh supervisor to `FAULT`. Link
reconnect, configuration reload and a process restart therefore have no
implicit path to `DISABLED`, `ARMED` or `ENABLED`.

## Reset transaction

Reset requires the exact fault generation and four adapter assertions:

- the fault record is durable;
- the root cause is absent;
- tuple-specific motor-off has been observed; and
- the reset event is durable.

The existing supervisor then independently checks session, monotonic sequence,
reset-owner authorization, current configuration integrity, recovered
prerequisites and motor-off confirmation. Any failed check preserves both the
fault record and `FAULT`. Success clears the active record but preserves the
monotonic generation watermark and returns only to `BOOT`. Discovery, lease
acquisition and enable remain separate later operations.

These booleans are adapter assertions, not proof of persistence or physical
state. Production integration remains open until the storage, audit,
authentication, exact-tuple safe-action and independent power-removal paths
are implemented and verified at their required evidence classes.

## Verification

Run:

```bash
tests/safety/run_tests.sh
```

The suite compiles both portable cores with C++11 warnings-as-errors and
checks clean provisioning, full command/feedback/bus capture, secondary-event
ordering, bounded overflow, missing/corrupt/semantically mutated snapshots,
reconnect/reload/restart retention, malformed live events, reset guards,
generation advance and the absence of automatic re-enable.
