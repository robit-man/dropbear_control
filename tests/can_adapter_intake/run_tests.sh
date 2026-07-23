#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/manage_can_adapter_intake.py --check
PYTHONPATH=host python3 -m unittest -v \
  tests.can_adapter_intake.test_can_adapter_intake
