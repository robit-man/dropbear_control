#!/usr/bin/env python3
"""Fetch and verify the exact Dropbear source USD into the ignored cache."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


REPOSITORY = "https://github.com/Hyperspawn/dropbear_rl.git"
REVISION = "3c37aedce6d445205671d5714d05ae28b8c90e2c"
SOURCE = Path("dropbear_model/Dropbear/usd/dropbear.usd")
EXPECTED_SHA256 = (
    "ef4434e0adb5a74cb0fe8e779c49aac4ebdcba48998ed519cf17ab16d822e073"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/usd/dropbear.usd"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_file() and digest(output) == EXPECTED_SHA256:
        print(f"verified existing source USD: {output}")
        return

    with tempfile.TemporaryDirectory(prefix="dropbear-usd-") as temporary:
        checkout = Path(temporary) / "dropbear_rl"
        run(
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            REPOSITORY,
            str(checkout),
        )
        run(
            "git",
            "sparse-checkout",
            "set",
            "--no-cone",
            str(SOURCE),
            cwd=checkout,
        )
        run("git", "checkout", REVISION, cwd=checkout)
        source = checkout / SOURCE
        actual = digest(source)
        if actual != EXPECTED_SHA256:
            raise SystemExit(
                f"downloaded USD SHA-256 mismatch: {actual}"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_suffix(".usd.tmp")
        shutil.copyfile(source, temporary_output)
        temporary_output.replace(output)
    print(f"cached verified source USD: {output}")


if __name__ == "__main__":
    main()
