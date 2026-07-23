#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHONPATH="$ROOT/host${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v \
    tests.plant_runtime_adapter_v2.test_plant_runtime_adapter_v2
