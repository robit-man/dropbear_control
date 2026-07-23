#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHONPATH="$ROOT/host:$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.plant_parameter_sets.test_plant_parameter_sets
python3 tools/generate_plant_parameter_sets.py --check
