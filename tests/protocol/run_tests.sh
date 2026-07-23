#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cd "$ROOT_DIR"

PYTHONPATH="$ROOT_DIR/host${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.protocol.test_rmd_v44

CXX_BIN="${CXX:-g++}"
"$CXX_BIN" \
  -std=c++11 \
  -Wall -Wextra -Werror -pedantic \
  -Ifirmware/esp32/src/protocols \
  firmware/esp32/src/protocols/rmd_v44_codec.cpp \
  tests/protocol/test_rmd_v44_codec.cpp \
  -o "$BUILD_DIR/test_rmd_v44_codec"

"$BUILD_DIR/test_rmd_v44_codec" tests/protocol/golden_v44.tsv
