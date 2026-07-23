#!/usr/bin/env python3
"""Verify the checked-in corpus against the Python host-link V1 authority."""

from __future__ import annotations

import csv
import io
import pathlib
import subprocess
import sys

from myactuator_lib import hostlink_v1 as hl


ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS = pathlib.Path(__file__).with_name("golden_hostlink_v1.tsv")
GENERATOR = pathlib.Path(__file__).with_name("generate_golden.py")


def main() -> int:
    generated = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "host")},
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    checked_in = CORPUS.read_text(encoding="utf-8")
    if generated != checked_in:
        raise AssertionError("golden_hostlink_v1.tsv is not generator-reproducible")

    counts = {"accept": 0, "reject_frame": 0, "reject_body": 0}
    types = set()
    for row in csv.DictReader(io.StringIO(checked_in), delimiter="\t"):
        raw = bytes.fromhex(row["frame_hex"])
        outcome = row["outcome"]
        counts[outcome] += 1
        if outcome == "reject_frame":
            try:
                hl.decode_frame(raw)
            except hl.FrameError:
                continue
            raise AssertionError(f"{row['name']} unexpectedly passed frame decode")
        decoded = hl.decode_frame(raw)
        if outcome == "reject_body":
            try:
                hl.decode_message(decoded)
            except hl.BodyError:
                continue
            raise AssertionError(f"{row['name']} unexpectedly passed body decode")
        body = hl.decode_message(decoded)
        types.add(type(body).__name__.upper())
        if hl.encode_frame(decoded) != raw:
            raise AssertionError(f"{row['name']} did not round-trip byte-exactly")
    expected_types = {
        "HELLO",
        "CAPABILITIES",
        "COMMAND",
        "STATE",
        "DISPOSITION",
        "FAULT",
        "HEARTBEAT",
    }
    if not expected_types <= types:
        raise AssertionError(
            f"missing positive message types: {expected_types - types}"
        )
    print(
        "HOSTLINK_GOLDEN_PY_OK",
        sum(counts.values()),
        "vectors",
        counts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
