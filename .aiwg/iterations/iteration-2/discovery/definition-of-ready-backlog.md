# Iteration 3 Definition-of-Ready backlog

`READY-OFFLINE` means the work can start without hardware authority.
`READY-INSPECTION` means passive, unpowered inspection can start only under an
approved local procedure. `NOT-READY` names missing evidence or a decision.

| ID | Candidate outcome | Depends on | Acceptance evidence | DoR status |
|---|---|---|---|---|
| I3-001 | Add pinned Draft 2020-12 structural validation to CI while retaining semantic validation | schema v1; dependency/change policy | positive/negative schema corpus, pinned tool/version, explicit structural vs semantic reporting | READY-OFFLINE |
| I3-002 | Build a read-only legacy import report rather than runtime defaults | incomplete example; legacy source | deterministic 12-ID/10-sensor/alias report; no generated enable config | READY-OFFLINE |
| I3-003 | Define generated firmware/host/ROS/UI/simulator view contracts and canonical digest propagation | schema v1; ADR-001 | interface schemas and parity/hash-mismatch tests | READY-OFFLINE |
| I3-004 | Add config admission tests to the offline safety core | semantic validator; safety-state-machine | incomplete, tampered, stale and mismatched configs cannot leave BOOT/DISABLED | READY-OFFLINE |
| I3-005 | Record physical controller, motor and wiring inventory | approved passive inspection; repository ownership; SRC-016 record format | labeled devices, serials, revisions, wiring/termination and operator/UTC evidence | READY-INSPECTION after procedure approval |
| I3-006 | Resolve physical bus segmentation and unique controller ownership | I3-005 | peer-reviewed topology and exactly one owner per bus/actuator | NOT-READY — physical inventory missing |
| I3-007 | Instantiate 12 exact actuator support tuples | I3-005/I3-006; applicable manuals | no UNKNOWN/wildcard fields; clause/applicability links; unsupported capabilities explicit | NOT-READY — installed tuple evidence missing |
| I3-008 | Resolve legacy full identifiers to verified native node IDs | I3-006/I3-007; authorized read-only trace if necessary | per-actuator derivation/capture and collision-free bus mapping | NOT-READY — tuple/topology unresolved |
| I3-009 | Approve joint sign, ratio and sourced limit profiles | I3-007; mechanical coordinate review | SI units, motor/output transforms, hard/soft limits and independent review per joint | NOT-READY — tuple/mechanical evidence missing |
| I3-010 | Define encoder/feedback and calibration plan including hip yaw | I3-005/I3-009 | device-bound method, validity/age rules and explicit missing-sensor disposition | NOT-READY — sensor inventory and coordinate review missing |
| I3-011 | Select canonical Dropbear detailed/simplified description authority | upstream tree provenance inventory | source/generation boundary, duplicates classified, no build/install authority | READY-OFFLINE |
| I3-012 | Bind installed actuator models and joints to reviewed CAD | I3-007/I3-009/I3-011; WP-140 reviews | housing/output, axis/origin, scale, zero pose and provenance per joint | NOT-READY — motor mapping and CAD reviews missing |
| I3-013 | Create a physically reviewed complete configuration | I3-006..I3-012 | structural/semantic pass, independent review and reproducible views | NOT-READY — dependent evidence missing |
| I3-014 | Consider any motion enable authority | I3-013; approved bench/HIL safety evidence and independent cut | G2/G3 evidence and security authorization decision | NOT-READY — prohibited in current offline scope |

## Item-level DoR checklist

Before moving any row into Delivery, record:

- [ ] named owner and reviewer;
- [ ] requirements, ADR and work-package links;
- [ ] pinned source/input revisions and evidence class;
- [ ] dependency decisions resolved or explicitly mocked only for offline tests;
- [ ] testable acceptance criteria and test command;
- [ ] units, coordinates and uncertainty for every numerical fact;
- [ ] safety impact and rollback/invalidation behavior;
- [ ] no family inference, wildcard tuple or legacy-ID arithmetic promoted as
  physical truth;
- [ ] no hardware operation without the separately approved runbook/gate;
- [ ] incomplete or stale output is demonstrably non-enableable.

