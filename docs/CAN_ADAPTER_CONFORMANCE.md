# CAN adapter conformance and listen-only evidence contract

Status: `OFFLINE-FAKE-DRIVER-PROVEN`; no real ESP32 controller is admitted and
no physical CAN traffic has been captured.

## Purpose and authority boundary

`runtime/can_adapter_contract` is the controller-independent boundary between
an eventual ESP32 CAN driver and `NativeCanTransport`. It does not implement
TWAI, MCP2515, SPI, pins, interrupts, a transceiver or recovery. It rejects a
driver unless the driver reports all capabilities required by its selected
purpose.

Two purposes are closed and mutually exclusive:

| Purpose | Required mode/filter | TX result | Evidence meaning |
|---|---|---|---|
| `LISTEN_ONLY_CAPTURE` | Controller-enforced listen-only, full 11-bit `0x000..0x7ff` filter | Always `TX_DISABLED`; driver `transmit` is never called | Observation of frames only |
| `RUNTIME_GATEWAY` | Normal mode, exact V4.4 response range `0x241..0x260` | Only driver-confirmed synchronous acceptance becomes `SENT` | Offline adapter behavior until real tuple/HIL gates pass |

Both require 1 Mbit/s, standard-ID filtering, DLC 8 capability, monotonic RX
timestamps with declared resolution, bus-state reporting and a cumulative RX
loss counter. Runtime mode additionally requires a synchronous controller-
acceptance result. Listen-only mode additionally requires an explicit
controller capability stating that transmission is disabled—not merely an
application promise not to call transmit.

## Fail-closed outcome map

| Driver/controller evidence | Portable outcome | Runtime action |
|---|---|---|
| Exact frame accepted by controller | `SENT` | Response slot remains pending; still not proof of on-wire delivery or motion |
| Controller queue cannot accept now | `WOULD_BLOCK` | TX failure disposition and safety fault in the current conservative runtime |
| Error passive | `ERROR_PASSIVE` | Distinct service result, response slot cleared, safety fault latched |
| Bus off | `BUS_OFF` | Distinct bus-off result/disposition, response slot cleared, safety fault latched |
| Listen-only attempted TX | `TX_DISABLED` | Driver is not called; safety fault if a command reached this mode |
| Wrong bus, recovery, warning/non-active TX state | `NOT_READY` | Response slot cleared and safety fault latched |
| Extended/RTR/non-DLC-8/malformed request | `INVALID_FRAME` | Driver is not called |
| RX counter increase or driver overflow | `OVERFLOW` | Capture/runtime is not lossless; safety fault latched |
| RX timestamp/counter regression, wrong bus/filter/shape | `IO_ERROR` | Evidence rejected; safety fault latched |

The conservative handling of `WOULD_BLOCK` is intentional for this iteration:
there is no bounded retry deadline/WCET proof yet. A later policy may retain a
frame for retry only after queue bounds and final safety re-authorization are
specified and tested.

## Append-only capture record

Every JSONL line must satisfy
`schemas/myactuator-can-listen-capture-record.schema.json`. Repeated context is
deliberate: each record independently retains capture/controller/clock/frame/
counter/provenance/evidence-boundary data. Whole-stream validation additionally
requires:

1. sequence starts at one and is contiguous;
2. the monotonic timestamp never regresses;
3. controller, clock, capture, provenance and evidence boundary never drift;
4. DLC equals the number of encoded data bytes;
5. receive counters strictly increase and loss/overflow counters never regress;
6. dropped and overflow totals remain zero for a valid evidence capture; and
7. every record remains RX-only, standard, non-RTR, controller listen-only,
   support false, motion false and protocol applicability unverified.

Run:

```bash
python3 tools/validate_can_capture.py assets/myactuator/can_captures/<capture>.jsonl
```

The validator counts DLC-8 IDs in the V4.4 request/response ranges as *shape
candidates*. It does not decode them or promote protocol applicability. A
bench applicability decision still requires exact motor model, hardware,
drive firmware, transport, control mode, setup provenance and a reviewed
comparison against official vectors.

## Required evidence before a concrete ESP32 adapter

- exact ESP32 board/controller revision and whether TWAI or external MCP2515 is
  physically populated;
- oscillator frequency and bit-timing calculation for 1 Mbit/s;
- transceiver part, voltage domains, standby/silent pins and verified
  controller-enforced listen-only behavior;
- connector/pinout, bus topology, termination and isolated analyzer setup;
- monotonic timestamp source/resolution/wrap behavior and interrupt latency;
- RX FIFO/queue bounds, loss counter behavior and overflow injection;
- state transitions for error-warning, error-passive, bus-off and recovery;
- binary/config hashes plus operator/setup identity in each capture; and
- an explicit hardware authorization before connecting even listen-only to the
  robot, followed by a separate authorization before isolated TX HIL.

The preserved PAL/CANBus/MCP2515 prototype does not satisfy this contract and
is not wrapped by the adapter.

The no-I/O manifest boundary is documented in
[CAN_ADAPTER_MANIFEST_INTAKE.md](CAN_ADAPTER_MANIFEST_INTAKE.md). It records
the exact installed tuple needed before either TWAI or MCP2515 can be selected;
the current intake contains zero manifests and its physical factory is
structurally disabled.
