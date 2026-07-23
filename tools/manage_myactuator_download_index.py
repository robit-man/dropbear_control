#!/usr/bin/env python3
"""Probe and pin the MYACTUATOR vendor download-index URL set.

The online modes only observe navigation links. They never download archives,
change the catalog, or grant protocol, CAD, plant, motor, or motion authority.
The default mode validates the tracked snapshot completely offline.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
DOCUMENTS = ROOT / "assets/myactuator/documents.tsv"
SNAPSHOT = ROOT / "assets/myactuator/download_index_snapshot.json"
SCHEMA = ROOT / "schemas/myactuator-download-index-snapshot.schema.json"
VERSION = "myactuator-download-index-snapshot/1"
PAGE_SPECS = (
    ("RMD-X", "https://www.myactuator.com/downloads-xseries"),
    ("RH", "https://www.myactuator.com/downloads-rhseries"),
    ("RMD-L", "https://www.myactuator.com/downloads-lseries"),
    (
        "CEM",
        "https://www.myactuator.com/%E5%89%AF%E6%9C%AC-downloads-hm-series",
    ),
    ("RMD-H", "https://www.myactuator.com/downloads-hseries"),
    ("FL-FLO", "https://www.myactuator.com/downloads-flseries"),
)
ARCHIVE_URL_RE = re.compile(
    r"https://www\.myactuator\.com/_files/archives/"
    r'[^"<>\s]+?\.zip(?:\?dn=[^"<>\s]*)?'
)
OBSERVED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)


class DownloadIndexError(ValueError):
    """The vendor index, source join, or snapshot is not admissible."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DownloadIndexError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def normalize_archive_url(value: str) -> str:
    value = html.unescape(value).replace("\\u0026", "&").replace("\\/", "/")
    return value.rstrip("\\")


def extract_archive_urls(body: bytes) -> list[str]:
    text = body.decode("utf-8", "replace")
    return sorted(
        {normalize_archive_url(value) for value in ARCHIVE_URL_RE.findall(text)}
    )


def default_fetch(page_url: str) -> bytes:
    request = urllib.request.Request(
        page_url,
        headers={"User-Agent": "MYACTUATOR-source-index-audit/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            require(
                response.status == 200,
                f"{page_url}: HTTP status {response.status}",
            )
            return response.read()
    except (OSError, urllib.error.URLError) as error:
        raise DownloadIndexError(f"{page_url}: fetch failed: {error}") from error


def load_tsv(path: Path, identity: str) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except OSError as error:
        raise DownloadIndexError(f"cannot read {path}: {error}") from error
    require(
        rows
        and "series" in rows[0]
        and "archive_url" in rows[0]
        and identity in rows[0],
        f"{path}: source columns drift",
    )
    require(
        all(
            value == value.strip() and "\n" not in value and "\r" not in value
            for row in rows
            for value in row.values()
        ),
        f"{path}: non-canonical source whitespace",
    )
    return rows


def tracked_sources() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    dict[tuple[str, str], tuple[str, str]],
]:
    catalog = load_tsv(CATALOG, "model")
    documents = load_tsv(DOCUMENTS, "document_set")
    require(len(catalog) == 44, "catalog row count drift")
    require(len(documents) == 9, "document row count drift")
    joined: dict[tuple[str, str], tuple[str, str]] = {}
    for kind, identity, rows in (
        ("cad", "model", catalog),
        ("document", "document_set", documents),
    ):
        for row in rows:
            key = (row["series"], row["archive_url"])
            require(key not in joined, f"duplicate tracked archive URL: {key}")
            joined[key] = (kind, row[identity])
    require(len(joined) == 53, "tracked archive URL count drift")
    return catalog, documents, joined


