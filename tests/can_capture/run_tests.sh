#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHONPATH="$ROOT/host${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.can_capture.test_can_capture
