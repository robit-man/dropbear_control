from dropbear_wbc_controller import ros_bridge


def test_ros_bridge_module_is_importable_without_ros():
    assert isinstance(ros_bridge.ROS_AVAILABLE, bool)
