# Iteration 13 rigid-body and trace interoperability verification

Status: `PASS / G13.4 SOFTWARE BENCHMARK CLOSED`

## Outcome

The project now has a positive-capable canonical simulation-trace contract and
one exact, executed generic rigid-body benchmark:

- MuJoCo 3.6.0 on Linux x86-64 / CPython 3.12 / glibc 2.39;
- two engine native binaries and one NumPy ABI binary checked by size/hash;
- three recorded engine candidates, one executed and two pending;
- a tracked generic nine-DOF, three-actuator MJCF fixture;
- 2,500 fixed 1 ms steps per run;
- two byte-identical complete traces;
- 764 densely chained events;
- 9 accepted typed effort commands;
- 753 validity-preserving joint-state samples;
- 10/10 benchmark cases PASS; and
- zero production-engine selection, canonical Dropbear, exact-model fidelity,
  physical validation, support, physical I/O or motion authority.

The current Dropbear rigid-body descriptor remains non-loadable because the
canonical graph, accepted articulated CAD and admitted real plants are all
absent.

## Implemented boundaries

- strict Draft 2020-12 trace, engine-lock and benchmark-report schemas;
- exact session subject/backend/catalog/source/graph generation identity;
- canonical normalized command/state/disposition projections;
- original arbitrary event preservation with dense sequence, monotonic tick,
  predecessor SHA-256 and record SHA-256;
- whole-trace stable ID/digest and canonical atomic JSON I/O;
- deterministic cross-backend reset/input/disposition comparison;
- positive canonical-scene transition requiring exact fidelity and all
  admitted generations;
- generic-fixture fidelity-promotion denial;
- exact platform/package/native-binary/NumPy ABI lock;
- headless fixed-step articulation, contact and excited closed-chain cases;
- repeated byte-equality and tracked-output check mode;
- current unavailable Dropbear descriptor and zero-input scene admission;
- critical-artifact and claim-invariant machine-report binding; and
- requirements/test trace registration.

## Exact benchmark observations

| Observation | Result |
|---|---:|
| Simulated duration | 2.4999999999998357 s |
| Maximum drive-joint response | 0.28214073445382604 rad |
| Worst transient contact penetration | 0.006925427420111346 m |
| Settled contact penetration | 0.00001331269762449433 m |
| Final contact body height | 0.039986687302375507 m |
| Excited loop-joint response | 0.0000018027081656744087 rad |
| Maximum loop-closure residual | 0.00000027040759126295555 m |
| Trace record SHA-256 | `eb1411713d188ce218a203a8651fbc5845f1515285ae056b61b1c56d8a8e73ca` |

## Focused verification

- `tests/trace_interchange/run_tests.sh`: 6/6 PASS
- `tests/rigid_body_benchmark/run_tests.sh`: 6/6 PASS plus generated check
- `tests/offline_gate_report/run_tests.sh`: 7/7 PASS
- `python3 tools/validate_traceability.py`: 77 requirements / 129 tests PASS

An initial full-gate attempt correctly failed at the new trace stage with exit
126 because the new shell runners lacked executable file modes. After fixing
only those modes, the complete gate passed. This failure remains useful
evidence that the machine report does not turn an unexecuted stage into PASS.

## Canonical full gate

- run ID: `a0663b12426d9defa25f2197`
- result: `PASS`
- stages: 65/65
- critical artifacts: 30
- claim invariants: 82
- source manifest files: 596
- source manifest SHA-256:
  `d11c587df9c4fe7cba861f50154aee3a3bdc65e1256c073dcc4ceff86d8cf5d4`
- tracked diff SHA-256:
  `85c3e279c07e4961979fcc9077554bd7e599f1c67838d9f0e489f3cec8e2e116`
- generic benchmark cases: 10/10
- production rigid-body engine selected: false
- canonical Dropbear scene executed: false
- exact-model simulation ready: 0/44
- physical work: false
- motion enable: false

## Bound artifact hashes

| Artifact | SHA-256 |
|---|---|
| Trace schema | `87ccf7c02ddc5641d68db4468990ff5c6fced01ad346acc385b0d49eae0e7d58` |
| Trace consumer/exporter | `5682f3d0e81c00d737eb62a15ed24bea306520d761968c6408ef49024854b2ef` |
| Engine-lock schema | `28498074e4a9628d0eacff5650daea322df098bc9d3f5dec888c0aeb380d542f` |
| Engine lock | `ee92fa2ede6903b3c75dac6f33d9760e6d7628710532a8a41f3af608a8f21ce6` |
| Benchmark schema | `4894743c37b03cb10f05172251e29d9d0d7a17306db9e0525510d365630658bc` |
| Benchmark runner | `94c99e982abf519040239a60b5331e2cd78f0730c651513f465b4da199109f67` |
| Generic MJCF fixture | `088e0c20b22ab3223b055942f5cd6528fccf0b1c3fc8f7c7330e9e8cdbea36fd` |
| Generated benchmark report | `634b4f42c269970b8ca52c7e3b59a84d68c3a50bff25e17e040e22d273db99c7` |
| Generated trace | `5c1579f88d77521cd2d3fc300e9d24f8acd0465766fae6ba762b3602f1f5f450` |
| Canonical gate report | `985c3bf71992d9e73afbbf9a2eb4ddda9ee31e5827f10a76822c30232535f797` |

## Next evidence transition

G13.4 closes the generic machinery benchmark, not the Dropbear simulator.
The controlled transitions are:

1. run equivalent locked fixtures for the remaining engine candidates;
2. assign and record a production-engine decision owner;
3. accept a canonical graph and exact articulated CAD/plant inputs;
4. generate the canonical engine-neutral scene and parity vectors;
5. compile the ROS 2 C++ handoff against a pinned ABI; and
6. run controller/estimator replay, SIL and later physical-correlation gates.
