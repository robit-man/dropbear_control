# Rigid-body benchmark and canonical trace interchange

Status: `GENERIC FIXTURE PASS / PRODUCTION ENGINE UNSELECTED / DROPBEAR DENIED`

This slice proves that one exact local rigid-body stack can execute the common
offline mechanics and trace machinery. It does not execute a MYACTUATOR
product model or the Dropbear robot.

The machine outputs are:

- [`generated/myactuator/rigid_body_benchmark/report.json`](../generated/myactuator/rigid_body_benchmark/report.json);
- [`generated/myactuator/rigid_body_benchmark/trace.json`](../generated/myactuator/rigid_body_benchmark/trace.json);
- [`tools/rigid-body-engine-lock.json`](../tools/rigid-body-engine-lock.json);
- [`schemas/rigid-body-benchmark-report.schema.json`](../schemas/rigid-body-benchmark-report.schema.json); and
- [`schemas/simulation-trace-interchange.schema.json`](../schemas/simulation-trace-interchange.schema.json).

## Exact executed environment

The executed candidate is MuJoCo 3.6.0 on Linux x86-64, CPython 3.12 and
glibc 2.39. The lock verifies the installed package version, two native
MuJoCo binaries, NumPy 1.26.4 and its native ABI binary by exact size and
SHA-256 before loading the fixture.

The lock also records Gazebo Jetty / gz-sim 10.4.0 and Drake 1.55.0 as
uninstalled candidates. They have not run an equivalent fixture, so this work
does not select a production Dropbear engine. The candidate references are the
[MuJoCo 3.6.0 release](https://github.com/google-deepmind/mujoco/releases/tag/3.6.0),
[Gazebo Jetty Ubuntu installation](https://gazebosim.org/docs/jetty/install_ubuntu/)
and [Drake pip installation](https://drake.mit.edu/pip.html).

This lock is an exact record of the executed environment, not yet a portable
container lock. A production selection still needs equivalent isolated runs,
toolchain/SBOM capture, an owned decision and the actual canonical scene.

## Generic fixture contract

The tracked MJCF fixture contains three independent test mechanisms:

1. an actuated hinge for deterministic fixed-step joint response;
2. a free box which falls, contacts and settles on a plane; and
3. two hinged branches joined by a MuJoCo `connect` equality constraint.

The loop is actively excited by bounded effort; merely loading an idle
constraint is not sufficient. The current exact result is:

| Case | Contract | Observed |
|---|---:|---:|
| Fixed step | 2,500 × 1 ms | 2.4999999999998357 s |
| Drive response | at least 0.1 rad | 0.28214073445382604 rad |
| Worst transient contact penetration | at most 0.01 m | 0.006925427420111346 m |
| Settled contact penetration | at most 0.0001 m | 0.00001331269762449433 m |
| Final box center height | 0.039–0.041 m | 0.039986687302375507 m |
| Loop response | at least 0.000001 rad | 0.0000018027081656744087 rad |
| Loop closure residual | at most 0.00001 m | 0.00000027040759126295555 m |
| Repeatability | two byte-equal traces | PASS |

All 10 benchmark cases pass. The report additionally proves headless core
execution, exact engine/dependency lock, explicit rad/rad/s/Nm state,
validity-preserving samples, a network-free command, current non-loadable
Dropbear descriptor behavior, and zero canonical scene inputs.

Run and verify the tracked output with:

```bash
python3 tools/run_rigid_body_benchmark.py --check
tests/rigid_body_benchmark/run_tests.sh
```

Generate new tracked output only after deliberately changing the fixture,
lock, contract or implementation:

```bash
python3 tools/run_rigid_body_benchmark.py
```

## Trace contract

`simulation-trace-interchange/1` is independent of MuJoCo. It contains:

- an exact subject and backend identity;
- catalog/source/graph generations when applicable;
- integer virtual tick and reset identity;
- normalized typed commands and dispositions;
- normalized validity-preserving joint states;
- original event payloads with dense sequence, monotonic tick, predecessor
  SHA-256 and record SHA-256;
- a whole-record stable ID and digest; and
- explicit fidelity, canonical-scene, support and physical-authority claims.

Session export derives commands, states and dispositions from the event stream.
The loader independently recomputes them, the complete event chain, summary,
trace ID and record digest. Canonical JSON is byte stable and writes are
staged before replacement. Cross-backend comparison considers reset, clock,
input and disposition projections, not expected engine-dependent state values.

The schema is positive-capable: a future accepted exact-model or canonical
Dropbear trace can be represented. A canonical Dropbear subject must match an
exact-fidelity backend and non-null catalog, source-registry and graph-registry
generations. A generic fixture must keep canonical, exact and physically
validated claims false. No trace can itself grant motor support, physical
motion authority or physical I/O.

## Why Dropbear remains denied

The benchmark consumes no Dropbear source, graph, CAD or motor plant. At the
time of this result there are:

- 0 active canonical graph submissions;
- 0 accepted articulated CAD configurations;
- 0 admitted real motor plants;
- 0 production engine-selection decisions; and
- no compiled ROS 2 C++ handoff.

The existing `dropbear-rigid-body-unavailable-v1` catalog descriptor therefore
remains non-loadable with `backend_not_loadable`. A canonical run may begin
only after those inputs are accepted through their own evidence lifecycles.
