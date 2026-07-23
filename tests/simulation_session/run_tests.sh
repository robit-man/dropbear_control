#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_simulator_runtime_catalog.py --check
PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest tests.simulation_session.test_simulation_session -v
