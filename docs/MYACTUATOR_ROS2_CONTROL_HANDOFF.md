# MYACTUATOR / Dropbear ROS 2 control handoff

Status: `OFFLINE SOFTWARE VERIFIED / PHYSICAL AND CANONICAL ROBOT HOLD`

This package is the first compiled ROS 2 handoff for the project. It proves
that the existing graph-gated Python hardware semantics can be represented by
a C++ `hardware_interface::SystemInterface` without adding a second motor
command path. It does not connect to a motor, select a CAN adapter, accept the
current Dropbear graph or grant motion authority.

## Verified environment

The exact supported build target is recorded in
`tools/ros2-cpp-environment-lock.json`:

- Ubuntu 24.04, Linux x86-64, glibc 2.39;
- ROS 2 Jazzy;
- `ros2_control` / `hardware_interface` 4.45.2;
- `pluginlib` 5.4.5 and `rclcpp` / `rclcpp_lifecycle` 28.1.21;
- GCC 13.3.0, CMake 3.28.3, C++17 and colcon-core 0.21.0; and
- hashes for the compiler, build tools, four ABI libraries and three API
  headers used by the package.

The lock is intentionally exact. A package or ABI update must produce a new
reviewed lock and rerun the parity/build campaign. ROS 2 Jazzy installation
and lifecycle references are maintained by the
[ROS project](https://docs.ros.org/en/jazzy/Installation.html) and
[`ros2_control`](https://control.ros.org/jazzy/doc/ros2_control/hardware_interface/doc/writing_new_hardware_component.html).

## Boundary

```text
ros2_control controllers
          |
          v
DropbearSystemInterface        ROS lifecycle + framework-managed handles
          |
          v
SemanticCore                   graph/config/generation/lease/limit semantics
          |
          v
SessionPort                    typed backend-neutral handoff
          |
          v
UnavailableSessionPort         shipped default: no I/O and no success path

Future only:
SessionPort -> graph-gated host/gateway adapter -> ESP32 gateway -> motor
```

`DropbearSystemInterface` does not include firmware, CAN, serial, motor IDs,
opcodes, raw frames or vendor-native commands. The shipped session port is
unavailable and the shipped generation provider has no authority snapshot, so
`on_configure` fails closed. A future concrete adapter must sit beneath
`SessionPort` and consume the existing typed gateway/hardware API; it must not
reimplement native motor access in the ROS plugin.

## Package

The ament package is
`ros2_control/myactuator_dropbear_hardware`.

It installs:

- `myactuator_dropbear_semantic_core`, a ROS-independent C++17 library;
- `myactuator_dropbear_system_interface`, the plugin shared library;
- public semantic/plugin headers; and
- the pluginlib class
  `myactuator_dropbear_hardware/DropbearSystemInterface`.

The semantic descriptor field order is exactly equal to
`host/myactuator_lib/ros2_control_core.py`. The common command interfaces are
`position`, `velocity` and `effort`; state interfaces are `position`,
`velocity`, `effort` and `qaxis_current`.

## Required hardware parameters

Every future `<ros2_control>` instance must carry these exact hardware
parameters. They are evidence identities, not convenient defaults.

| Parameter | Meaning |
|---|---|
| `canonical_configuration_digest` | Exact canonical configuration SHA-256 |
| `accepted_graph_decision_id` | Independently accepted graph decision |
| `accepted_graph_sha256` | Accepted graph artifact SHA-256 |
| `source_registry_generation_sha256` | Active source-authority generation |
| `graph_registry_generation_sha256` | Active graph-authority generation |
| `simulator_catalog_generation_sha256` | Exact runtime catalog generation |
| `configuration_generation` | Positive configured-session generation |
| `session_id`, `session_owner` | Unique typed control-session identity |
| `lease_id`, `lease_owner`, `lease_sequence` | Command ownership identity |
| `lease_issued_monotonic_ns`, `lease_expires_monotonic_ns` | Authority-issued monotonic lease window |
| `command_deadline_ns` | Positive per-cycle command validity interval |

Each joint also requires:

| Parameter | Meaning |
|---|---|
| `canonical_actuator_id` | One of the twelve canonical Dropbear actuator IDs |
| `position_lower_rad`, `position_upper_rad` | Reviewed joint-position envelope |
| `maximum_velocity_rad_s` | Reviewed absolute joint-velocity limit |
| `maximum_output_effort_nm` | Reviewed absolute output-effort limit |
| `maximum_current_a` | Reviewed current limit carried to typed intent |

Joint and actuator mappings must be one-to-one. Missing fields, duplicate
mappings, unknown interfaces, non-finite numbers, reversed limits, stale
generations and expired timing all deny.

## Lifecycle and cycle behavior

| ROS callback | Semantic transition | Failure behavior |
|---|---|---|
| `on_init` | Parse and validate exact descriptor | `ERROR`; no core retained |
| `on_configure` | `UNCONFIGURED -> INACTIVE` | `FAILURE` on missing/stale authority or adapter |
| `on_activate` | Validate lease and open every exact handle | Deny and fault if any handle is unavailable |
| `read` | Read all joints without issuing commands | Fault atomically; return no partial semantic state |
| `write` | Validate generation, sequence, deadline, lease, interface and limit | Invalid/stale/timeout remain distinct; backend failure faults |
| `on_deactivate` | `ACTIVE -> INACTIVE` and revoke handles | Critical callback failure |
| `on_cleanup` | `INACTIVE/FAULTED -> UNCONFIGURED` | Critical callback failure |
| `on_shutdown` | `UNCONFIGURED -> FINALIZED` | Critical callback failure |
| `on_error` | Latch semantic fault and clear the lease | ROS error result; never auto-resume |

The semantic core preserves optional values, signal validity, source age and
provenance. The standard ROS state handles can carry only scalar values, so
the thin plugin writes a real value only for `VALID` signals. Missing, stale
or faulted signals become IEEE NaN, never zero. A later diagnostics/state
message may expose the full non-real-time provenance record, but it may not
turn invalid values into controller-ready numbers.

## Reproduce

With the ROS apt repository configured:

```bash
sudo apt-get install ros-jazzy-ros2-control python3-colcon-common-extensions
tests/ros2_control_cpp/run_tests.sh
```

The runner:

1. verifies every package, tool, ABI binary and API header against the lock;
2. performs a clean temporary colcon build without physical hardware;
3. runs the native semantic and plugin-load CTests;
4. runs six repository mutation/static/parity tests;
5. compares six C++ transcript lines byte-for-byte with outcomes generated by
   the live Python semantic core; and
6. atomically writes and rechecks
   `generated/myactuator/ros2_control_cpp_handoff/report.json`.

The verified vectors cover descriptor fields, configure/activate/deactivate/
cleanup/shutdown, stale generation, early/expired deadline, limit denial,
successful write, replay denial, validity-preserving read and live generation
revocation.

## What remains before canonical ROS control

The following are deliberately absent:

- an accepted Dropbear source decision and resolved 161-question graph;
- generated canonical frames, transmissions and twelve actuator/ROS mappings;
- reviewed CAD/output axes, real plant parameters and physical calibration;
- a live source/graph/catalog generation provider;
- an authority-owned renewable command-lease provider;
- a concrete `SessionPort` adapter over the approved gateway API;
- authenticated multi-client arbitration and non-real-time provenance
  publication;
- controller-manager integration against the accepted robot description;
- SIL with the canonical robot, HIL, stop-distance, bus-off, power-cut and
  long-haul physical evidence.

Until those dependencies are independently accepted, the plugin’s correct
runtime result is denial.
