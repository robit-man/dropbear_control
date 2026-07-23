#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH="$ROOT_DIR/host${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.host_cad_assets.test_cad_assets
