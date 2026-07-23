#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$(mktemp -d)"
trap 'rm -rf "${BUILD}"' EXIT
cd "${ROOT}"

PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v tests.artifact_trust.test_artifact_trust

FLAGS=(
  -std=c++11 -Wall -Wextra -Werror -pedantic -fno-exceptions -fno-rtti
  -Ifirmware/esp32/src/security
)
SOURCES=(
  firmware/esp32/src/security/artifact_trust_core.cpp
  tests/artifact_trust/test_artifact_trust.cpp
)

g++ "${FLAGS[@]}" "${SOURCES[@]}" -o "${BUILD}/artifact_trust_tests"
"${BUILD}/artifact_trust_tests"

g++ "${FLAGS[@]}" -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${SOURCES[@]}" -o "${BUILD}/artifact_trust_tests_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "${BUILD}/artifact_trust_tests_sanitized"

g++ "${FLAGS[@]}" -c \
  firmware/esp32/src/security/artifact_trust_core.cpp \
  -o "${BUILD}/artifact_trust_core.o"
if nm -u "${BUILD}/artifact_trust_core.o" |
  grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "artifact trust core unexpectedly references allocation" >&2
  exit 1
fi

size "${BUILD}/artifact_trust_core.o"
echo "ARTIFACT_TRUST_SANITIZERS_OK"
