#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT
cd "$ROOT"

FLAGS=(
  -std=c++11 -Wall -Wextra -Werror -pedantic -fno-exceptions -fno-rtti
  -Ifirmware/esp32/src/runtime
  -Ifirmware/esp32/src/gateway
  -Ifirmware/esp32/src/safety
  -Ifirmware/esp32/src/protocols
)
SOURCES=(
  firmware/esp32/src/runtime/gateway_transport_runtime.cpp
  firmware/esp32/src/gateway/gateway_core.cpp
  firmware/esp32/src/safety/config_identity_guard.cpp
  firmware/esp32/src/safety/safety_supervisor.cpp
  firmware/esp32/src/protocols/rmd_v44_codec.cpp
  tests/gateway_transport_runtime/test_gateway_transport_runtime.cpp
)

g++ "${FLAGS[@]}" "${SOURCES[@]}" -o "$BUILD_DIR/runtime_tests"
"$BUILD_DIR/runtime_tests"

g++ "${FLAGS[@]}" -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${SOURCES[@]}" -o "$BUILD_DIR/runtime_tests_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$BUILD_DIR/runtime_tests_sanitized"

g++ "${FLAGS[@]}" -c \
  firmware/esp32/src/runtime/gateway_transport_runtime.cpp \
  -o "$BUILD_DIR/runtime.o"
if nm -u "$BUILD_DIR/runtime.o" | grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "gateway transport runtime unexpectedly references dynamic allocation" >&2
  exit 1
fi

echo "GATEWAY_TRANSPORT_RUNTIME_SANITIZERS_OK"
