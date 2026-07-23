#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$(mktemp -d)"
trap 'rm -rf "${BUILD}"' EXIT
cd "${ROOT}"

PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v \
    tests.security_authorization.test_security_authorization

FLAGS=(
  -std=c++11 -Wall -Wextra -Werror -pedantic -fno-exceptions -fno-rtti
  -Ifirmware/esp32/src/security
)
SOURCES=(
  firmware/esp32/src/security/security_authorization_core.cpp
  tests/security_authorization/test_security_authorization.cpp
)

g++ "${FLAGS[@]}" "${SOURCES[@]}" -o "${BUILD}/security_authorization_tests"
"${BUILD}/security_authorization_tests"

g++ "${FLAGS[@]}" -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${SOURCES[@]}" -o "${BUILD}/security_authorization_tests_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "${BUILD}/security_authorization_tests_sanitized"

g++ "${FLAGS[@]}" -c \
  firmware/esp32/src/security/security_authorization_core.cpp \
  -o "${BUILD}/security_authorization_core.o"
if nm -u "${BUILD}/security_authorization_core.o" |
  grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "security authorization core unexpectedly references allocation" >&2
  exit 1
fi

echo "SECURITY_AUTHORIZATION_SANITIZERS_OK"
