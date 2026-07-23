#!/usr/bin/env python3
"""Build or verify the tracked MYACTUATOR source-asset evidence manifests.

The vendor cache is intentionally ignored.  These manifests retain the exact
archive and extracted STEP identities without asserting redistribution rights,
geometry correctness, or simulation readiness.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "myactuator"
VENDOR = ROOT / "assets" / "vendor" / "myactuator"
CATALOG = ASSETS / "catalog.tsv"
ARCHIVES = ASSETS / "source_archives.tsv"
STEPS = ASSETS / "step_manifest.tsv"
DOCUMENT_CATALOG = ASSETS / "documents.tsv"
DOCUMENT_ARCHIVES = ASSETS / "document_archives.tsv"
DOCUMENT_FILES = ASSETS / "document_files.tsv"

EXPECTED_MODELS = 44
EXPECTED_STEPS = 53
EXPECTED_ASSEMBLIES = 26
EXPECTED_FLATTENED = 27
EXPECTED_DOCUMENT_SETS = 9
EXPECTED_PDFS = 32


@dataclass(frozen=True)
class CatalogRow:
    series: str
    model: str
    revision: str
    url: str


@dataclass(frozen=True)
class DocumentRow:
    series: str
    document_set: str
    revision: str
    url: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def catalog() -> list[CatalogRow]:
    rows = read_tsv(CATALOG)
    required = {"series", "model", "package_revision", "archive_url"}
    if not rows or set(rows[0]) != required:
        raise ValueError(f"{CATALOG}: expected columns {sorted(required)}")
    result = [
        CatalogRow(
            row["series"], row["model"], row["package_revision"], row["archive_url"]
        )
        for row in rows
    ]
    keys = {(row.series, row.model) for row in result}
    if len(result) != EXPECTED_MODELS or len(keys) != EXPECTED_MODELS:
        raise ValueError(
            f"catalog must contain {EXPECTED_MODELS} unique series/model rows; "
            f"found {len(result)} rows and {len(keys)} unique keys"
        )
    return result


def document_catalog() -> list[DocumentRow]:
    rows = read_tsv(DOCUMENT_CATALOG)
    required = {"series", "document_set", "package_revision", "archive_url"}
    if not rows or set(rows[0]) != required:
        raise ValueError(f"{DOCUMENT_CATALOG}: expected columns {sorted(required)}")
    result = [
        DocumentRow(
            row["series"],
            row["document_set"],
            row["package_revision"],
            row["archive_url"],
        )
        for row in rows
    ]
    keys = {(row.series, row.document_set) for row in result}
    if len(result) != EXPECTED_DOCUMENT_SETS or len(keys) != EXPECTED_DOCUMENT_SETS:
        raise ValueError(
            f"document catalog must contain {EXPECTED_DOCUMENT_SETS} unique rows; "
            f"found {len(result)} rows and {len(keys)} unique keys"
        )
    return result


def build_from_cache(rows: list[CatalogRow]) -> tuple[list[list[str]], list[list[str]]]:
    archive_rows: list[list[str]] = []
    step_rows: list[list[str]] = []

    for row in rows:
        model_dir = VENDOR / row.series / row.model
        digest_record = model_dir / "source.zip.sha256"
        url_record = model_dir / "source.url"
        if not digest_record.is_file() or not url_record.is_file():
            raise ValueError(f"missing source evidence for {row.series}/{row.model}")
        if url_record.read_text(encoding="utf-8").strip() != row.url:
            raise ValueError(f"source URL mismatch for {row.series}/{row.model}")

        fields = digest_record.read_text(encoding="utf-8").strip().split(maxsplit=1)
        if len(fields) != 2 or len(fields[0]) != 64:
            raise ValueError(f"invalid archive digest record: {digest_record}")
        digest, filename = fields
        archive_path = VENDOR / ".downloads" / filename
        if not archive_path.is_file():
            raise ValueError(f"missing cached archive: {archive_path}")
        if sha256(archive_path) != digest:
            raise ValueError(f"archive digest mismatch: {archive_path}")
        archive_rows.append(
            [row.series, row.model, row.revision, filename, digest, row.url]
        )

        vendor_dir = model_dir / "vendor"
        motor_steps = sorted(
            (
                path
                for path in vendor_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".step", ".stp"}
            ),
            key=lambda path: path.as_posix(),
        )
        if not motor_steps:
            raise ValueError(f"no STEP source for {row.series}/{row.model}")
        for path in motor_steps:
            data = path.read_bytes()
            structure = (
                "assembly"
                if b"NEXT_ASSEMBLY_USAGE_OCCURRENCE" in data
                else "flattened"
            )
            step_rows.append(
                [
                    row.series,
                    row.model,
                    path.relative_to(VENDOR).as_posix(),
                    hashlib.sha256(data).hexdigest(),
                    str(len(data)),
                    structure,
                    "unreviewed",
                    "not_separately_named",
                    "unreviewed",
                    "license_review_required",
                ]
            )

    return archive_rows, step_rows


def build_documents_from_cache(
    rows: list[DocumentRow],
) -> tuple[list[list[str]], list[list[str]]]:
    root = VENDOR / "docs"
    archive_rows: list[list[str]] = []
    file_rows: list[list[str]] = []
    for row in rows:
        document_dir = root / row.series / row.document_set
        digest_record = document_dir / "source.zip.sha256"
        url_record = document_dir / "source.url"
        if not digest_record.is_file() or not url_record.is_file():
            raise ValueError(f"missing document evidence for {row.series}/{row.document_set}")
        if url_record.read_text(encoding="utf-8").strip() != row.url:
            raise ValueError(f"document URL mismatch for {row.series}/{row.document_set}")
        fields = digest_record.read_text(encoding="utf-8").strip().split(maxsplit=1)
        if len(fields) != 2 or len(fields[0]) != 64:
            raise ValueError(f"invalid document archive digest record: {digest_record}")
        digest, filename = fields
        archive_path = root / ".downloads" / filename
        if not archive_path.is_file() or sha256(archive_path) != digest:
            raise ValueError(f"document archive digest mismatch: {archive_path}")
        archive_rows.append(
            [row.series, row.document_set, row.revision, filename, digest, row.url]
        )
        pdfs = sorted(
            (path for path in (document_dir / "vendor").rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"),
            key=lambda path: path.as_posix(),
        )
        if not pdfs:
            raise ValueError(f"no PDF source for {row.series}/{row.document_set}")
        for path in pdfs:
            file_rows.append(
                [
                    row.series,
                    row.document_set,
                    path.relative_to(root).as_posix(),
                    sha256(path),
                    str(path.stat().st_size),
                ]
            )
    return archive_rows, file_rows


def render_tsv(header: list[str], rows: list[list[str]]) -> str:
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in rows)
    return "\n".join(lines) + "\n"


def validate_tracked(rows: list[CatalogRow]) -> None:
    archive_rows = read_tsv(ARCHIVES)
    step_rows = read_tsv(STEPS)
    catalog_keys = {(row.series, row.model) for row in rows}

    archive_keys = {(row["series"], row["model"]) for row in archive_rows}
    if len(archive_rows) != EXPECTED_MODELS or archive_keys != catalog_keys:
        raise ValueError("archive manifest is not a one-to-one map of the 44-model catalog")
    if any(len(row["archive_sha256"]) != 64 for row in archive_rows):
        raise ValueError("archive manifest contains an invalid SHA-256")

    if len(step_rows) != EXPECTED_STEPS:
        raise ValueError(
            f"STEP manifest must contain {EXPECTED_STEPS} rows; found {len(step_rows)}"
        )
    step_keys = {(row["series"], row["model"]) for row in step_rows}
    if step_keys != catalog_keys:
        raise ValueError("STEP manifest does not cover every catalog model")
    paths = [row["vendor_relative_path"] for row in step_rows]
    if len(paths) != len(set(paths)):
        raise ValueError("STEP manifest contains duplicate paths")
    if any(len(row["step_sha256"]) != 64 for row in step_rows):
        raise ValueError("STEP manifest contains an invalid SHA-256")
    structures = {name: 0 for name in ("assembly", "flattened")}
    for row in step_rows:
        if row["step_structure"] not in structures:
            raise ValueError(f"invalid STEP structure: {row['step_structure']}")
        structures[row["step_structure"]] += 1
        if row["simulation_review"] != "unreviewed":
            raise ValueError("P0-P1 must not imply that STEP simulation review is complete")
        if row["output_member"] != "not_separately_named":
            raise ValueError("vendor packages do not identify a separate output member")
    expected = {
        "assembly": EXPECTED_ASSEMBLIES,
        "flattened": EXPECTED_FLATTENED,
    }
    if structures != expected:
        raise ValueError(f"STEP structure counts {structures}; expected {expected}")


def validate_tracked_documents(rows: list[DocumentRow]) -> None:
    archive_rows = read_tsv(DOCUMENT_ARCHIVES)
    file_rows = read_tsv(DOCUMENT_FILES)
    expected_keys = {(row.series, row.document_set) for row in rows}
    archive_keys = {(row["series"], row["document_set"]) for row in archive_rows}
    if len(archive_rows) != EXPECTED_DOCUMENT_SETS or archive_keys != expected_keys:
        raise ValueError("document archive manifest is not a one-to-one catalog map")
    if any(len(row["archive_sha256"]) != 64 for row in archive_rows):
        raise ValueError("document archive manifest contains an invalid SHA-256")
    if len(file_rows) != EXPECTED_PDFS:
        raise ValueError(
            f"document file manifest must contain {EXPECTED_PDFS} PDFs; found {len(file_rows)}"
        )
    file_keys = {(row["series"], row["document_set"]) for row in file_rows}
    if file_keys != expected_keys:
        raise ValueError("document file manifest does not cover every document set")
    paths = [row["vendor_relative_path"] for row in file_rows]
    if len(paths) != len(set(paths)):
        raise ValueError("document file manifest contains duplicate paths")
    if any(len(row["file_sha256"]) != 64 for row in file_rows):
        raise ValueError("document file manifest contains an invalid SHA-256")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="replace tracked manifests from the cache"
    )
    parser.add_argument(
        "--require-cache",
        action="store_true",
        help="fail instead of validating only tracked evidence when cache is absent",
    )
    args = parser.parse_args()
    rows = catalog()
    document_rows = document_catalog()

    cache_present = (VENDOR / ".downloads").is_dir()
    if args.write or cache_present:
        generated_archives, generated_steps = build_from_cache(rows)
        generated_document_archives, generated_document_files = build_documents_from_cache(
            document_rows
        )
        archive_text = render_tsv(
            [
                "series",
                "model",
                "package_revision",
                "archive_filename",
                "archive_sha256",
                "archive_url",
            ],
            generated_archives,
        )
        step_text = render_tsv(
            [
                "series",
                "model",
                "vendor_relative_path",
                "step_sha256",
                "bytes",
                "step_structure",
                "simulation_review",
                "output_member",
                "axis_origin_units_review",
                "redistribution_status",
            ],
            generated_steps,
        )
        document_archive_text = render_tsv(
            [
                "series",
                "document_set",
                "package_revision",
                "archive_filename",
                "archive_sha256",
                "archive_url",
            ],
            generated_document_archives,
        )
        document_file_text = render_tsv(
            [
                "series",
                "document_set",
                "vendor_relative_path",
                "file_sha256",
                "bytes",
            ],
            generated_document_files,
        )
        if args.write:
            ARCHIVES.write_text(archive_text, encoding="utf-8")
            STEPS.write_text(step_text, encoding="utf-8")
            DOCUMENT_ARCHIVES.write_text(document_archive_text, encoding="utf-8")
            DOCUMENT_FILES.write_text(document_file_text, encoding="utf-8")
        else:
            if ARCHIVES.read_text(encoding="utf-8") != archive_text:
                raise ValueError("tracked archive manifest differs from the vendor cache")
            if STEPS.read_text(encoding="utf-8") != step_text:
                raise ValueError("tracked STEP manifest differs from the vendor cache")
            if DOCUMENT_ARCHIVES.read_text(encoding="utf-8") != document_archive_text:
                raise ValueError("tracked document archive manifest differs from the cache")
            if DOCUMENT_FILES.read_text(encoding="utf-8") != document_file_text:
                raise ValueError("tracked document file manifest differs from the cache")
    elif args.require_cache:
        raise ValueError(f"vendor cache is required but absent: {VENDOR}")

    validate_tracked(rows)
    validate_tracked_documents(document_rows)
    cache_state = "cache verified" if cache_present else "tracked evidence only"
    print(
        "ASSET_MANIFEST_OK "
        f"models={EXPECTED_MODELS} steps={EXPECTED_STEPS} "
        f"assemblies={EXPECTED_ASSEMBLIES} flattened={EXPECTED_FLATTENED} "
        f"document_sets={EXPECTED_DOCUMENT_SETS} pdfs={EXPECTED_PDFS} "
        f"({cache_state})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as error:
        print(f"asset manifest validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
