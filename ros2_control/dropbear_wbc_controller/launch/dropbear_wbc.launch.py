from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("dropbear_wbc_controller"))
    return LaunchDescription(
        [
            Node(
                package="dropbear_wbc_controller",
                executable="dropbear_wbc_bridge",
                name="dropbear_wbc_bridge",
                parameters=[str(share / "config" / "dropbear_wbc.yaml")],
                output="screen",
            )
        ]
    )
