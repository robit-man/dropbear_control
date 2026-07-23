#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

if [[ ! -x .venv/bin/python ]]; then
  printf '%s\n' 'missing pinned CAD environment: create .venv and install requirements-cad-lock.txt' >&2
  exit 2
fi

.venv/bin/python tools/check_cad_toolchain.py
.venv/bin/python tools/prove_cad_toolchain.py --check
python3 -m unittest -v tests.cad_toolchain.test_toolchain_contract

