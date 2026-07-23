#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

PYTHONPATH="$root" python3 -m unittest -v tests.flattened_partition.test_flattened_partition
python3 tools/summarize_flattened_partition_packets.py
