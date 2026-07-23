# Reviewed sourced-plant runtime adapter V1

Status: implemented offline, positive-capable, real baseline empty.

The V1 runtime adapter is the only path from a generated exact-model source
parameter set to executable deterministic plant parameters. It separates
three kinds of information that must not be silently mixed:

1. reviewed motor facts from official sources;
2. independently reviewed execution/scenario choices; and
3. the fixed equations and solver implemented by this repository.

A complete source set is therefore necessary but not sufficient. The adapter
must account for all 34 source parameters and four source envelopes, and it
must reject any source semantics the current equation core cannot represent
exactly.

## Controlled chain

```text
active reviewed V2 source facts + accepted exact protocol tuple
  -> generated source-only parameter set
  -> independently prepared and reviewed execution profile
  -> deterministic V1 adapter
  -> hash-bound runtime contract
  -> aggregate plant registry V4 backend
  -> SourcedPlantEngine session
```

Every edge binds the exact upstream generation and SHA-256. Removing or
changing a source fact, applicability decision, parameter set, profile,
adapter implementation or plant implementation invalidates downstream
admission. There is no family, nearest-model, implicit-latest or default
profile fallback.

## Source facts versus modeling choices

The source set remains immutable. The execution profile supplies only choices
that are needed to run a bounded scenario but are not vendor motor facts:

| Profile field | Required interpretation |
|---|---|
| `torque_regime` | `continuous_only`; peak torque and duration are excluded |
| `supply_voltage_v` | one point inside the reviewed source envelope |
| `ambient_temperature_k` | one point inside the reviewed source envelope |
| `rotation_direction` | positive, negative, or exactly representable bidirectional |
| `position_lower_rad`, `position_upper_rad` | scenario bounds containing reset position zero |
| `output_load_torque_bound_nm` | positive and no greater than the continuous source/envelope intersection |
| `transmission_damping_nm_s_per_rad` | explicit positive model choice |
| `current_controller_kp_v_per_a` | explicit positive controller choice |
| `derate_start_temperature_k` | strictly between ambient and the conservative shutdown limit |

The profile must be prepared by one human `simulation_engineer`, accepted by
a distinct human `controls_safety_reviewer`, and carry a nonempty rationale.
It cannot grant support, physical validation, physical I/O or motion
authority.

## Exact V1 representability boundary

The current deterministic core can execute a source set only when all of the
following hold:

- position, velocity and current noise standard deviations are exactly zero;
- command delay and delay jitter are exactly zero;
- current-loop and state-sample periods are equal;
- feedback delay is an exact nonnegative integer number of solver steps;
- execution is continuous-torque-only;
- bidirectional execution has equal forward and reverse efficiencies;
- one selected direction may instead use its corresponding directional
  efficiency;
- supply, ambient, speed, torque and direction stay within the reviewed
  source envelopes; and
- motor speed, case temperature and all ordinary plant constraints remain
  explicit runtime guards.

These restrictions are deliberate. A set with real noise, jitter,
multi-rate sampling, command latency or asymmetric bidirectional efficiency
is rejected; those facts are never rounded away or replaced with a convenient
default. Supporting them requires a new equation/solver adapter version with
its own analytical and regression evidence.

## Controlled inputs and outputs

Human-reviewed inputs belong in:

- `assets/myactuator/plant_runtime_profiles/<profile-id>.json`

Their schema is:

- `schemas/myactuator-plant-runtime-profile.schema.json`

Generated outputs are:

- `generated/myactuator/plant/runtime_adapters/registry.json`
- `generated/myactuator/plant/runtime_adapters/contracts/<contract-id>.json`

The generated registry covers all 44 models and includes:

- exact source, schema, generator, adapter and plant-implementation hashes;
- one 38-row source-semantic disposition table;
- profile and contract hashes;
- per-model source-set/profile/contract/loadable counts and blockers; and
- explicit false support, physical validation, physical I/O and motion
  authority.

## Runtime contract

An admitted contract carries:

- exact applicability and plant identity;
- parameter-set, assembly-generation, profile, adapter and implementation
  identities;
- reviewed preparer/reviewer identities and review time;
- all 38 source-semantic dispositions;
- typed deterministic `PlantParameters`;
- selected direction and continuous torque regime;
- maximum motor-speed and case-temperature runtime guards;
- source/scenario/solver provenance; and
- a whole-record digest.

`SourcedPlantEngine` loads only this typed contract, requires its exact
backend/model identity, enforces direction/current/speed/temperature guards,
and includes the contract/profile/source/solver identities in snapshots and
trace provenance. It remains an offline exact-source plant evidence class,
not physical evidence.

## Reproduction and verification

```bash
python3 tools/generate_plant_parameter_sets.py --write
python3 tools/generate_plant_runtime_adapters.py --write
python3 tools/generate_plant_registry.py --write
python3 tools/generate_simulator_runtime_catalog.py --write

tests/plant_runtime_adapter/run_tests.sh
tests/plant_registry/run_tests.sh
tests/plant_core/run_tests.sh
tests/simulation_session/run_tests.sh
tests/simulator_runtime/run_tests.sh
```

Generation is transactional: malformed, duplicated, stale, unsupported or
authority-promoting input fails before the previous valid output is replaced.
The focused adapter suite includes synthetic positive execution, digest and
semantic tampering, unsupported noise/timing/direction, scenario/envelope and
review denial, revocation and output-transaction tests.

## Current baseline and next frontier

- reviewed execution profiles: 0;
- generated runtime contracts: 0;
- runtime-loadable exact source sets: 0;
- runtime-loadable exact models: 0/44;
- physically validated contracts: 0; and
- support, physical I/O and motion authority: false.

The V2 dynamics and adapter path is now implemented separately; see
[`PLANT_RUNTIME_ADAPTER_V2.md`](PLANT_RUNTIME_ADAPTER_V2.md). It represents
real source noise, command delay/jitter, multi-rate sampling, arbitrary
feedback delay, peak-duration semantics, separate thermal limits and
asymmetric bidirectional efficiency. V1 remains frozen and independently
admitted—no source set is silently upgraded between adapters.

The next external input is independent human review of real source facts and
execution profiles. Physical correlation remains behind separate
authorization and bench/HIL gates.
