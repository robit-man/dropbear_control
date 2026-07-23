#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_coverage_dashboard.py --check
python3 -m unittest -v tests.coverage_dashboard.test_coverage_dashboard
