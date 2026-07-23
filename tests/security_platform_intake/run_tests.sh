#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH=host \
  python3 -m unittest -v \
  tests.security_platform_intake.test_security_platform_intake
