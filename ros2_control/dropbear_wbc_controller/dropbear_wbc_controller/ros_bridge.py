"""Optional ROS 2 JSON transport for the dependency-free WBC guard."""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from .contract import (
    ActivationRequest,
    ContractError,
    JointReferenceFrame,
    MotionTokenFrame,
    RobotStateFrame,
)
from .safety import SafetyConfig, WbcSafetyController

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    ROS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on non-ROS hosts
    rclpy = None
    Node = object  # type: ignore[assignment,misc]
    String = None
    ROS_AVAILABLE = False


if ROS_AVAILABLE:

    class DropbearWbcBridge(Node):
        """50 Hz std_msgs/String bridge; it contains no physical transport."""

        def __init__(self) -> None:
            super().__init__("dropbear_wbc_bridge")
            self.declare_parameter("control_hz", 50.0)
            self.declare_parameter("command_timeout_sec", 0.10)
            self.declare_parameter("state_timeout_sec", 0.10)
            self.declare_parameter("stand_blend_sec", 1.0)
            self.declare_parameter("watchdog_blend_sec", 0.75)
            self.declare_parameter("activation_max_velocity_rad_s", 0.15)
            self.declare_parameter("source_future_tolerance_sec", 0.025)
            self.declare_parameter("limits_profile", "conservative_sil_v1")
            if self.get_parameter("limits_profile").value != "conservative_sil_v1":
                raise RuntimeError(
                    "only the versioned conservative_sil_v1 limits profile is admitted"
                )
            config = SafetyConfig(
                control_hz=float(self.get_parameter("control_hz").value),
                command_timeout_sec=float(
                    self.get_parameter("command_timeout_sec").value
                ),
                state_timeout_sec=float(
                    self.get_parameter("state_timeout_sec").value
                ),
                stand_blend_sec=float(
                    self.get_parameter("stand_blend_sec").value
                ),
                watchdog_blend_sec=float(
                    self.get_parameter("watchdog_blend_sec").value
                ),
                activation_max_velocity_rad_s=float(
                    self.get_parameter("activation_max_velocity_rad_s").value
                ),
                source_future_tolerance_sec=float(
                    self.get_parameter("source_future_tolerance_sec").value
                ),
            )
            self.guard = WbcSafetyController(config)
            self.command_pub = self.create_publisher(
                String, "/dropbear/wbc/safe_command_json", 10
            )
            self.status_pub = self.create_publisher(
                String, "/dropbear/wbc/status_json", 10
            )
            self.create_subscription(
                String,
                "/dropbear/wbc/state_json",
                self._on_state,
                10,
            )
            self.create_subscription(
                String,
                "/dropbear/wbc/reference_json",
                self._on_reference,
                10,
            )
            self.create_subscription(
                String,
                "/dropbear/wbc/token_json",
                self._on_token,
                10,
            )
            self.create_subscription(
                String,
                "/dropbear/wbc/control_json",
                self._on_control,
                10,
            )
            self.timer = self.create_timer(1.0 / config.control_hz, self._tick)
            self.get_logger().warning(
                "Dropbear WBC bridge started with SIL-only authority; "
                "no hardware transport is present"
            )

        @staticmethod
        def _now_ns() -> int:
            return time.monotonic_ns()

        @staticmethod
        def _json(message: String) -> Dict[str, Any]:
            value = json.loads(message.data)
            if not isinstance(value, dict):
                raise ContractError("JSON message must contain an object")
            return value

        def _on_state(self, message: String) -> None:
            self._guard_call(
                lambda: self.guard.observe_state(
                    RobotStateFrame.from_dict(self._json(message)),
                    receipt_steady_time_ns=self._now_ns(),
                ),
                "state",
            )

        def _on_reference(self, message: String) -> None:
            self._guard_call(
                lambda: self.guard.submit_reference(
                    JointReferenceFrame.from_dict(self._json(message)),
                    receipt_steady_time_ns=self._now_ns(),
                ),
                "reference",
            )

        def _on_token(self, message: String) -> None:
            self._guard_call(
                lambda: self.guard.accept_token(
                    MotionTokenFrame.from_dict(self._json(message)),
                    receipt_steady_time_ns=self._now_ns(),
                ),
                "token",
            )

        def _on_control(self, message: String) -> None:
            def apply() -> None:
                payload = self._json(message)
                action = payload.get("action")
                now_ns = self._now_ns()
                if action == "activate":
                    self.guard.activate(
                        ActivationRequest.from_dict(payload.get("request")),
                        now_ns=now_ns,
                    )
                elif action == "deactivate":
                    self.guard.deactivate(str(payload.get("reason", "operator deactivated")))
                elif action == "estop":
                    self.guard.latch_estop(
                        str(payload.get("reason", "ROS estop request"))
                    )
                elif action == "reset_estop":
                    self.guard.reset_estop(
                        operator_confirmation=str(
                            payload.get("operator_confirmation", "")
                        ),
                        now_ns=now_ns,
                    )
                else:
                    raise ContractError("unknown control action")

            self._guard_call(apply, "control")

        def _guard_call(self, operation: Any, source: str) -> None:
            try:
                operation()
            except (ContractError, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.get_logger().error(f"rejected {source} frame: {exc}")
                self._publish_status({"last_rejection": f"{source}: {exc}"})

        def _tick(self) -> None:
            now_ns = self._now_ns()
            try:
                command = self.guard.tick(now_ns)
                message = String()
                message.data = json.dumps(
                    command.to_dict(), separators=(",", ":"), sort_keys=True
                )
                self.command_pub.publish(message)
                self._publish_status()
            except ContractError as exc:
                self.guard.latch_estop(f"guard tick failed: {exc}")
                self._publish_status({"last_rejection": f"tick: {exc}"})

        def _publish_status(self, extra: Dict[str, Any] | None = None) -> None:
            payload = self.guard.status_dict(self._now_ns())
            if extra:
                payload.update(extra)
            message = String()
            message.data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            self.status_pub.publish(message)


def main(args: Any = None) -> None:
    if not ROS_AVAILABLE:
        raise RuntimeError(
            "ROS 2 Python packages are unavailable; the pure-Python contracts "
            "and tests remain usable"
        )
    assert rclpy is not None
    rclpy.init(args=args)
    node = DropbearWbcBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        # ``ros2 launch`` may already have shut the context down while
        # delivering SIGINT. Treat an operator stop as a clean node exit.
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
