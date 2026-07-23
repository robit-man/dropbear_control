#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_ros2_cpp_environment_lock.py --check

set +u
source /opt/ros/jazzy/setup.bash
set -u
build_root="$(mktemp -d /tmp/myactuator-ros2-handoff.XXXXXX)"
echo "ROS2_CPP_BUILD_ROOT=$build_root"

colcon --log-base "$build_root/log" build \
    --base-paths "$root/ros2_control" \
    --build-base "$build_root/build" \
    --install-base "$build_root/install" \
    --merge-install \
    --cmake-args \
        -DBUILD_TESTING=ON \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DPython3_EXECUTABLE=/usr/bin/python3

set +u
source "$build_root/install/setup.bash"
set -u
colcon --log-base "$build_root/test-log" test \
    --base-paths "$root/ros2_control" \
    --build-base "$build_root/build" \
    --install-base "$build_root/install" \
    --merge-install
colcon --log-base "$build_root/result-log" test-result \
    --test-result-base "$build_root/build" \
    --verbose

MYACTUATOR_CPP_PARITY_BIN="$build_root/build/myactuator_dropbear_hardware/semantic_core_test" \
PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest tests.ros2_control_cpp.test_ros2_control_cpp_handoff -v

python3 tools/generate_ros2_cpp_handoff_report.py \
    --write \
    --parity-bin "$build_root/build/myactuator_dropbear_hardware/semantic_core_test"
python3 tools/generate_ros2_cpp_handoff_report.py \
    --check \
    --parity-bin "$build_root/build/myactuator_dropbear_hardware/semantic_core_test"
