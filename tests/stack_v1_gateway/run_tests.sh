#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cd "$root"

cxx="${CXX:-g++}"
"$cxx" \
  -std=c++17 \
  -Wall -Wextra -Werror -pedantic \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -fno-omit-frame-pointer \
  -Ifirmware/esp32/src/hostlink \
  -Ifirmware/esp32/src/gateway \
  -Ifirmware/esp32/src/runtime \
  -Ifirmware/esp32/src/safety \
  -Ifirmware/esp32/src/protocols \
  -Igenerated/dropbear/firmware \
  firmware/esp32/src/hostlink/hostlink_v1.cpp \
  firmware/esp32/src/gateway/gateway_core.cpp \
  firmware/esp32/src/runtime/host_command_ingress.cpp \
  firmware/esp32/src/safety/config_identity_guard.cpp \
  firmware/esp32/src/safety/safety_supervisor.cpp \
  firmware/esp32/src/protocols/rmd_v44_codec.cpp \
  generated/dropbear/firmware/dropbear_config.generated.cpp \
  tests/stack_v1_gateway/stack_bridge.cpp \
  -o "$build/stack_bridge"

ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:halt_on_error=1}" \
UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}" \
STACK_V1_GATEWAY_BRIDGE="$build/stack_bridge" \
PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest -v tests.stack_v1_gateway.test_stack_v1_gateway

echo "STACK_V1_GATEWAY_EMULATOR_OK"
