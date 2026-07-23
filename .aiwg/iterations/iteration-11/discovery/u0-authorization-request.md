# U0 visual-only installed-inventory authorization request

Status: `DRAFT-NOT-AUTHORIZED`

This record is a bounded request template, not permission. It cannot be made
effective by repository status, a test result, an informal message or one
person acting in multiple independent roles. All fields in the authorization
block and every required approval must be complete before the first physical
step.

## Requested outcome

Collect externally visible identity evidence for one named, de-energized
Dropbear asset so later reviewers can determine the installed actuator,
controller, transceiver and connector facts. This phase grants no support,
protocol applicability, CAN-controller selection, runtime route, calibration,
limit, CAD acceptance, powered test or motion authority.

## Authorization block

| Field | Required value | Current value |
|---|---|---|
| authorization ID and revision | unique controlled identifier | `UNASSIGNED` |
| superseded authorization | exact ID or `none` | `UNASSIGNED` |
| robot asset ID and revision | physical tag plus configuration revision | `UNVERIFIED` |
| robot owner | named accountable human | `UNASSIGNED` |
| physical location | exact room/bench/bay | `UNASSIGNED` |
| valid UTC start and expiry | bounded window | `UNASSIGNED` |
| named operator | one trained human | `UNASSIGNED` |
| hardware owner/authorizer | named human, separate accountability | `UNASSIGNED` |
| safety reviewer | named independent human | `UNASSIGNED` |
| inventory reviewer | named human independent of capture | `UNASSIGNED` |
| evidence custodian | named human/service and approved root | `UNASSIGNED` |
| isolation method | every energy source and lockout method | `UNREVIEWED` |
| zero-energy verifier | named qualified human and rated instrument | `UNASSIGNED` |
| mechanical-restraint state | gravity/stored-energy/pinch controls | `UNREVIEWED` |
| restoration owner/state | named human and exact final state | `UNASSIGNED` |
| exception process | stop-and-reauthorize only | `REQUIRED` |

Any `UNASSIGNED`, `UNVERIFIED` or `UNREVIEWED` value keeps this request
inactive.

## Exact requested actions

If authorized without modification, the only allowed actions are:

1. verify the asset tag, location and external configuration against the
   signed authorization;
2. witness and record the safety reviewer's isolation and zero-energy result;
3. photograph the whole-robot context without changing its state;
4. photograph externally visible controller, PCB, transceiver, connector and
   cable labels;
5. photograph externally visible labels for the twelve named actuator slots;
6. transcribe only values that are legible in the captured evidence;
7. record inaccessible, ambiguous, duplicate or conflicting observations as
   explicit unknown/conflict values; and
8. hash, review and seal the observation record, then verify restoration to
   the authorization's named final state.

No cover, enclosure, connector, fastener or cable may be opened, loosened,
mated, removed or repositioned. A label requiring any such action is recorded
as inaccessible and the campaign stops for that item.

## Explicit exclusions

This request does not permit:

- connecting USB, serial, debug, Ethernet, CAN, battery, supply, analyzer or
  any other cable;
- energizing a rail or using a tool that can inject voltage/current;
- continuity, resistance or termination measurement;
- turning, back-driving, loading, unloading or releasing any joint or brake;
- reading a drive/controller register or starting controller firmware;
- transmitting or receiving CAN traffic, even in nominal listen-only mode;
- changing node IDs, configuration, firmware, calibration or mechanical zero;
- removing guards/covers or entering an unreviewed pinch/crush zone;
- bench, HIL, thermal, plant-identification or locomotion work; or
- delegating an authorization/independent-review role to automation.

Discovery of a need for an excluded action is an abort and a new authorization
request, never an implied scope expansion.

## Preconditions and hold points

| Hold | Required independent evidence | Release authority | Abort condition |
|---|---|---|---|
| H0 request review | completed authorization block and exact asset boundary | hardware owner + safety reviewer | incomplete, expired or conflicting record |
| H1 energy isolation | all electrical, gravity, pneumatic, hydraulic, elastic and thermal sources identified and controlled | safety reviewer | any uncertain/nonzero source or unstable restraint |
| H2 scene integrity | no cable connected; no unapproved tool or cover access needed | operator + hardware owner | unexpected connection/state/configuration |
| H3 per-item capture | exact actuator/controller slot and photo context are unambiguous | operator | side/slot/model cannot be established visually |
| H4 record seal | evidence hashes, UTC times, tools and conflicts reconcile | independent inventory reviewer | missing evidence, silent inference or hash mismatch |
| H5 restoration | asset matches the named safe final state | hardware owner + safety reviewer | damage, change, missing item or uncertain state |

Any person may call stop. Restart requires the same reviewers to document the
resolved condition; an expired window requires a new authorization revision.

## Evidence and custody contract

Before authorization, the custodian must assign an approved, access-controlled
capture root and retention policy. The sealed package must contain:

- the signed authorization and revisions;
- asset/context and per-slot image originals;
- isolation/zero-energy checklist and instrument identity;
- operator UTC log and abort/exception log;
- a new installed-inventory JSON copied from the tracked template;
- SHA-256 and byte length for every evidence object;
- reviewer disposition without inferred values; and
- restoration confirmation.

Evidence must not be written into generated status directories. A submission
is observation-only until schema validation, hash verification and independent
review succeed; even then it grants no later phase.

## Approval table

| Approval | Name/identity | UTC | Controlled signature/reference | Status |
|---|---|---|---|---|
| robot owner consent | `UNASSIGNED` | — | — | `MISSING` |
| hardware-owner authorization | `UNASSIGNED` | — | — | `MISSING` |
| independent safety review | `UNASSIGNED` | — | — | `MISSING` |
| operator acceptance | `UNASSIGNED` | — | — | `MISSING` |
| inventory reviewer acceptance | `UNASSIGNED` | — | — | `MISSING` |
| evidence custodian acceptance | `UNASSIGNED` | — | — | `MISSING` |

Effective authorization is false until all six rows are complete, consistent
and within the valid UTC window. L1 listen-only, safe-power, calibration and
HIL phases always require separate future records.
