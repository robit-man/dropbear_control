#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
cd "$root"

export PYTHONPATH="$root/host${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.hostlink.test_hostlink_v1
python3 tests/hostlink_native/verify_golden.py

cxx="${CXX:-g++}"
common=(
    -std=c++11
    -Wall -Wextra -Werror -pedantic
    -fno-exceptions -fno-rtti
    -Ifirmware/esp32/src/hostlink
)

"$cxx" "${common[@]}" \
    -c firmware/esp32/src/hostlink/hostlink_v1.cpp \
    -o "$build/hostlink_v1.o"

if nm -u "$build/hostlink_v1.o" | \
    grep -Eq '(_Zn[aw]|malloc|calloc|realloc|free|__cxa_throw|__cxa_allocate_exception)'; then
    echo "native host-link object references allocation/exception symbols" >&2
    exit 1
fi

sanitizers=()
if [[ "${SANITIZE:-1}" != "0" ]]; then
    sanitizers=(
        -fsanitize=address,undefined
        -fno-sanitize-recover=all
        -fno-omit-frame-pointer
    )
fi

"$cxx" "${common[@]}" "${sanitizers[@]}" \
    firmware/esp32/src/hostlink/hostlink_v1.cpp \
    tests/hostlink_native/test_hostlink_v1.cpp \
    -o "$build/test_hostlink_v1"

ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:halt_on_error=1}" \
UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}" \
    "$build/test_hostlink_v1" \
    tests/hostlink_native/golden_hostlink_v1.tsv

if command -v clang++ >/dev/null 2>&1; then
    clang++ "${common[@]}" \
        firmware/esp32/src/hostlink/hostlink_v1.cpp \
        tests/hostlink_native/test_hostlink_v1.cpp \
        -o "$build/test_hostlink_v1_clang"
    "$build/test_hostlink_v1_clang" \
        tests/hostlink_native/golden_hostlink_v1.tsv
fi
