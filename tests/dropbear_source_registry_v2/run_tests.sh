#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 tools/manage_dropbear_source_registry_v2.py --check
PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v \
    tests.dropbear_source_registry_v2.test_dropbear_source_registry_v2
