#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

python3 tools/validate_calibration_registry.py
PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v tests.calibration_registry.test_calibration_registry
