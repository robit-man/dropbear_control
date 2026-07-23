# Architecture option matrix

Scores are 1 (poor) through 5 (strong). Safety and correctness are mandatory;
cost/effort is scored higher when the option is easier.

## ESP32 role

| Option | Safety | Determinism | Protocol reuse | Dropbear fit | Ease | Decision |
|---|---:|---:|---:|---:|---:|---|
| Direct host-to-CAN; ESP32 removed | 2 | 4 | 4 | 2 | 3 | Rejected for the present wiring/sensor topology and local fail-safe needs |
| ESP32 as transparent byte bridge | 2 | 4 | 4 | 3 | 4 | Useful diagnostic mode, insufficient as the only safety boundary |
| ESP32 deterministic joint gateway | 5 | 5 | 4 | 5 | 3 | **Recommended** |
| ESP32 owns whole-body/gait control | 2 | 3 | 2 | 2 | 1 | Rejected; mixes timing, planning, UI, and safety responsibilities |

The recommended gateway owns bus scheduling, calibrated local sensing,
single-writer arbitration, limits, faults, and command expiry. It exposes a
stable joint interface without absorbing robot planning.

## Source of robot truth

| Option | Cross-layer consistency | Tool compatibility | Reviewability | Ease | Decision |
|---|---:|---:|---:|---:|---|
| Hard-code each firmware/UI/host/URDF independently | 1 | 2 | 1 | 3 | Reject; this is the current failure mode |
| URDF alone | 3 | 5 | 4 | 4 | Insufficient for firmware/protocol/calibration and evidence data |
| Versioned robot/joint registry generating validated artifacts | 5 | 5 | 5 | 3 | **Recommended** |

URDF/xacro remains the robot-description output used by robotics tooling, while
the registry also carries bus identity, firmware/protocol, calibration,
provenance and capability metadata that URDF should not own.

## Simulation strategy

| Option | Protocol fidelity | Robot dynamics | CI/HIL reuse | Asset fidelity | Ease | Decision |
|---|---:|---:|---:|---:|---:|---|
| Browser-only Three.js toy simulator | 1 | 1 | 2 | 3 | 5 | Keep only for catalog/diagnostics |
| One rigid-body engine with mocked joint API | 2 | 5 | 3 | 5 | 3 | Incomplete without protocol/plant layers |
| Protocol emulator + actuator plant + engine-neutral robot model | 5 | 5 | 5 | 5 | 2 | **Recommended staged target** |

Do not lock the canonical model to one physics engine yet. Benchmark candidate
backends after the URDF/joint contract and common controller test are ready.
The selection gate should measure contact stability, deterministic replay,
headless CI, robotics middleware integration, sensor support, and team workflow.

## CAD storage

| Option | Reproducibility | Repository size | Legal control | Ease | Decision |
|---|---:|---:|---:|---:|---|
| Commit expanded STEP directly to ordinary Git | 5 | 1 | 2 | 4 | Reject |
| Track source URLs/revisions/checksums; use ignored local cache | 5 | 5 | 5 | 4 | **Current intake choice** |
| Approved artifact registry/Git LFS after rights review | 5 | 4 | 4 | 3 | Recommended production choice after policy decision |

## Migration approach

| Option | Risk containment | Learning speed | Regression value | Decision |
|---|---:|---:|---:|---|
| Incrementally patch the monolithic Dropbear sketch | 1 | 3 | 2 | Reject for production; preserve only as prototype |
| Big-bang rewrite of all motors and robot layers | 1 | 2 | 2 | Reject |
| Evidence-gated vertical slice, then expand model/bus/layer coverage | 5 | 5 | 5 | **Recommended** |
