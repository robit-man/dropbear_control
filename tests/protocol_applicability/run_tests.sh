#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

python3 tools/generate_protocol_applicability_registry.py --check
python3 tools/manage_protocol_applicability_decisions.py --check-directory
PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest \
    tests.protocol_applicability.test_protocol_applicability -v
