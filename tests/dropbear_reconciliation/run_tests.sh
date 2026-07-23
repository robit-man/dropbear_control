#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

python3 tools/generate_dropbear_reconciliation.py --check
python3 -m unittest discover -s tests/dropbear_reconciliation -p 'test_*.py' -v
