#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest tests.ros2_control_core.test_ros2_control_core -v
