#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/audit_claim_surfaces.py --check
python3 -m unittest -v tests.claim_surface.test_claim_surface
