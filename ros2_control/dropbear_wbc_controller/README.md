# Dropbear 22-axis WBC JSON SIL guard

This ROS 2 Jazzy package is a deterministic, 50 Hz, 22-axis JSON guard. It
accepts **absolute motor-coordinate positions in radians** and emits clamped
`dropbear-wbc-safe-command-v1` JSON with `authority: sil_only`.

It is not a policy decoder, a `ros2_control` controller plugin, a
`JointTrajectory` publisher, a state estimator, a physical motor driver, or a
hardware-enable authority.

## Exact local residual-to-reference path

The local `dropbear-sonic-checkpoint-v1` artifact does not output radians.
[`rl/sonic_runtime.py`](../../rl/sonic_runtime.py) returns a
`RuntimeResult.motor_residual` containing 22 normalized residuals. Sending that
vector directly to `/dropbear/wbc/reference_json` is invalid.

The intended repository-local SIL path is:

```text
90-D current observation + 64-D compatibility token
                         |
          external local Torch/ONNX runtime
                  rl/sonic_runtime.py
                         |
       normalized motor_residual[22], no ROS frame
                         |
    + time-aligned authored_reference_rad[22]
                         |
       pure adapter in rl/sonic_action.py
                         |
 absolute dropbear-wbc-reference-v1 positions[22]
                         |
          /dropbear/wbc/reference_json
                         |
       this package's 22-axis JSON SIL guard
                         |
       /dropbear/wbc/safe_command_json
                         |
               no consumer supplied
```

The pure conversion helper is
[`rl/sonic_action.py`](../../rl/sonic_action.py). It is deliberately outside
this ROS package. No node in this package runs the policy, chooses or advances
the authored gait frame, calls the helper, or publishes the resulting
reference.

The local action semantic is
`dropbear-local-reference-residual-v1`. For each canonical motor index `i`,
the exact training and deployment formula is:

```text
r_i = clamp(motor_residual_i, -1, 1)
q_requested_rad_i(t) =
    q_authored_rad_i(t) + r_i * LOCAL_POLICY_ACTION_SCALE_i * 0.62
```

`LOCAL_POLICY_ACTION_SCALE`, in the canonical order below, is:

```text
0.10, 0.10, 0.10, 0.10,
0.55, 0.62, 0.62, 0.55,
0.30, 0.35, 0.35, 0.30,
0.82, 0.32, 0.42, 0.36, 0.38,
0.82, 0.32, 0.42, 0.36, 0.38
```

The corresponding effective residual scales in radians are:

```text
0.0620, 0.0620, 0.0620, 0.0620,
0.3410, 0.3844, 0.3844, 0.3410,
0.1860, 0.2170, 0.2170, 0.1860,
0.5084, 0.1984, 0.2604, 0.2232, 0.2356,
0.5084, 0.1984, 0.2604, 0.2232, 0.2356
```

After conversion, the two knee targets are clamped to `[0, π]` radians. Zero
residual reproduces the supplied, time-varying authored reference; it does
**not** mean a fixed stand pose or the embodiment `centerRad` values. The
caller must provide the reference frame synchronized to the same gait phase
used for policy input. The built-in local reference is sampled from
`DropbearWalkEnv._reference_motor_targets()` by
[`rl/sonic_reference.py`](../../rl/sonic_reference.py).

A deployment-side publisher must first require `RuntimeResult.accepted`, then
call `reference_payload(...)` with the runtime residual and its time-matched
authored reference. The stateless helper does not inspect the runtime's
accept/reject flag. It produces:

- schema `dropbear-wbc-reference-v1`;
- a caller-provided session ID and sequence (the ROS guard requires sequences
  to be strictly increasing);
- `time.monotonic_ns()` by default for `generated_steady_time_ns`, or an
  explicit caller-provided value;
- the exact semantic `joint_names`;
- absolute radian `positions`;
- optional `source_token_sequence`; and
- the `dropbear-local-reference-residual-v1` semantic marker as an extension.

The ROS contract also accepts an optional 22-value `velocities` vector, but
`reference_payload(...)` currently emits positions only. A publisher that adds
velocities must derive them in the same steady-clock frame and preserve the
canonical order.

Do not use
[`integrations/gr00t_wbc/action_adapter.py`](../../integrations/gr00t_wbc/action_adapter.py)
for a local checkpoint. That separate adapter implements
`centerRad + clamp(action) * scaleRad` for a future native upstream 784-input
Dropbear SONIC artifact. The fixed-center and local authored-reference
contracts are intentionally incompatible and must not be silently
interchanged.

## Canonical 22-axis contract

Every state, reference, and safe-command frame uses this immutable semantic
order:

```text
left_outer_calf, left_inner_calf, right_inner_calf, right_outer_calf,
left_knee, left_hip_pitch, right_hip_pitch, right_knee,
left_hip_yaw, left_hip_roll, right_hip_roll, right_hip_yaw,
left_shoulder_pitch, left_shoulder_yaw, left_shoulder_roll,
left_elbow_pitch, left_wrist_roll,
right_shoulder_pitch, right_shoulder_yaw, right_shoulder_roll,
right_elbow_pitch, right_wrist_roll
```

Names must match exactly; the guard never alphabetizes or infers a mapping.
The two knee motor coordinates are constrained to `0..π rad`: `0 rad` is the
`180°` mechanical-lock datum and `π rad` is the `360°` encoder-side datum.
Passive knee and elbow linkage coordinates are not policy axes.

## Guard behavior

