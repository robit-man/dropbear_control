# Reviewed sourced-plant runtime adapter V2

Status: implemented offline, positive-capable, real baseline empty.

The V2 runtime path executes all 38 reviewed source semantics without
weakening or silently upgrading the conservative V1 path. It is a
single-actuator, source-only SIL contract. It is not physical correlation,
motor support, HIL evidence, physical I/O, or motion authority.

## Controlled chain

```text
active reviewed V2 source facts + accepted exact protocol tuple
  -> generated source-only parameter set
  -> independently prepared and accepted V2 execution profile
  -> deterministic V2 adapter
  -> hash-bound V2 runtime contract
  -> aggregate plant registry V4
  -> exact simulator-catalog backend
  -> SourcedPlantV2Engine session
  -> canonical backend-neutral trace
```

Every edge is content- and generation-bound. The V2 contract binds the exact
catalog, parameter-set file, assembly generation, source-fact set, execution
profile, profile schema, adapter implementation, plant implementation,
configuration digest, reviewer identities, and all 38 semantic mappings.
There is no family, nearest-model, implicit-latest, cross-configuration, or
default-profile fallback.

The aggregate registry permits at most one active runtime-contract generation
for one plant. A plant admitted by both V1 and V2 fails closed instead of
selecting one by precedence.

## Execution-profile boundary

Reviewed motor facts remain immutable. A profile in
`assets/myactuator/plant_runtime_profiles_v2/` selects only unsourced
execution choices:

- continuous-only or one-shot-per-reset peak torque;
- whether sourced delay jitter applies to commands, feedback, or both;
- supply voltage and ambient temperature inside reviewed envelopes;
- bidirectional execution without averaging directional efficiencies;
- position and external-load scenario bounds;
- transmission damping and current-controller gain; and
- separate winding and case derate thresholds.

The preparer must be a human simulation engineer. A distinct human
controls/safety reviewer must accept the profile with a rationale. The schema
structurally fixes support, physical validation, physical I/O, and motion
authority to false.

## Exact V2 semantics

The engine uses
`semi-implicit-euler-event-scheduled-v2` with rational schedule timestamps.
It represents:

- distinct forward and reverse transmission efficiencies;
- continuous torque and a nonrecovering one-shot peak-duration budget;
- maximum motor and output speed;
- separate winding and case temperature limits and derating;
- exact position quantization;
- deterministic position, velocity, and current noise using
  `sha256-box-muller-counter-v1`;
- deterministic command/feedback delay jitter using
  `sha256-bounded-uniform-counter-v1`;
- a state-sample period distinct from the solver period;
- interpolation at capture time and arbitrary feedback latency;
- explicit unavailable, valid, and held-stale feedback;
- sequence-monotonic command and sample delivery;
- exclusive host deadlines that expire pending or active commands; and
- complete snapshot/restore of queues, watermarks, counters, rational clocks,
  peak budget, sensor visibility, seed, and configuration identity.

Commands become eligible at their exact delayed time and activate at the
first solver boundary at or after that time. The newest sequence wins.
Expired or superseded commands cannot later activate, even if jitter reordered
them. Sensor captures retain exact capture, eligibility, and delivery time.

`state_sample_period_s` must be at least the solver period. The interpolation
is a declared plant observation model, not evidence of unreviewed internal
drive sensor dynamics. Peak recovery is not modeled because no recovery fact
is sourced. Noise reproducibility is bound to the pinned Python
floating-point implementation.

## Runtime, registry, and trace integration

`SourcedPlantV2Engine` accepts only a typed
`ExecutablePlantV2ParameterSet`. Its session identity is
`actuator_plant` / `exact_model_plant_sil`; exact-model here means exact
source-tuple applicability, not physical validation. The wrapper maps:

- session sequence, issue tick, and exclusive deadline to the plant command;
- no delivered sample to `missing`;
- a held older delivered sample to `stale`;
- exact capture/delivery times and all adapter provenance into state
  provenance references; and
- thermal shutdown to command cancellation and a latched session fault.

The trace interchange retains the catalog generation and exact derived backend
identity. Each V2 state contains the adapter-provided contract, parameter-set,
execution-profile, source-fact-set, solver, noise, and jitter references. A
synthetic sourced-V2 fixture is pinned to trace record SHA-256
`1257214ab285ce52c8022f1d5dc98edcf5dec40c232987f594dea333f7c979b9`.
The lower-level canonical plant trace is pinned to
`1e601fed12104a5c3251a8e1f3a3b0a94470df923c319127dee7c4cfddba743d`.

## Controlled inputs and outputs

Human input:

- `assets/myactuator/plant_runtime_profiles_v2/<profile-id>.json`

Schemas:

- `schemas/myactuator-plant-runtime-profile-v2.schema.json`
- `schemas/myactuator-plant-runtime-adapter-registry-v2.schema.json`
- `schemas/myactuator-plant-registry.schema.json`
- `schemas/myactuator-simulator-runtime-catalog.schema.json`
- `schemas/simulation-trace-interchange.schema.json`

Generated outputs:

- `generated/myactuator/plant/runtime_adapters_v2/registry.json`
- `generated/myactuator/plant/runtime_adapters_v2/contracts/<contract-id>.json`
- `generated/myactuator/plant/runtime_registry.json`
- `generated/myactuator/simulator/runtime_catalog.json`

## Reproduction and verification

Regenerate in dependency order:

```bash
python3 tools/generate_plant_parameter_sets.py --write
python3 tools/generate_plant_runtime_adapters.py --write
python3 tools/generate_plant_runtime_adapters_v2.py --write
python3 tools/generate_plant_registry.py --write
python3 tools/generate_simulator_runtime_catalog.py --write
python3 tools/generate_coverage_dashboard.py --write
```

Focused verification:

```bash
tests/plant_core/run_tests.sh
tests/plant_core_v2/run_tests.sh
tests/plant_runtime_adapter/run_tests.sh
tests/plant_runtime_adapter_v2/run_tests.sh
tests/plant_registry/run_tests.sh
tests/simulator_runtime/run_tests.sh
tests/simulation_session/run_tests.sh
tests/trace_interchange/run_tests.sh
tests/coverage_dashboard/run_tests.sh
```

The current focused suites contain 15 V1-core, 15 V2-core, 10 V1-adapter,
eight V2-adapter, 11 registry, 10 simulator-catalog, 15 session, seven trace,
and dashboard adversarial tests. The repository-wide offline gate runs both
engine and adapter generations as separate stages and records the V2 registry
as a critical artifact with explicit algorithm and denial-state claims.

## Current evidence state

- catalog models: 44;
- reviewed V2 execution profiles: 0;
- generated V2 runtime contracts: 0;
- runtime-loadable V2 parameter sets: 0;
- runtime-loadable exact V2 models: 0/44;
- physically validated V2 contracts: 0;
- exact-model simulation-ready models across the tracked catalog: 0/44; and
- support, physical validation, physical I/O, and motion authority: false.

The next evidence-producing work is human review of exact source facts and V2
profiles, followed by model-specific CAD/output-member review and separately
authorized physical correlation. The next software work is Dropbear
multi-actuator plant/rigid-body composition; neither may promote the current
zero baseline.
