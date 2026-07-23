#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

PYTHONPATH="${ROOT}/host${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v tests.plant_runtime_adapter.test_plant_runtime_adapter
python3 tools/generate_plant_runtime_adapters.py --check
