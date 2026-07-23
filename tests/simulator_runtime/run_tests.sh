#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_plant_registry.py --check
python3 tools/generate_protocol_applicability_registry.py --check
python3 tools/generate_simulator_runtime_catalog.py --check
PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest \
    tests.simulator_runtime.test_simulator_runtime -v
