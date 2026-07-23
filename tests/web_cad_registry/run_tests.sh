#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root" python3 -m unittest -v tests.web_cad_registry.test_web_cad_registry
python3 tools/generate_web_cad_registry.py --check
node web/test/cad_support.test.mjs