- Fixed 50 Hz output cadence.
- Exact 22-axis shape, order, and finite-value validation.
- Strictly monotonic state, token, reference, and activation sequences.
- Source-frame freshness checks and local receipt watchdogs.
- Hard position and velocity clamping plus per-tick velocity slew limiting.
- Explicit guarded activation requiring fresh, fault-free, stationary state.
- Smooth blend from measured state to the baseline stand pose.
- Stale state or reference enters disabled `watchdog_stand`; a new guarded
  activation is required to resume.
- E-stop is immediate and latched. Reset requires fresh, fault-free,
  stationary state and the exact reset confirmation.

The token topic validates token metadata, order, and freshness only. It does
not decode a token or synthesize a reference. In contract v1,
`source_token_sequence` on a reference is optional, so receipt of a token is
not proof that a reference came from that token.

The conservative envelopes in
[`contract.py`](dropbear_wbc_controller/contract.py) are SIL integration
bounds, not measured Dropbear actuator limits. They cannot be widened through
ROS parameters.

## ROS topics

All payloads are compact JSON carried in `std_msgs/msg/String`:

| Topic | Direction | Schema or purpose |
| --- | --- | --- |
| `/dropbear/wbc/token_json` | input | `dropbear-sonic-token-v1` metadata guard |
| `/dropbear/wbc/reference_json` | input | absolute-radian `dropbear-wbc-reference-v1` |
| `/dropbear/wbc/state_json` | input | `dropbear-wbc-state-v1` |
| `/dropbear/wbc/control_json` | input | activate, deactivate, E-stop, or reset |
| `/dropbear/wbc/safe_command_json` | output | `dropbear-wbc-safe-command-v1` SIL data |
| `/dropbear/wbc/status_json` | output | `dropbear-wbc-status-v1` |

Producers and the bridge must share a steady-clock domain. A gateway between
hosts must restamp frames into the bridge host's steady-clock domain and
preserve the original source time separately.

Guarded activation:

```json
{
  "action": "activate",
  "request": {
    "schema": "dropbear-wbc-activation-v1",
    "session_id": "sonic-run-0001",
    "sequence": 1,
    "issued_steady_time_ns": 123456789000,
    "guarded_confirmation": "DROPBEAR_WBC_SIL_GUARDED",
    "authority": "sil_only"
  }
}
```

E-stop and reset:

```json
{"action":"estop","reason":"operator request"}
{"action":"reset_estop","operator_confirmation":"DROPBEAR_WBC_RESET_ESTOP"}
```

Reset returns the guard to `inactive`; it does not reactivate the session.

## Separate from the existing 12-axis JTC

This package is not connected to
[`dropbear_trajectory_bringup`](../dropbear_trajectory_bringup/README.md).

| | This WBC JSON guard | Existing trajectory bringup |
| --- | --- | --- |
| Axis contract | 22 semantic motor names, legs and arms | 12 USD-labelled leg axes |
| Input | absolute JSON reference at 50 Hz | ROS `JointTrajectory` or `FollowJointTrajectory` |
| Output | SIL-only safe-command JSON | position interfaces on `mock_components/GenericSystem` |
| Launch | `dropbear_wbc.launch.py` | `dropbear_trajectory.launch.py` |

Launching either package does not start the other. There is no 22-to-12
mapping, safe-command consumer, trajectory forwarder, aggregate launch file,
or 22-axis JTC here. In particular,
`/dropbear/wbc/safe_command_json` is not forwarded to
`dropbear_joint_trajectory_controller`.

Any future integration must explicitly map the 22 semantic motor coordinates
to reviewed backend names, resolve the ten arm axes and all sign/limit
conventions, and remain SIL-only until separately admitted.

## Build and run with ROS 2 Jazzy

Run from the repository root. `--log-base` is a global `colcon` argument and
therefore appears before the `build` verb:

```bash
source /opt/ros/jazzy/setup.bash
colcon --log-base /tmp/dropbear_wbc_log build \
  --symlink-install \
  --base-paths ros2_control/dropbear_wbc_controller \
  --build-base /tmp/dropbear_wbc_build \
  --install-base /tmp/dropbear_wbc_install
source /tmp/dropbear_wbc_install/setup.bash
ros2 launch dropbear_wbc_controller dropbear_wbc.launch.py
```

## Tests and exact import paths

The dependency-free guard tests require the package source directory on
`PYTHONPATH` when run from the repository root without installing it:

```bash
PYTHONPATH="$PWD/ros2_control/dropbear_wbc_controller${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m pytest -q ros2_control/dropbear_wbc_controller/test
```

The cross-boundary test verifies that the local authored-reference adapter
matches the teaching-plant formula and that its payload is accepted by the ROS
contract:

```bash
PYTHONPATH="$PWD:$PWD/ros2_control/dropbear_wbc_controller${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m pytest -q tests/rl/test_sonic_action.py
```

CUDA-first policy inference remains in the external local policy process. The
guard tests intentionally remain CPU-only so watchdog, schema, and limit
behavior can be verified independently of GPU availability.

## Hardware and transport boundary

This package opens no CAN, serial, WebSocket, ZeroMQ, or vendor actuator
transport. It claims no command lease, exposes no `hardware_interface`, and
contains no automatic consumer for `/dropbear/wbc/safe_command_json`.
`command_enabled: true` means only that the SIL guard state machine enabled
that output frame; it is not permission to energize a motor.

Physical transport, calibrated limits, feedback provenance, independent
watchdogs, command arbitration, fault handling, and emergency power removal
are all outside this package. No hardware-readiness or full-passthrough claim
is made by this README or by the `sil_only` output.
