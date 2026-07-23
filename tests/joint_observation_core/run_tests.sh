#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD="$(mktemp -d)"
trap 'rm -rf "${BUILD}"' EXIT
cd "${ROOT}"

PYTHONPATH="${ROOT}/host:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  python3 -m unittest -v tests.joint_observation_core.test_joint_observation_reference

FLAGS=(-std=c++11 -Wall -Wextra -Werror -pedantic -fno-exceptions -fno-rtti -Ifirmware/esp32/src/runtime -Ifirmware/esp32/src/hostlink)
SOURCES=(firmware/esp32/src/runtime/joint_observation_core.cpp firmware/esp32/src/hostlink/hostlink_v1.cpp tests/joint_observation_core/test_joint_observation_core.cpp)

g++ "${FLAGS[@]}" "${SOURCES[@]}" -o "${BUILD}/joint_observation_tests"
"${BUILD}/joint_observation_tests"

g++ "${FLAGS[@]}" -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${SOURCES[@]}" -o "${BUILD}/joint_observation_tests_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "${BUILD}/joint_observation_tests_sanitized"

g++ "${FLAGS[@]}" -c firmware/esp32/src/runtime/joint_observation_core.cpp \
  -o "${BUILD}/joint_observation_core.o"
if nm -u "${BUILD}/joint_observation_core.o" | grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "joint observation core unexpectedly references dynamic allocation" >&2
  exit 1
fi

echo "JOINT_OBSERVATION_CORE_SANITIZERS_OK"
