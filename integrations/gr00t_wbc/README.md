# Dropbear GR00T Whole-Body Control overlay

This directory is the source-controlled integration overlay for adding
Dropbear to NVIDIA GR00T-WholeBodyControl. It is pinned to the upstream commit
in `UPSTREAM_LOCK.json`, vendors no upstream source or model weights, and treats
the checked Dropbear USD as the mechanical authority.

Two deliberately separate policy contracts exist in this repository:

| Contract | Input | Output | Purpose |
| --- | --- | --- | --- |
| Pinned upstream Dropbear overlay | One 784-value SONIC decoder observation, including the 64-value token and ten-frame histories | 22 normalized motor residuals | Target ABI for a native Dropbear SONIC encoder/decoder trained in the pinned upstream Isaac Lab stack |
| Local CUDA compatibility PoC | 90 current robot observations plus a separate 64-value compatibility token | 22 residual actions | Fast teaching-plant training, ONNX CUDA comparison, safety-runtime tests, and TensorRT engine-build verification |

The local `90 + 64` PoC is not a substitute for the upstream 784-input
decoder, is not compatible with released G1 weights, and must never be admitted
as a native Dropbear SONIC checkpoint.

## Delivered overlay

- Canonical 22-motor semantic, source-USD, and ROS 2 SIL ordering, plus
  explicitly unverified target orders for future Isaac Lab and MuJoCo assets.
- A versioned 784-value upstream decoder observation contract and seed Hydra
  configuration.
- SHA-256 and structural verification for the authoritative USD, articulation
  manifest, physics manifest, 93 rigid bodies, 116 articulation joints, 117
  source-physics joints, 27 retained closures, and all commanded motor
  bindings.
- A dependency-free order converter that serves as the round-trip oracle when
  the upstream `DropbearConverter` is implemented.
- Exact knee, calf, and elbow closure topology plus fail-closed reduced
  projections. Full passive poses, collision response, and constraint impulses
  remain the responsibility of the source USD in Isaac/PhysX.
- A digest-pinned, CUDA-only runner for NVIDIA's released G1 SONIC decoder,
  including the exact 994-value tensor layout populated by a declared
  kinematic shadow history, official action scaling, canonical 29-joint
  ordering, cadence checks, and fail-closed runtime behavior. Shadow history
  is not represented as measured G1 plant/IMU feedback.
- Exact dependency-light forward kinematics from the pinned G1 MJCF and from
  the retained 93-body Dropbear USD articulation cache.
- A bounded body-space retargeter that converts decoded G1 feet, lower legs,
  shoulders, forearms, and wrists into the actual 22 Dropbear motor
  coordinates while solving the retained passive knee/calf/elbow loops.
- A strict dashboard API for a decoded G1 q[29], one verified 64D token, or a
  complete 1–40-frame NVIDIA token chunk. Responses contain exact q[22]
  references, provenance, task residuals, passive angles, and explicit
  non-authority flags.
- A standalone, optional PolicyClient-compatible ZMQ helper with safe
  msgpack-numpy decoding and exact `UNITREE_G1_SONIC` output validation. It is
  not automatically connected to the dashboard; an external adapter must
  forward validated chunks into the strict HTTP retarget endpoint.
- A motion-reference converter that resamples dashboard policy rollouts to an
  exact 50 Hz timeline and emits the versioned
  `dropbear-sonic-motion-reference-v1` JSON/CSV bundle.
- Licensing records and explicit patch points for the pinned upstream checkout.

The converted 50 Hz bundle uses the pinned upstream reader's root-only
`joint_pos.csv`, `joint_vel.csv`, `body_pos.csv`, `body_quat.csv`, and
`metadata.txt` layout. Its 22-axis Isaac/MuJoCo ordering remains a declared
target until the derived MJCF and registered Isaac asset are parity-tested.
`rl.sonic_reference.SonicReferenceDataset.from_json()` also provides a tested,
strict adapter into the local compatibility trainer. That convenience does not
make the 90+64 checkpoint compatible with the upstream 784-value decoder.

## Current gates

