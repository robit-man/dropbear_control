#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root" python3 -m unittest -v tests.cad_review_decision.test_review_decision
python3 tools/manage_cad_review_decisions.py --check-templates
