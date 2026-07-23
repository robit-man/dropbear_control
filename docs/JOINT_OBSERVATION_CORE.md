# Joint observation, calibration and reconciliation core

[`joint_observation_core`](../firmware/esp32/src/runtime/joint_observation_core.h)
is an allocation-free C++11 state core. It performs no I/O, is not wired to
the preserved ESP32 `main.cpp`, and cannot authorize motion.

## Conversion boundary

A raw sample carries exact joint, actuator, sensor and configuration identity;
source kind and raw unit; nonzero sequence; monotonic sample and receive times;
raw value; source fault; and quality. It can be converted only with a validated
immutable calibration snapshot containing exact identities and nonzero subject/
record digests, generation, validity, evidence class and explicit coordinate
semantics.

The core keeps these conversions distinct:

- external absolute/incremental and synthetic samples use the explicit raw
  zero, scale, sign and optional reviewed wrap interval;
- native motor position uses explicit motor-to-output ratio and sign;
- native output position uses explicit output zero and sign.

It never interprets current as effort and never borrows another sensor. Raw
unit, source kind, config and sensor identity must match exactly. Synthetic and
physical calibration evidence cannot substitute for each other.

Calibration must be valid both when evaluated and at the sample time. Sample
and receive time are independent, with separate maximum ages. Future samples,
receive-before-sample, stale values, source faults, bad quality, nonfinite
arithmetic and overflow-producing conversion deny.

## Stream ordering

`ObservationStreamGuard` owns the last accepted calibration generation,
sequence, sample time and receive time for one exact stream. It rejects:

- duplicate or reordered sequence;
- sample-time regression;
- receive-time regression;
- calibration-generation rollback;
- identity/config changes on an established stream.

A denial does not advance the window and returns a zeroed output. Reset is an
explicit caller action; it grants no continuity or calibration authority.

## Reconciliation policy

The closed modes are external-only, native-only, require-both/prefer-external
and require-both/prefer-native. There is no implicit fallback or averaging.
Require-both modes retain both positions and their absolute disagreement, then
emit exactly the selected source if disagreement is within the explicit
threshold. Missing required input, sensor alias, identity/evidence mismatch or
excessive disagreement denies.

This is how missing hip-yaw external feedback remains visible: an
external-required policy has no valid sample and denies. A native-only policy
could be used only if a reviewed generated policy and exact native calibration
eventually exist; the current Dropbear configuration provides neither.

## Limit check

The position check consumes a generated exact joint/actuator/config snapshot
with nonzero provenance digest/generation and bounded validity. At least one
finite lower/upper bound is required, contradictions deny, endpoints are
inclusive, and an expired or wrong-identity snapshot cannot evaluate state.
The host four-class selector remains responsible for producing the restrictive
effective snapshot from evidence; this embedded core does not search a
registry or invent a limit.

## Verification

```bash
tests/joint_observation_core/run_tests.sh
```

The suite covers affine/wrap and native ratio conversions, identity/unit/
evidence/fault/quality denials, all time boundaries, stream replay/regression,
explicit source preference without averaging, missing required input,
disagreement, aliasing and inclusive position limits. It runs normally and
under ASan/UBSan, scans the core object for allocation symbols, and compiles as
part of the ESP32 project.

The Python reference and native test also consume the same byte-stable
[`golden_runtime.jsonl`](../tests/joint_observation_core/golden_runtime.jsonl)
corpus. Its 39 canonical cases cover conversion, ordering, reconciliation and
limit dispositions. The Python lane replays the corpus twice and verifies that
denied samples do not advance stream state; the C++ lane dispatches every
fixture to the corresponding allocation-free service path. Numeric enum values
are asserted explicitly across both implementations. These are synthetic
parity fixtures, not physical calibration, sensor-correlation or motor
evidence.
