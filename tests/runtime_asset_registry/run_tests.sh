#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root" python3 -m unittest -v tests.runtime_asset_registry.test_runtime_asset_registry
python3 tools/generate_cad_runtime_registry.py --check
python3 tools/generate_web_cad_registry.py --check
