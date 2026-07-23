#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 tools/generate_plant_spec_candidates.py --check
python3 -m unittest \
  tests.plant_spec_candidates.test_plant_spec_candidates -v
