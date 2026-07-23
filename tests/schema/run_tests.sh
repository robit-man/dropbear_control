#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

python3 -m json.tool schemas/dropbear-config.schema.json >/dev/null
python3 -m json.tool schemas/examples/dropbear-observed-incomplete.json >/dev/null
python3 schemas/validate_dropbear_config.py \
  schemas/examples/dropbear-observed-incomplete.json
python3 -m unittest discover -s tests/schema -p 'test_*.py' -v
