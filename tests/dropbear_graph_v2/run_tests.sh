#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/manage_dropbear_graph_v2.py --check
PYTHONPATH=host python3 -m unittest -v \
  tests.dropbear_graph_v2.test_dropbear_graph_v2