| Gate | Current state |
| --- | --- |
| Dropbear source contract | Delivered and covered by offline tests |
| G1 token → Dropbear USD preview | Delivered: verified CUDA G1 decoder, exact G1 FK, retained-USD task-space retarget, passive-loop solve, q[22] API/browser playback |
| Order and closure adapters | Delivered for the retained browser/USD graph; force-level loop and contact authority remains Isaac/PhysX-only |
| Local CUDA PoC | Torch CUDA training, ONNX Runtime CUDA comparison, safety-runtime tests, and TensorRT 10.13 engine-build verification are available |
| Native upstream Dropbear SONIC | Blocked: upstream registration, Isaac training, and a Dropbear checkpoint are not present |
| Natural-language VLA | Transport/shape boundary is implemented, but no local Isaac-GR00T policy server, N1.7 checkpoint, camera/state stream, or prompt-labelled Dropbear dataset is installed |
| Authoritative physics | Blocked until the original USD passes a recorded Isaac/PhysX gravity, contact, collision, and closure evaluation |
| Hardware | Denied; the ROS boundary is SIL-only and no HIL admission exists |

## Verify the source contract

```bash
python3 -c \
  'from integrations.gr00t_wbc import verify_source_assets; print(verify_source_assets())'
```

## Exercise the released G1 bridge

The released decoder is a separately licensed, ignored cache. Fetch and verify
it after bootstrapping the pinned source:

```bash
tools/bootstrap_gr00t_wbc.sh
tools/setup_gr00t_runtime.sh
tools/fetch_gr00t_g1_decoder.sh
./.gr00t-venv/bin/python tools/verify_gr00t_g1_bridge.py --device 0
```

The strict bridge is exposed by the loopback dashboard at
`POST /api/gr00t/retarget`. Its three source schemas are:

- canonical decoded G1 `q[29]` in the pinned body order;
- one NVIDIA SONIC 64D token with a session-contiguous sequence; or
- one NVIDIA SONIC token chunk containing 1–40 frames.

Token input is rejected unless the pinned ONNX digest is present and ONNX
Runtime CUDA is the active provider with CPU fallback disabled. The bridge
does not accept the dashboard's deterministic prompt-router token.

The upstream VLA returns a 40-frame horizon at 2.5 Hz whose frame semantics
are 50 Hz. The HTTP bridge validates contiguous frame sequences but does not
timestamp or prove wall-clock decode cadence; the browser schedules a nominal
20 ms best-effort preview. The output is suitable for visualization and for
generating teacher data. It is not collision/contact validation and carries
no hardware authority.

## Convert the checked-in walking reference

```bash
python3 -m integrations.gr00t_wbc.motion_reference convert \
  --input web/assets/rl/dropbear-walk-reference.json \
  --output /tmp/dropbear-sonic-reference.json \
  --csv-dir /tmp/dropbear-sonic-reference-csv
```

The converter validates canonical motor order, finite root/joint/contact data,
knee-lock direction, reduced closed-linkage domains, and the exact 50 Hz
timeline. It writes the pinned reader's root-only joint/body CSV files and
`metadata.txt` alongside the separate versioned JSON bundle.

Validate an existing bundle:

```bash
python3 -m integrations.gr00t_wbc.motion_reference validate \
  --input /tmp/dropbear-sonic-reference.json
```

## Remaining upstream work

Before prompt-conditioned Dropbear deployment can be claimed:

1. Apply `PATCH_POINTS.md` to a checkout matching `UPSTREAM_LOCK.json`.
2. Produce and parity-check the Dropbear MJCF required by the motion library
   without replacing the USD as the source of truth.
3. Register the 22-axis robot and exact closed-loop asset in Isaac Lab, then
   run recorded single-environment gravity/contact/closure tests.
4. Characterize actuator gains, armatures, effort/velocity limits, encoder
   signs, latency, and thermal/current guards.
5. Retarget and validate prompt-labelled motion data at 50 Hz.
6. Train a native Dropbear SONIC encoder/decoder and export a matching
   784-input/22-output ONNX bundle.
7. Add a persistent CUDA/TensorRT inference service and connect its decoded
   radian references to the guarded 22-axis ROS 2 SIL boundary.
8. Complete separate HIL and physical safety admission before any hardware
   authority is possible.