def fetch_pages(
    fetcher: Callable[[str], bytes] = default_fetch,
) -> list[dict[str, Any]]:
    pages = []
    for series, page_url in PAGE_SPECS:
        urls = extract_archive_urls(fetcher(page_url))
        require(urls, f"{series}: vendor page contains no archive links")
        pages.append(
            {
                "page_id": stable_id(
                    "downloadpage-",
                    {"page_url": page_url, "series": series},
                ),
                "series": series,
                "page_url": page_url,
                "archive_url_set_sha256": sha_bytes(canonical_bytes(urls)),
                "archive_urls": urls,
            }
        )
    return pages


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def build_snapshot(
    observed_at_utc: str,
    fetcher: Callable[[str], bytes] = default_fetch,
) -> dict[str, Any]:
    require(
        bool(OBSERVED_AT_RE.fullmatch(observed_at_utc)),
        "observed_at_utc must be canonical UTC seconds",
    )
    catalog, documents, tracked = tracked_sources()
    pages = fetch_pages(fetcher)
    live_pairs = [
        (page["series"], url)
        for page in pages
        for url in page["archive_urls"]
    ]
    require(
        len(live_pairs) == len(set(live_pairs)),
        "an archive URL appears more than once in the live index",
    )
    live = set(live_pairs)
    expected = set(tracked)
    live_only = sorted(live - expected)
    tracked_only = sorted(expected - live)
    if live_only or tracked_only:
        details = {
            "live_only": live_only,
            "tracked_only": tracked_only,
        }
        raise DownloadIndexError(
            "vendor download index drift; change control required: "
            + json.dumps(details, ensure_ascii=False, sort_keys=True)
        )
    identity = [
        {
            "archive_urls": page["archive_urls"],
            "page_url": page["page_url"],
            "series": page["series"],
        }
        for page in pages
    ]
    value = {
        "schema_version": VERSION,
        "snapshot_id": stable_id("downloadindex-", identity),
        "observed_at_utc": observed_at_utc,
        "authority": "vendor_download_navigation_and_drift_evidence_only",
        "sources": {
            "catalog_sha256": sha_file(CATALOG),
            "documents_sha256": sha_file(DOCUMENTS),
        },
        "pages": pages,
        "summary": {
            "page_count": len(pages),
            "archive_url_count": len(live),
            "cad_archive_url_count": len(catalog),
            "document_archive_url_count": len(documents),
            "live_only_url_count": 0,
            "tracked_only_url_count": 0,
            "tracked_exact_match": True,
        },
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    validate(value)
    return value


def load_schema() -> dict[str, Any]:
    try:
        value = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DownloadIndexError(f"cannot load snapshot schema: {error}") from error
    require(isinstance(value, dict), "snapshot schema root must be an object")
    return value


def validate(value: dict[str, Any], *, verify_sources: bool = True) -> None:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise DownloadIndexError(
            "schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "snapshot record digest drift",
    )
    require(
        [(page["series"], page["page_url"]) for page in value["pages"]]
        == list(PAGE_SPECS),
        "download page identity/order drift",
    )
    for page in value["pages"]:
        require(
            page["archive_urls"] == sorted(set(page["archive_urls"])),
            f"{page['series']}: archive URL order/uniqueness drift",
        )
        require(
            page["archive_url_set_sha256"]
            == sha_bytes(canonical_bytes(page["archive_urls"])),
            f"{page['series']}: archive URL set digest drift",
        )
        require(
            page["page_id"]
            == stable_id(
                "downloadpage-",
                {"page_url": page["page_url"], "series": page["series"]},
            ),
            f"{page['series']}: page identity digest drift",
        )
    identity = [
        {
            "archive_urls": page["archive_urls"],
            "page_url": page["page_url"],
            "series": page["series"],
        }
        for page in value["pages"]
    ]
    require(
        value["snapshot_id"] == stable_id("downloadindex-", identity),
        "snapshot identity digest drift",
    )
    _, _, tracked = tracked_sources()
    observed = [
        (page["series"], url)
        for page in value["pages"]
        for url in page["archive_urls"]
    ]
    require(
        len(observed) == 53
        and len(set(observed)) == 53
        and set(observed) == set(tracked),
        "snapshot does not exactly partition the tracked source URLs",
    )
    expected_summary = {
        "page_count": 6,
        "archive_url_count": 53,
        "cad_archive_url_count": 44,
        "document_archive_url_count": 9,
        "live_only_url_count": 0,
        "tracked_only_url_count": 0,
        "tracked_exact_match": True,
    }
    require(value["summary"] == expected_summary, "snapshot summary drift")
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "download navigation evidence promoted authority",
    )
    if verify_sources:
        require(
            value["sources"]
            == {
                "catalog_sha256": sha_file(CATALOG),
                "documents_sha256": sha_file(DOCUMENTS),
            },
            "snapshot source digest drift",
        )


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def refresh(
    output: Path,
    observed_at_utc: str,
    fetcher: Callable[[str], bytes] = default_fetch,
) -> dict[str, Any]:
    value = build_snapshot(observed_at_utc, fetcher)
    atomic_write(output, canonical_bytes(value))
    return value


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DownloadIndexError(f"cannot load snapshot: {error}") from error
    require(isinstance(value, dict), "snapshot root must be an object")
    return value


def current_utc_seconds() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--probe",
        action="store_true",
        help="fetch live pages and compare without writing",
    )
    mode.add_argument(
        "--refresh",
        action="store_true",
        help="fetch live pages and atomically replace an exact-match snapshot",
    )
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    parser.add_argument("--observed-at-utc", default=None)
    args = parser.parse_args()
    try:
        if args.probe or args.refresh:
            observed = args.observed_at_utc or current_utc_seconds()
            if args.refresh:
                value = refresh(args.output, observed)
            else:
                value = build_snapshot(observed)
            print(
                "MYACTUATOR_DOWNLOAD_INDEX_LIVE_OK "
                f"snapshot={value['snapshot_id']} "
                f"pages={value['summary']['page_count']} "
                f"archives={value['summary']['archive_url_count']} "
                f"cad={value['summary']['cad_archive_url_count']} "
                f"documents={value['summary']['document_archive_url_count']} "
                "support=0 physical=0"
            )
            return 0
        value = load_snapshot(args.output)
        validate(value)
        print(
            "MYACTUATOR_DOWNLOAD_INDEX_OFFLINE_OK "
            f"snapshot={value['snapshot_id']} "
            f"observed={value['observed_at_utc']} "
            f"pages={value['summary']['page_count']} "
            f"archives={value['summary']['archive_url_count']} "
            "support=0 physical=0"
        )
        return 0
    except DownloadIndexError as error:
        print(f"MYACTUATOR_DOWNLOAD_INDEX_ERROR {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
