#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

python3 tools/generate_dropbear_views.py --check
python3 -m unittest discover -s tests/config_views -p 'test_*.py' -v
