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
  -Ifirmware/esp32/src/hostlink
  -Ifirmware/esp32/src/safety
  -Ifirmware/esp32/src/protocols
)
SOURCES=(
  firmware/esp32/src/runtime/host_command_ingress.cpp
  firmware/esp32/src/runtime/gateway_transport_runtime.cpp
  firmware/esp32/src/gateway/gateway_core.cpp
  firmware/esp32/src/hostlink/hostlink_v1.cpp
  firmware/esp32/src/safety/config_identity_guard.cpp
  firmware/esp32/src/safety/safety_supervisor.cpp
  firmware/esp32/src/protocols/rmd_v44_codec.cpp
  tests/host_command_ingress/test_host_command_ingress.cpp
)

g++ "${FLAGS[@]}" "${SOURCES[@]}" -o "$BUILD_DIR/ingress_tests"
"$BUILD_DIR/ingress_tests"

g++ "${FLAGS[@]}" -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${SOURCES[@]}" -o "$BUILD_DIR/ingress_tests_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$BUILD_DIR/ingress_tests_sanitized"

g++ "${FLAGS[@]}" -c \
  firmware/esp32/src/runtime/host_command_ingress.cpp \
  -o "$BUILD_DIR/ingress.o"
if nm -u "$BUILD_DIR/ingress.o" | grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "host command ingress unexpectedly references dynamic allocation" >&2
  exit 1
fi

echo "HOST_COMMAND_INGRESS_SANITIZERS_OK"
