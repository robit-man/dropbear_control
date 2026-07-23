# Calibration evidence and admission contract

The calibration registry is an evidence boundary, not a calibration wizard and
not a motion-enable file. Its schema is
[`schemas/myactuator-calibration-registry.schema.json`](../schemas/myactuator-calibration-registry.schema.json),
the current physical registry is
[`assets/myactuator/calibration_registry.json`](../assets/myactuator/calibration_registry.json),
and host validation/admission lives in
[`host/myactuator_lib/calibration.py`](../host/myactuator_lib/calibration.py).

The current registry intentionally contains zero records. It is bound to the
current incomplete Dropbear configuration digest, reports zero accepted
physical calibrations and cannot authorize motion.

## Exact subject

A record applies to one exact combination of:

- robot ID and hardware revision;
- canonical joint and actuator ID;
- installed actuator serial;
- manufacturer, series, model, hardware revision, drive firmware, protocol
  name/revision, transport and control mode;
- bus and native node;
- sensor ID, kind and serial;
- canonical configuration ID, revision and SHA-256 digest.

Admission requires an explicit `record_id` and exact equality of all fields.
There is no “latest,” joint-name, family, neighboring sensor, unknown-field or
synthetic-to-physical fallback.

## Coordinate meaning

The record keeps raw, native output, motor and canonical joint coordinates
separate. It requires raw unit/zero, joint and native-output zero, explicit
raw-to-joint scale, motor-to-joint sign, positive-direction definition,
output-per-motor ratio and wrap convention. A wrap period must agree
numerically with its scale.

These values are evidence inputs for the observation core. Merely entering
them in a draft does not make them valid. In particular, the offsets and
direction multipliers in the legacy Dropbear sketch lack an exact installed
subject, procedure and review, so they remain observations outside this
registry.

## Procedure and measurements

Every record includes:

- versioned method and fixture/reference;
- identified operator and UTC measurement time;
- temperature, supply voltage and robot support state;
- unique tools with serial/version/calibration-due time;
- hashed procedure, measurement, fixture, configuration or manual artifacts;
- at least three dense ordered raw/reference/residual samples;
- uncertainty, repeatability, maximum residual and explicit acceptance
  thresholds.

The validator recomputes the maximum residual and acceptance result. Nonfinite
numbers, expired tools, reversed time, unordered samples or threshold/result
disagreement fail closed.

## Review, lifecycle and invalidation

An accepted record requires an identified human reviewer distinct from the
operator, an accept disposition, rationale and review time after measurement.
Validity cannot begin before review. Accepted records must list every required
invalidation cause:

- actuator, sensor or controller replacement;
- native node reassignment;
- mechanical disassembly;
- drive firmware change;
- canonical configuration or coordinate-frame change;
- procedure or fixture change;
- validity expiry.

Records have stable IDs, family IDs and increasing revisions. Supersession is
linear, subject-exact and append-ordered; the superseded record stops admitting
immediately. Draft, rejected and revoked records never admit. Each record and
the registry have independent canonical SHA-256 integrity fields.

## Evidence classes

`synthetic_fixture` records may be fully accepted to exercise conversion and
replay logic, but physical admission rejects them with
`NONPHYSICAL_EVIDENCE`. Only an accepted, current, non-superseded
`physical_bench` record for the exact query can return `ADMITTED`. Even that
result proves calibration applicability only; global motion remains false and
still depends on installed routes, limits, protocol applicability, physical
safety and HIL evidence.

## Validation

```bash
python3 tools/validate_calibration_registry.py
tests/calibration_registry/run_tests.sh
```

The suite checks the empty baseline, exact subject fields, inclusive validity
boundaries, explicit record selection, draft/reject/synthetic denial,
supersession, digests, finite values, measurement math, procedure/reviewer
time and identity, wrap consistency, all invalidation conditions,
configuration drift and false physical counts.
