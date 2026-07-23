#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}"

python3 -m unittest discover \
  -s "$root/tests/download_index" \
  -p 'test_*.py' \
  -v
