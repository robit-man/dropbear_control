#!/usr/bin/env python3
"""Apply the required uartSetPins return-value fix to ESP32 Arduino 2.0.13."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path


RELATIVE_UART_SOURCE = Path("2.0.13/cores/esp32/esp32-hal-uart.c")
BROKEN = b'''    if(uart_num >= SOC_UART_NUM) {
        log_e("Serial number is invalid, please use numers from 0 to %u", SOC_UART_NUM - 1);
        return;
    }
'''
FIXED = b'''    if(uart_num >= SOC_UART_NUM) {
        log_e("Serial number is invalid, please use numers from 0 to %u", SOC_UART_NUM - 1);
        return false;
    }
'''


def patch(core_root: Path) -> tuple[str, Path]:
    target = core_root.expanduser().resolve() / RELATIVE_UART_SOURCE
    if not target.is_file():
        raise RuntimeError(f"ESP32 Arduino 2.0.13 UART source was not found: {target}")

    source = target.read_bytes()
    function_start = source.find(b"bool uartSetPins(")
    function_end = source.find(b"bool uartSetHwFlowCtrlMode(", function_start)
    if function_start < 0 or function_end <= function_start:
        raise RuntimeError("could not isolate uartSetPins in the reviewed ESP32 core source")
    function = source[function_start:function_end]
    if FIXED in function and BROKEN not in function:
        return "already-fixed", target
    if function.count(BROKEN) != 1:
        raise RuntimeError(
            "ESP32 UART source does not match the reviewed 2.0.13 defect; refusing an uncertain edit"
        )

    corrected_function = function.replace(BROKEN, FIXED, 1)
    corrected = source[:function_start] + corrected_function + source[function_end:]
    temporary = target.with_name(f".{target.name}.dropbear-{os.getpid()}.tmp")
    temporary.write_bytes(corrected)
    temporary.chmod(target.stat().st_mode)
    os.replace(temporary, target)
    return "patched", target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--core-root",
        type=Path,
        default=Path.home() / ".arduino15/packages/esp32/hardware/esp32",
        help="Directory containing the installed ESP32 Arduino core versions",
    )
    args = parser.parse_args()
    state, target = patch(args.core_root)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"{state}: {target}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
