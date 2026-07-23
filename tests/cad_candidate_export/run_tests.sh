#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root" python3 -m unittest -v tests.cad_candidate_export.test_candidate_export
python3 tools/validate_cad_candidate_reports.py
