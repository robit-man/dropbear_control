# Future isolated listen-only CAN capture runbook

Status: `DESIGNED-SEPARATE-POWERED-AUTHORIZATION-REQUIRED`

This is a future campaign design, not an instruction to connect hardware now.
It begins only after the unpowered inventory is independently accepted, a CAN
controller is selected, controller-enforced listen-only and physical TX
disable are proven, and a new authorization explicitly permits the powered
capture. Approval of the unpowered inventory does not approve this runbook.

## Required roles

- Hardware owner: controls asset access and exact configuration.
- Safety reviewer: owns isolation, power-state and abort approval.
- Electrical operator: builds and operates the isolated receive path.
- Independent capture reviewer: verifies setup, logs, counters and custody.
- Power-removal owner: can remove energy without relying on capture firmware.

One person may not self-approve setup and evidence.

## Preconditions

1. exact accepted installed inventory and controller decision;
2. reviewed schematic/pinout, 1-Mbit/s bit timing and termination plan;
3. controller listen-only configuration plus physical transceiver TX disable;
4. isolated analyzer/receiver with no path able to drive CANH/CANL;
5. independent power removal tested without the ESP32 or host;
6. receive timestamp, loss, overflow and bus-state instrumentation validated
   on an isolated synthetic CAN source;
7. exact firmware source/binary/config hashes;
8. capture ID, clock, duration, expected load envelope and storage assigned;
9. rollback/abort briefing; and
10. signed powered-listen-only authorization for the exact setup.

## Execution phases

| Phase | Owner | Independent hold point | Abort condition | Required evidence |
|---|---|---|---|---|
| L0 setup inspection, all power absent | electrical operator | safety reviewer | wiring/ground/termination/config differs from approval | setup photos, continuity and config hashes |
| L1 TX-disable proof on isolated test source | electrical operator | capture reviewer | any dominant bit or transmit path possible | measurement trace and controller state log |
| L2 attach receive-only boundary while robot remains off | electrical operator | safety reviewer | unexpected continuity/ground/current | connection checklist |
| L3 controlled robot power-up by approved owner | power-removal owner | safety reviewer | unexpected state, sound, heat, movement, bus fault | power-state event log |
| L4 bounded capture | electrical operator | capture reviewer | any TX request/counter, RX loss, overflow, clock regression, bus-off, movement or envelope violation | append-only JSONL plus raw capture/hash |
| L5 independent power removal | power-removal owner | safety reviewer | removal path fails or latency exceeds approved bound | shutdown timestamps |
| L6 disconnect, hash and seal | electrical operator | capture reviewer | custody gap or hash mismatch | immutable manifest/reviewer record |

## Acceptance

- frames are RX-only, standard and non-RTR;
- capture sequence/timestamps/counters are monotonic;
- dropped and overflow totals are zero;
- clock resolution and duration meet the predeclared bounds;
- bus state and load remain inside the approved envelope;
- every record has the exact controller, transceiver, binary, config, setup,
  operator and capture identity; and
- the stream passes `tools/validate_can_capture.py`.

Frame shapes remain uninterpreted observations. Even an apparent V4.4 ID/DLC
does not prove installed model/firmware applicability, safe TX, actuator
mapping, calibration, limits or support.

## Absolute aborts

Any motion; unexpected brake release; sound, odor or heat; ground/isolation
change; dominant-bit evidence; a TX call or TX counter; error-passive or
bus-off; dropped/overflow data; timestamp regression; loss of the independent
power-removal owner; or deviation from the exact approved setup ends the
campaign. No automatic restart or recovery is allowed.
