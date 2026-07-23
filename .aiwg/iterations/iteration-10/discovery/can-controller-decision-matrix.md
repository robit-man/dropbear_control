# Iteration 11 ESP32 CAN-controller decision matrix

Status: `NO-CONTROLLER-SELECTED`

The current runtime mentions MCP2515-era code, but a source include or library
dependency is not evidence of installed hardware. Native ESP32 TWAI and an
external MCP2515 remain candidates until the installed-inventory record and
bench evidence identify one exact path.

| Decision fact | ESP32 TWAI candidate | External MCP2515 candidate | Admission evidence |
|---|---|---|---|
| physically populated controller | unknown | unknown | PCB/board revision and component evidence |
| exact controller part/revision | unknown | unknown | marking plus official datasheet |
| controller clock/oscillator | unknown | unknown | board evidence and clock source |
| pins and mux/SPI chip select/IRQ | unknown | unknown | schematic or reviewed continuity map |
| transceiver part/voltage/isolation | unknown | unknown | marking, schematic and datasheet |
| 1 Mbit/s sample point and timing error | uncomputed | uncomputed | exact-clock bit-timing calculation |
| standard 11-bit acceptance filters | unproved | unproved | driver configuration plus fake/bench conformance |
| controller-enforced listen-only | unproved | unproved | controller specification and no-TX measurement |
| independent physical TX disable | unproved | unproved | transceiver silent/standby or isolated TX path proof |
| RX monotonic timestamp source | unproved | unproved | timer source/resolution/wrap evidence |
| RX FIFO and software queue bounds | unproved | unproved | capacity, WCET and overflow injection |
| cumulative dropped/overflow counters | unproved | unproved | fault-injection result |
| error-warning/passive/bus-off state | unproved | unproved | injected-state conformance |
| recovery policy | unreviewed | unreviewed | explicit bounded state machine |
| exact SDK/library and binary hash | absent | absent | reproducible build record |
| wiring/termination/ground boundary | unknown | unknown | installed inventory and isolated setup review |

## Selection rule

Selection requires every row for one physically present path to be evidenced
and reviewed. The decision records the exact board/controller/transceiver,
pins, clock, driver version, configuration hash and intended purpose. A
capability known for a controller family cannot fill an installed fact.

TWAI is not preferred merely because it is native. MCP2515 is not preferred
merely because prototype code exists. Neither candidate is selected now.

## Purpose partition

The first selectable purpose is `LISTEN_ONLY_CAPTURE`, which must enforce
receive-only operation in the controller and an independent TX-disable
boundary. `RUNTIME_GATEWAY` is a distinct later decision and requires
synchronous TX acceptance, bounded scheduling, bus-state handling, exact
protocol applicability, readiness and HIL. A listen-only decision cannot be
reused as runtime-gateway authority.

## Decision gate

The electrical reviewer and hardware owner sign the exact selection. The
safety reviewer separately approves the setup and phase. Until then, no
adapter wrapper, pin assignment, driver installation or firmware integration
is authorized.
