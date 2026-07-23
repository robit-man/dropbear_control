#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

cd "$root"
cxx="${CXX:-g++}"
"$cxx" \
  -std=c++11 \
  -Wall -Wextra -Werror -pedantic \
  -Ifirmware/esp32/src/safety \
  firmware/esp32/src/safety/safety_supervisor.cpp \
  tests/safety/test_safety_supervisor.cpp \
  -o "$build/test_safety_supervisor"

"$build/test_safety_supervisor"

"$cxx" \
  -std=c++11 \
  -Wall -Wextra -Werror -pedantic \
  -Ifirmware/esp32/src/safety \
  firmware/esp32/src/safety/safety_supervisor.cpp \
  firmware/esp32/src/safety/fault_evidence.cpp \
  tests/safety/test_fault_evidence.cpp \
  -o "$build/test_fault_evidence"

"$build/test_fault_evidence"

evidence_guard_flags=(
  -std=c++11
  -Wall -Wextra -Werror -pedantic
  -fno-exceptions -fno-rtti
  -Ifirmware/esp32/src/safety
)
evidence_guard_sources=(
  firmware/esp32/src/safety/safety_supervisor.cpp
  firmware/esp32/src/safety/config_identity_guard.cpp
  firmware/esp32/src/safety/motion_evidence_guard.cpp
  tests/safety/test_motion_evidence_guard.cpp
)

"$cxx" "${evidence_guard_flags[@]}" "${evidence_guard_sources[@]}" \
  -o "$build/test_motion_evidence_guard"
"$build/test_motion_evidence_guard"

"$cxx" "${evidence_guard_flags[@]}" \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${evidence_guard_sources[@]}" \
  -o "$build/test_motion_evidence_guard_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$build/test_motion_evidence_guard_sanitized"

"$cxx" "${evidence_guard_flags[@]}" -c \
  firmware/esp32/src/safety/motion_evidence_guard.cpp \
  -o "$build/motion_evidence_guard.o"
if nm -u "$build/motion_evidence_guard.o" |
    grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "motion evidence guard unexpectedly references dynamic allocation" >&2
  exit 1
fi

if command -v clang++ >/dev/null 2>&1; then
  clang++ "${evidence_guard_flags[@]}" "${evidence_guard_sources[@]}" \
    -o "$build/test_motion_evidence_guard_clang"
  "$build/test_motion_evidence_guard_clang"
fi
echo "MOTION_EVIDENCE_GUARD_SANITIZERS_ALLOCATION_AND_CLANG_OK"

monitor_flags=(
  -std=c++11
  -Wall -Wextra -Werror -pedantic
  -fno-exceptions -fno-rtti
  -Ifirmware/esp32/src/safety \
  -Ifirmware/esp32/src/gateway \
  -Ifirmware/esp32/src/protocols \
)
monitor_sources=(
  firmware/esp32/src/safety/safety_supervisor.cpp \
  firmware/esp32/src/safety/config_identity_guard.cpp \
  firmware/esp32/src/safety/fault_evidence.cpp \
  firmware/esp32/src/safety/fault_monitor.cpp \
  firmware/esp32/src/protocols/rmd_v44_codec.cpp \
  firmware/esp32/src/gateway/gateway_core.cpp \
  tests/safety/test_fault_monitor.cpp \
)

"$cxx" "${monitor_flags[@]}" "${monitor_sources[@]}" \
  -o "$build/test_fault_monitor"
"$build/test_fault_monitor"

"$cxx" "${monitor_flags[@]}" \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  "${monitor_sources[@]}" -o "$build/test_fault_monitor_sanitized"
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$build/test_fault_monitor_sanitized"

"$cxx" "${monitor_flags[@]}" -c \
  firmware/esp32/src/safety/fault_monitor.cpp \
  -o "$build/fault_monitor.o"
if nm -u "$build/fault_monitor.o" |
    grep -Eq 'operator new|operator delete|_Zn[wa]|_Zd[al]'; then
  echo "fault monitor unexpectedly references dynamic allocation" >&2
  exit 1
fi

if command -v clang++ >/dev/null 2>&1; then
  clang++ "${monitor_flags[@]}" "${monitor_sources[@]}" \
    -o "$build/test_fault_monitor_clang"
  "$build/test_fault_monitor_clang"
fi
echo "FAULT_MONITOR_SANITIZERS_ALLOCATION_AND_CLANG_OK"

"$cxx" \
  -std=c++11 \
  -Wall -Wextra -Werror -pedantic \
  -Ifirmware/esp32/src/safety \
  -Ifirmware/esp32/src/gateway \
  -Ifirmware/esp32/src/protocols \
  firmware/esp32/src/safety/safety_supervisor.cpp \
  firmware/esp32/src/safety/config_identity_guard.cpp \
  firmware/esp32/src/protocols/rmd_v44_codec.cpp \
  firmware/esp32/src/gateway/gateway_core.cpp \
  tests/safety/test_safety_event_properties.cpp \
  -o "$build/test_safety_event_properties"

"$build/test_safety_event_properties"
