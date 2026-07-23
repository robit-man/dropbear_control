#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

cd "$root"
PYTHONPATH=. python3 -m unittest discover \
  -s tests/stack_contract -p 'test_*.py' -v

g++ \
  -std=c++17 \
  -Wall -Wextra -Werror -pedantic \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -fno-omit-frame-pointer \
  -Ifirmware/esp32/src/safety \
  -Igenerated/dropbear/firmware \
  firmware/esp32/src/safety/config_identity_guard.cpp \
  firmware/esp32/src/safety/safety_supervisor.cpp \
  generated/dropbear/firmware/dropbear_config.generated.cpp \
  tests/stack_contract/test_generated_config_guard.cpp \
  -o "$build/test_generated_config_guard"

ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:halt_on_error=1}" \
UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}" \
  "$build/test_generated_config_guard"
