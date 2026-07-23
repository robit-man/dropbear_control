# Independent safe-power survey and measurement plan

Status: `PLAN-ONLY-NO-ENERGY-AUTHORITY`

The objective is to learn how energy reaches and leaves the controller and
drives without relying on software, CAN or the ESP32. No survey is executed
under Iteration 10.

## Survey questions

- Which owner controls each battery, DC supply, contactor, precharge path,
  fuse, breaker, E-stop, enable and brake supply?
- Which mechanism removes drive energy independently of host, gateway and
  drive firmware?
- What feedback proves contactor/E-stop/power state, and is that feedback
  independent of commanded state?
- Which stored electrical, gravitational, elastic or pneumatic energy remains
  after removal?
- What is the worst-case measured removal latency at controller and drive
  terminals, including welded-contact, failed-feedback and lost-control-power
  cases?
- What safe state results from loss of host, ESP32, CAN, sensor, enable,
  contactor feedback and facility power?

## Planned measurements

| Measurement | Owner | Reviewer | Prerequisites | Abort | Evidence |
|---|---|---|---|---|---|
| de-energized topology trace | qualified electrical operator | hardware owner | unpowered authorization and drawings | unknown conductor or stored energy | marked schematic/photo hashes |
| protective-device identity/rating | electrical operator | safety reviewer | visible labels only | enclosure work exceeds authorization | exact part/rating evidence |
| power-state feedback independence | controls engineer | safety reviewer | separate powered authorization/test fixture | feedback shares unreviewed failure path | I/O trace and fault tree |
| removal latency | power-removal owner | independent instrumentation operator | restrained load, approved energization, rated isolated probes | any motion/envelope/probe anomaly | raw synchronized traces and uncertainty |
| stuck/welded/feedback fault response | safety test team | independent safety reviewer | reviewed injection method and rollback | safety layer defeated beyond approved scope | injection log and result |

## Acceptance boundary

The power path is not ready until an independent reviewer accepts the
schematic, component identities, state sensing, failure analysis, measured
latency distribution, uncertainty, environmental envelope and repeatability.
Passing one removal does not establish a safety function or performance level.
No result grants command authority by itself.
