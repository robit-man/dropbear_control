#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 tools/manage_dropbear_graph_review.py --check
PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v \
    tests.dropbear_graph_review.test_dropbear_graph_review
