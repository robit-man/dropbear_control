"""Bidirectional WebSocket bridge between ROS 2 control and the USD dashboard."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import Any, Dict, Optional

import rclpy
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTrajectoryControllerState
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from websockets.asyncio.server import serve

from .protocol import JOINT_NAMES, ProtocolError, SCHEMA, validate_trajectory


def _duration(seconds: float):
    from builtin_interfaces.msg import Duration

    whole = int(seconds)
    nanoseconds = int(round((seconds - whole) * 1_000_000_000))
    if nanoseconds >= 1_000_000_000:
        whole += 1
        nanoseconds -= 1_000_000_000
    return Duration(sec=whole, nanosec=nanoseconds)


def _trajectory_message(request: Dict[str, Any]) -> JointTrajectory:
    message = JointTrajectory()
    message.joint_names = request["joint_names"]
    for source in request["points"]:
        point = JointTrajectoryPoint()
        point.positions = source["positions"]
        point.velocities = source.get("velocities", [])
        point.accelerations = source.get("accelerations", [])
        point.time_from_start = _duration(source["time_from_start"])
        message.points.append(point)
    return message


class DashboardBridge(Node):
    """Expose controller action/topic/state as a local dashboard WebSocket."""

    def __init__(self) -> None:
        super().__init__("dropbear_dashboard_bridge")
        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 9091)
        self.declare_parameter("controller_name", "dropbear_joint_trajectory_controller")
        self.declare_parameter("state_publish_rate", 50.0)
        self.host = str(self.get_parameter("host").value)
        self.port = int(self.get_parameter("port").value)
        self.controller_name = str(self.get_parameter("controller_name").value)
        self.action_name = f"/{self.controller_name}/follow_joint_trajectory"
        self.topic_name = f"/{self.controller_name}/joint_trajectory"
        self.controller_state_name = f"/{self.controller_name}/controller_state"
        self._last_state_sent = 0.0
        self._minimum_state_period = 1.0 / max(
            1.0, float(self.get_parameter("state_publish_rate").value)
        )
        self._inbound: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=100)
        self._clients: set[Any] = set()
        self._websocket_loop: Optional[asyncio.AbstractEventLoop] = None
        self._websocket_stop: Optional[asyncio.Event] = None
        self._active_goal = None

        self.trajectory_publisher = self.create_publisher(
            JointTrajectory, self.topic_name, 10
        )
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 20)
        self.create_subscription(
            JointTrajectoryControllerState,
            self.controller_state_name,
            self._on_controller_state,
            20,
        )
        self.action_client = ActionClient(
            self, FollowJointTrajectory, self.action_name
        )
        self.create_timer(0.01, self._drain_requests)

        self._thread = threading.Thread(
            target=self._run_websocket, name="dropbear-dashboard-websocket", daemon=True
        )
        self._thread.start()
        self.get_logger().info(
            f"dashboard passthrough ws://{self.host}:{self.port} -> {self.action_name}"
        )

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "schema": SCHEMA,
                        "joint_names": JOINT_NAMES,
                        "controller": self.controller_name,
                        "action": self.action_name,
                        "trajectory_topic": self.topic_name,
                    }
                )
            )
            async for raw in websocket:
                if len(raw) > 1_000_000:
                    await websocket.send(
                        json.dumps({"type": "error", "detail": "request too large"})
                    )
                    continue
                try:
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ProtocolError("request must be an object")
                    self._inbound.put_nowait(payload)
                except (json.JSONDecodeError, ProtocolError, queue.Full) as error:
                    await websocket.send(
                        json.dumps({"type": "error", "detail": str(error)})
                    )
        finally:
            self._clients.discard(websocket)

    async def _broadcast_async(self, message: Dict[str, Any]) -> None:
        if not self._clients:
            return
        serialized = json.dumps(message, separators=(",", ":"))
        stale = []
        for client in tuple(self._clients):
            try:
                await client.send(serialized)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        if self._websocket_loop and self._websocket_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._broadcast_async(message), self._websocket_loop
            )

    def _run_websocket(self) -> None:
        async def runner() -> None:
            self._websocket_loop = asyncio.get_running_loop()
            self._websocket_stop = asyncio.Event()
            async with serve(
                self._handler,
                self.host,
                self.port,
                max_size=1_000_000,
                ping_interval=20,
                ping_timeout=20,
            ):
                await self._websocket_stop.wait()

        asyncio.run(runner())

    def _on_joint_state(self, message: JointState) -> None:
        now = time.monotonic()
        if now - self._last_state_sent < self._minimum_state_period:
            return
        by_name = {
            name: index
            for index, name in enumerate(message.name)
            if name in JOINT_NAMES
        }
        if len(by_name) != len(JOINT_NAMES):
            return
        self._last_state_sent = now

        def ordered(values):
            return [
                float(values[by_name[name]]) if by_name[name] < len(values) else 0.0
                for name in JOINT_NAMES
            ]

        self._broadcast(
            {
                "type": "joint_state",
                "schema": SCHEMA,
                "source": "/joint_states",
                "joint_names": JOINT_NAMES,
                "positions": ordered(message.position),
                "velocities": ordered(message.velocity),
                "efforts": ordered(message.effort),
                "stamp": {
                    "sec": message.header.stamp.sec,
                    "nanosec": message.header.stamp.nanosec,
                },
            }
        )

    def _on_controller_state(self, message: JointTrajectoryControllerState) -> None:
        self._broadcast(
            {
                "type": "controller_state",
                "schema": SCHEMA,
                "joint_names": list(message.joint_names),
                "reference": list(message.reference.positions),
                "feedback": list(message.feedback.positions),
                "error": list(message.error.positions),
            }
        )

    def _drain_requests(self) -> None:
        for _ in range(20):
            try:
                payload = self._inbound.get_nowait()
            except queue.Empty:
                return
            request_id = str(payload.get("request_id", ""))[:128]
            try:
                request = validate_trajectory(payload)
                if payload.get("type") == "trajectory":
                    self.trajectory_publisher.publish(_trajectory_message(request))
                    self._broadcast(
                        {
                            "type": "trajectory_published",
                            "request_id": request_id,
                            "topic": self.topic_name,
                        }
                    )
                elif payload.get("type") == "follow_joint_trajectory":
                    self._send_action(request)
                elif payload.get("type") == "cancel_goal":
                    self._cancel_active_goal(request_id)
                else:
                    raise ProtocolError("unsupported request type")
            except (ProtocolError, TypeError, ValueError) as error:
                self._broadcast(
                    {
                        "type": "error",
                        "request_id": request_id,
                        "detail": str(error),
                    }
                )

    def _send_action(self, request: Dict[str, Any]) -> None:
        if not self.action_client.server_is_ready():
            self._broadcast(
                {
                    "type": "action_rejected",
                    "request_id": request["request_id"],
                    "detail": f"{self.action_name} is not ready",
                }
            )
            return
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = _trajectory_message(request)
        future = self.action_client.send_goal_async(
            goal,
            feedback_callback=lambda feedback: self._broadcast(
                {
                    "type": "action_feedback",
                    "request_id": request["request_id"],
                    "joint_names": list(feedback.feedback.joint_names),
                    "desired": list(feedback.feedback.desired.positions),
                    "actual": list(feedback.feedback.actual.positions),
                    "error": list(feedback.feedback.error.positions),
                }
            ),
        )
        future.add_done_callback(
            lambda done: self._goal_response(done, request["request_id"])
        )

    def _goal_response(self, future, request_id: str) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self._broadcast(
                {"type": "action_rejected", "request_id": request_id}
            )
            return
        self._active_goal = goal_handle
        self._broadcast({"type": "action_accepted", "request_id": request_id})
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda done: self._goal_result(done, request_id)
        )

    def _goal_result(self, future, request_id: str) -> None:
        wrapped = future.result()
        self._broadcast(
            {
                "type": "action_result",
                "request_id": request_id,
                "status": int(wrapped.status),
                "error_code": int(wrapped.result.error_code),
                "error_string": wrapped.result.error_string,
            }
        )
        self._active_goal = None

    def _cancel_active_goal(self, request_id: str) -> None:
        if self._active_goal is None:
            self._broadcast(
                {
                    "type": "cancel_result",
                    "request_id": request_id,
                    "detail": "no active goal",
                }
            )
            return
        future = self._active_goal.cancel_goal_async()
        future.add_done_callback(
            lambda done: self._broadcast(
                {
                    "type": "cancel_result",
                    "request_id": request_id,
                    "goals_canceling": len(done.result().goals_canceling),
                }
            )
        )

    def destroy_node(self) -> bool:
        if self._websocket_loop and self._websocket_stop:
            self._websocket_loop.call_soon_threadsafe(self._websocket_stop.set)
        if getattr(self, "_thread", None):
            self._thread.join(timeout=2.0)
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DashboardBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
