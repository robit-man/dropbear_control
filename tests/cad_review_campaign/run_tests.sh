#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_cad_review_campaign.py --check
python3 -m unittest tests.cad_review_campaign.test_cad_review_campaign -v
