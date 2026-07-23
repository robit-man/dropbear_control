#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
PYTHONPATH=host python3 -m unittest \
  tests.rigid_body_benchmark.test_rigid_body_benchmark -v
PYTHONPATH=host python3 tools/run_rigid_body_benchmark.py --check
