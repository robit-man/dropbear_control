# Limit provenance and effective-bound contract

The limit registry keeps ratings, configured limits, measured robot limits and
live derates separate until one exact query explicitly intersects them. The
schema is
[`schemas/myactuator-limit-registry.schema.json`](../schemas/myactuator-limit-registry.schema.json),
the current empty physical registry is
[`assets/myactuator/limit_registry.json`](../assets/myactuator/limit_registry.json),
and selection is implemented in
[`host/myactuator_lib/limits.py`](../host/myactuator_lib/limits.py).

The current Dropbear registry contains zero records, zero accepted measured
limits and motion false. Vendor catalog acquisition and the legacy sketch's
`0..360`/`3 A` values do not populate it.

## Four non-substitutable classes

Every selection declares which provenance classes are required:

1. `vendor_rating` is tied to a hashed, human-reviewed exact manual source;
2. `software_command_limit` is tied to a hashed, human-reviewed configuration;
3. `measured_safe_robot_limit` is tied to reviewed physical measurement;
4. `runtime_derate` is tied to a hashed reviewed policy and a controller-owned
   generation/sample/valid-until snapshot.

A record from one class cannot fill another. Selection reports a missing
class and direction separately instead of silently using the records that
happen to exist.

## Exact applicability

Each record binds robot/hardware revision, canonical joint/actuator, installed
actuator serial, nine-field drive tuple, bus/node and canonical configuration
identity. It also declares quantity, coordinate, direction, SI unit, control
mode set, validity interval and operating envelope.

The quantity/unit pairs are closed: position/rad, velocity/rad/s, q-axis
current/A, effort/N·m, temperature/°C and voltage/V. Coordinate choices are
also constrained; q-axis current cannot become a joint quantity and effort is
not derived from current. An operating envelope can restrict supply voltage,
temperature and absolute joint speed. If a selected record requires an
operating value and the query lacks it, selection denies rather than assuming
nominal conditions.

## Intersection semantics

Record IDs are selected explicitly; the library does not search for “latest”
or fall back by model family. For applicable accepted records:

- the effective lower bound is the maximum of lower bounds;
- the effective upper bound is the minimum of upper bounds;
- the effective magnitude is the minimum of magnitude bounds;
- a magnitude additionally intersects the interval with
  `[-magnitude, +magnitude]`.

An empty interval is `CONTRADICTORY_BOUNDS`. Unknown, stale, future,
superseded-by-state, wrong-subject, wrong-mode, wrong-envelope or wrong-runtime
generation records deny. Inclusive validity and runtime snapshot endpoints are
tested.

## Integrity and evidence boundary

Records and the registry carry canonical SHA-256 digests. The semantic
validator additionally rejects nonfinite values, unknown/wildcard tuple
fields, unit/coordinate mismatches, negative magnitudes, reversed envelopes
or validity, invalid runtime intervals, wrong evidence authority/reviewer
class, duplicate IDs, configuration drift and false physical counts.

An effective limit is still only a bounded offline decision. It cannot enable
motion and does not prove motor identity, calibration, safe power, estimator
validity or HIL behavior.

## Validation

```bash
python3 tools/validate_limit_registry.py
tests/limit_registry/run_tests.sh
```

The suite uses synthetic exact subjects to prove four-class intersection,
direction coverage, operating-envelope and runtime-generation behavior,
contradiction denial and integrity/semantic failures. Synthetic test records
are not written to the physical registry.
