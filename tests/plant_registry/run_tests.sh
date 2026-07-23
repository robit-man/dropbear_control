#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH="$ROOT_DIR/host:$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.plant_registry.test_plant_registry
python3 tools/generate_plant_registry.py --check
