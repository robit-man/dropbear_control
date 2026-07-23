# Iteration 11 installed-inventory capture runbook

Status: `PREPARED-NOT-AUTHORIZED`

This runbook prepares one bounded, de-energized identification campaign. It
does not authorize access to the robot, electrical connection, controller
startup, CAN observation, transmission, actuator release or motion. The
machine-readable record is
`assets/dropbear/installed_inventory_template.json`; a copy must be assigned a
new capture identity before any approved work.

## Scope and non-scope

Permitted actions can only be selected from:

- visual label inspection;
- label photography;
- PCB silkscreen inspection;
- connector mapping without mating a cable;
- de-energized continuity measurement after the safety reviewer verifies zero
  energy and the hardware owner permits probing; and
- transcription from an identified document.

The capture excludes powering any rail, rotating or back-driving a joint,
releasing a brake, mating a controller or CAN connector, attaching a powered
analyzer, reading a device register, changing a node ID, opening firmware,
transmitting a frame, calibrating, testing limits or running HIL.

## Preconditions

The operator shall stop before touching the robot unless every item is
recorded and independently checked:

1. a hardware-owner authorization names the exact physical asset, location,
   time window and allowed actions;
2. a safety reviewer confirms all energy sources are isolated, locked out
   where applicable, discharged and measured de-energized;
3. mechanical stored energy, gravity loads, brakes and pinch/crush zones are
   controlled;
4. the operator, evidence storage location, tools and tool calibration status
   are identified;
5. no USB, CAN, DC supply, battery, Ethernet, serial or debug cable is
   connected; and
6. the template and current canonical configuration digest are revalidated.

Absence, expiry or disagreement is an abort—not an item to fill with a guess.

## Atomic capture steps

| Step | Owner | Independent check | Required input | Abort condition | Evidence output |
|---|---|---|---|---|---|
| I11-U01 verify asset boundary | hardware owner | safety reviewer | authorization, asset tag | asset/revision/location mismatch | signed authorization reference |
| I11-U02 prove zero energy | safety reviewer | operator | isolation procedure, rated meter | any nonzero/unstable energy or stored-load uncertainty | isolation checklist and meter evidence |
| I11-U03 photograph whole-robot context | operator | hardware owner | approved camera/storage | unexpected cable/cover removal required | overview evidence hash |
| I11-U04 identify controller PCB | operator | hardware owner | visible labels/silkscreen only | enclosure access not explicitly authorized | board model/revision/serial evidence |
| I11-U05 identify CAN controller/transceiver | operator | electrical reviewer | board evidence | part marking inaccessible or ambiguous | exact marking/photo or explicit unknown |
| I11-U06 map visible connectors/pins | operator | electrical reviewer | connector drawings/evidence | probing or cable mating would be needed | connector/pin observations |
| I11-U07 measure de-energized termination only if authorized | electrical operator | safety reviewer | rated meter, approved nodes | authorization omits measurement; unexpected continuity/voltage | measurement log/tool ID |
| I11-U08 inspect twelve installed motor labels | operator | mechanical reviewer | canonical actuator placement map | actuator identity/side cannot be established visually | one evidence set per exact actuator ID |
| I11-U09 record conflicts | operator | hardware owner | all observations | duplicate serial/node silently overwritten | explicit conflict records |
| I11-U10 seal record | operator | independent inventory reviewer | evidence hashes and draft JSON | missing evidence, non-UTC time or changed source digest | submitted inventory record |

Every unknown remains `null` with a partial/unobserved status. Arithmetic node
IDs, left/right symmetry, motor order and CAD labels are not installed facts.

## Conflict policy

- Duplicate non-null native node observations require
  `duplicate_native_node`.
- Duplicate non-null serial observations require `duplicate_serial`.
- A leg label, PCB label or document disagreement requires
  `conflicting_label`.
- A label that cannot be seen without expanding authorization requires
  `inaccessible_label`.
- A model/firmware/protocol relationship that cannot be proved requires
  `unknown_applicability`.

A conflict can be documented; it cannot be transformed into support,
protocol applicability, a runtime route or physical motion authority.

## Closeout

The reviewer verifies the record and evidence hashes, confirms that no
excluded action occurred and returns the asset to the state named by the
authorization. Submission only contributes observations. It does not select a
CAN controller, make listen-only capture executable, or grant any later
powered phase.
