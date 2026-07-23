#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_evidence_review_queue.py --check
python3 -m unittest \
  tests.evidence_review_queue.test_evidence_review_queue \
  -v
