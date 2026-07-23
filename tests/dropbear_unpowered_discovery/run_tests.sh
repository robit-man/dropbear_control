#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 tools/prepare_dropbear_unpowered_discovery.py --check
PYTHONPATH="${ROOT}:${PYTHONPATH:-}" \
  python3 -m unittest -v \
    tests.dropbear_unpowered_discovery.test_dropbear_unpowered_discovery
