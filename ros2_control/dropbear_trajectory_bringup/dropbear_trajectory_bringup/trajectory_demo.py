"""Send a monitored twelve-axis FollowJointTrajectory demonstration goal."""

from __future__ import annotations

import argparse
import math

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectoryPoint

from .protocol import JOINT_NAMES


class DemoClient(Node):
    def __init__(self, amplitude: float, duration: float) -> None:
        super().__init__("dropbear_trajectory_demo")
        self.amplitude = amplitude
        self.duration = duration
        self.client = ActionClient(
            self,
            FollowJointTrajectory,
            "/dropbear_joint_trajectory_controller/follow_joint_trajectory",
        )

    def send(self):
        if not self.client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("FollowJointTrajectory server did not become ready")
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = list(JOINT_NAMES)
        neutral = JointTrajectoryPoint()
        neutral.positions = [0.0] * len(JOINT_NAMES)
        neutral.time_from_start.sec = 1
        pose = JointTrajectoryPoint()
        pose.positions = [
            self.amplitude * math.sin(index * math.pi / 5.5)
            for index in range(len(JOINT_NAMES))
        ]
        for knee_index in (4, 7):
            pose.positions[knee_index] = abs(pose.positions[knee_index])
        pose.time_from_start.sec = int(self.duration)
        pose.time_from_start.nanosec = int(
            (self.duration - int(self.duration)) * 1_000_000_000
        )
        goal.trajectory.points = [neutral, pose]
        return self.client.send_goal_async(
            goal,
            feedback_callback=lambda feedback: self.get_logger().info(
                f"trajectory feedback: {len(feedback.feedback.actual.positions)} joints"
            ),
        )


def main(args=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--amplitude", type=float, default=0.18)
    parser.add_argument("--duration", type=float, default=3.0)
    known, ros_args = parser.parse_known_args(args=args)
    if not 0.0 <= known.amplitude <= 0.5:
        parser.error("--amplitude must be between 0 and 0.5 radians")
    if known.duration < 1.0:
        parser.error("--duration must be at least 1 second")
    rclpy.init(args=ros_args)
    node = DemoClient(known.amplitude, known.duration)
    try:
        goal_future = node.send()
        rclpy.spin_until_future_complete(node, goal_future)
        goal_handle = goal_future.result()
        if not goal_handle.accepted:
            raise RuntimeError("trajectory goal rejected")
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(node, result_future)
        result = result_future.result()
        node.get_logger().info(
            f"trajectory result status={result.status} error_code={result.result.error_code}"
        )
        if result.result.error_code != FollowJointTrajectory.Result.SUCCESSFUL:
            raise RuntimeError(result.result.error_string or "trajectory failed")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
