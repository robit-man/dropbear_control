#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

cd "${ROOT}"

COMMON_FLAGS=(
  -std=c++11
  -Wall
  -Wextra
  -Werror
  -pedantic
  -fno-exceptions
  -fno-rtti
  -Ifirmware/esp32/src/gateway
  -Ifirmware/esp32/src/safety
  -Ifirmware/esp32/src/protocols
)
SOURCES=(
  firmware/esp32/src/gateway/gateway_core.cpp
  firmware/esp32/src/safety/config_identity_guard.cpp
  firmware/esp32/src/safety/safety_supervisor.cpp
  firmware/esp32/src/protocols/rmd_v44_codec.cpp
  tests/gateway_core/test_gateway_core.cpp
)

g++ "${COMMON_FLAGS[@]}" "${SOURCES[@]}" \
  -o "${BUILD_DIR}/gateway_core_tests"
"${BUILD_DIR}/gateway_core_tests"

g++ "${COMMON_FLAGS[@]}" \
  -fsanitize=address,undefined \
  -fno-omit-frame-pointer \
  "${SOURCES[@]}" \
  -o "${BUILD_DIR}/gateway_core_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "${BUILD_DIR}/gateway_core_sanitized"

g++ "${COMMON_FLAGS[@]}" \
  -c firmware/esp32/src/gateway/gateway_core.cpp \
  -o "${BUILD_DIR}/gateway_core.o"
if nm -u "${BUILD_DIR}/gateway_core.o" | grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "gateway core unexpectedly references dynamic allocation" >&2
  exit 1
fi

echo "GATEWAY_CORE_SANITIZERS_OK"
