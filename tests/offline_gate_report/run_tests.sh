#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v tests.offline_gate_report.test_offline_gate_report
