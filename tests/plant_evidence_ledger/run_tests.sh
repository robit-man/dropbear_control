#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 tools/generate_plant_evidence_ledger.py --check
python3 -m unittest \
  tests.plant_evidence_ledger.test_plant_evidence_ledger -v
