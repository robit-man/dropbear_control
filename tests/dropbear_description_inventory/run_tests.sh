#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 tools/generate_dropbear_description_inventory.py --check
PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v \
    tests.dropbear_description_inventory.test_dropbear_description_inventory
