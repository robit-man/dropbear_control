#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 tools/generate_evidence_intake.py --check
python3 -m unittest tests.evidence_intake.test_evidence_intake -v
