# Dropbear ROS 2 trajectory passthrough

This package provides a complete ROS 2 Jazzy SIL path for the twelve low-level
Dropbear motors:

```text
FollowJointTrajectory action / JointTrajectory topic
                |
dropbear_joint_trajectory_controller
                |
position command + position/velocity state interfaces
                |
mock_components/GenericSystem (SIL only)
                |
/joint_states + controller_state
                |
local WebSocket bridge (ws://127.0.0.1:9091)
                |
browser adapter integration boundary
                |
browser Dropbear USD / exact CAN-to-USD map
```

The action endpoint is:

```text
/dropbear_joint_trajectory_controller/follow_joint_trajectory
```

The fire-and-forget topic is:

```text
/dropbear_joint_trajectory_controller/joint_trajectory
```

The dashboard bridge supports monitored action goals, topic trajectories,
cancel, action feedback/results, controller state, and ordered `/joint_states`.
It binds to loopback by default and validates the exact twelve-axis set,
finite values, strictly increasing times, point count, and a ±π SIL envelope.
Both knee actuator coordinates use the mechanical-lock datum: `0 rad` is the
browser/encoder `180°` lock and `π rad` is `360°`. Negative knee goals are
rejected before reaching `joint_trajectory_controller`.

## Install and build

From the repository root:

```bash
sudo ros2_control/setup_ros2_jazzy.sh
source /opt/ros/jazzy/setup.bash
colcon --log-base /tmp/dropbear_ros2_log build --symlink-install \
  --base-paths ros2_control/dropbear_trajectory_bringup \
  --build-base /tmp/dropbear_ros2_build \
  --install-base /tmp/dropbear_ros2_install
source /tmp/dropbear_ros2_install/setup.bash
```

## Run

```bash
ros2 launch dropbear_trajectory_bringup dropbear_trajectory.launch.py
```

The bridge listens on `ws://127.0.0.1:9091` and exposes the ordered ROS state
and trajectory request protocol needed by the USD dashboard. The current
tracked browser dashboard still runs its internal low-level simulator and
does not automatically open this WebSocket. Wiring that browser adapter is a
remaining integration step; this package completes and tests the ROS-side SIL
boundary.

Send a monitored action goal:

```bash
ros2 run dropbear_trajectory_bringup trajectory_demo --amplitude 0.18 --duration 3.0
```

Inspect the controller:

```bash
ros2 control list_controllers
ros2 action info /dropbear_joint_trajectory_controller/follow_joint_trajectory
ros2 topic echo /dropbear_joint_trajectory_controller/controller_state
ros2 topic echo /joint_states
```

## Hardware boundary

The included URDF is a controller-interface description, not a claim that the
closed-loop USD has been converted into canonical URDF kinematics. It uses
`mock_components/GenericSystem` for SIL and browser passthrough.

The separate `myactuator_dropbear_hardware/DropbearSystemInterface` remains
fail-closed. Replacing the SIL plugin with physical CAN requires the reviewed
`SessionPort`, accepted graph/config generations, a live command lease,
calibration/limit evidence, and HIL safety gates. This package does not create
a second physical motor command path.
