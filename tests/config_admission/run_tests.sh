#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

cd "$root"
cxx="${CXX:-g++}"
sanitizers=()
if [[ "${SANITIZE:-1}" != "0" ]]; then
    sanitizers=(-fsanitize=address,undefined -fno-sanitize-recover=all \
                -fno-omit-frame-pointer)
fi

"$cxx" \
    -std=c++11 \
    -Wall -Wextra -Werror -pedantic \
    -fno-exceptions -fno-rtti \
    "${sanitizers[@]}" \
    -Ifirmware/esp32/src/safety \
    firmware/esp32/src/safety/config_identity_guard.cpp \
    firmware/esp32/src/safety/safety_supervisor.cpp \
    tests/config_admission/test_config_identity_guard.cpp \
    -o "$build/test_config_identity_guard"

ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:halt_on_error=1}" \
UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}" \
    "$build/test_config_identity_guard"
