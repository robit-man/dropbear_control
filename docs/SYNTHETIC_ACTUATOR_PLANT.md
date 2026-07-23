# Deterministic synthetic actuator plant

Status: `SYNTHETIC-TEST-BACKEND`; physical fidelity false, support false, exact
MYACTUATOR applicability false.

## Boundary

`host/myactuator_lib/actuator_plant.py` is a fixed-step electromechanical test
backend for exercising controllers, protocol bridges and state plumbing. Its
fixture has the exact series value `SYNTHETIC` and a distinct backend kind
`synthetic_test_plant`. The loader rejects unknown fields, a non-seven-field
tuple, a physical backend kind, `support_granted: true`, invalid domains or a
missing identity. It is not loaded through the real plant registry and cannot
substitute for any of its 44 model rows.

## State and solver

The solver is `semi-implicit-euler-fixed-step-v1`. State is explicit:

- q-axis current;
- rotor position and velocity;
- output position and velocity;
- winding and case temperature;
- monotonic step/time; and
- a fixed-length sensor latency queue.

Each step applies, in order:

1. winding-temperature current derating/shutdown;
2. bounded current target and proportional voltage control;
3. R-L/back-EMF current dynamics and current/voltage saturation;
4. bounded motor torque;
5. elastic/damped gear coupling outside a backlash deadband;
6. reflected rotor load, output load, static/Coulomb/viscous friction;
7. output speed and hard position limits;
8. two-node winding/case thermal dynamics; and
9. half-away-from-zero sensor quantization and exact step latency.

Diagnostics retain applied voltage, motor/transmission torque, stored
electrical/kinetic/elastic energy, derate, every saturation/limit flag and a
finite-state assertion. Reset is deterministic. There is no stochastic noise,
wall clock, adaptive step or host scheduling input.

## Protocol coupling

`SyntheticIqPlantBridge` accepts only a codec-validated V4.4 IQ request for its
exact synthetic node, plus STOP/SHUTDOWN and read-only requests. Speed and
position commands reject. IQ wire units remain 0.01 A/LSB; no torque command is
inferred. A delayed/quantized plant sample can be converted to a synthetic
`NodeState` and supplied to the existing protocol-state emulator, whose
response encoding/timing remains independent.

This composition demonstrates:

```text
typed V4.4 IQ request -> synthetic plant -> quantized delayed sample
  -> protocol emulator response
```

It does not demonstrate that a real drive implements V4.4, that the fixture
matches a motor, or that a mechanical actuator moved.

## Current offline evidence

The suite covers rest equilibrium, the declared first electrical step,
backlash/friction behavior, current/voltage/torque/speed/position saturation,
thermal rise/derate/shutdown/cooldown, sensor quantization/latency, reset/input
denials, exact node/mode protocol coupling and emulator feedback. A 2,000-step
trace is pinned to SHA-256
`2cfca5c638918c938802e91bc189f40e42413b1c230cb5b3d6adb0868e296a3b`.

All real evidence counts remain unchanged:

- 44/44 catalog rows explicitly unsupported;
- zero sourced plant parameter sets;
- zero runtime-loadable real parameter sets; and
- zero physically correlated parameter sets.

## Required path to a real actuator plant

A real backend requires a complete parameter set satisfying the strict plant
registry schema, exact seven-field applicability, bounded uncertainty,
operating envelopes and source provenance. It must then pass TST-SIM-004
analytic/correlation work with bench data, identified holdout trajectories,
residual/error limits and revision-controlled acceptance. A synthetic test or
CAD dimension may never fill an absent electrical, friction, thermal, sensor or
latency value.
