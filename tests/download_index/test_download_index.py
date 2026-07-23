from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/manage_myactuator_download_index.py"
SNAPSHOT = ROOT / "assets/myactuator/download_index_snapshot.json"
SCHEMA = ROOT / "schemas/myactuator-download-index-snapshot.schema.json"

spec = importlib.util.spec_from_file_location(
    "download_index_manager_test_module", TOOL
)
assert spec is not None and spec.loader is not None
manager = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = manager
spec.loader.exec_module(manager)


class DownloadIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        _, _, tracked = manager.tracked_sources()
        cls.tracked = tracked

    def fake_fetcher(self, drift: str | None = None):
        by_series: dict[str, list[str]] = {
            series: [] for series, _ in manager.PAGE_SPECS
        }
        for series, url in self.tracked:
            by_series[series].append(url)
        if drift == "missing":
            by_series["RMD-X"].pop()
        elif drift == "extra":
            by_series["RMD-X"].append(
                "https://www.myactuator.com/_files/archives/"
                "cab28a_deadbeef.zip?dn=untracked.zip"
            )
        page_series = dict(manager.PAGE_SPECS)
        by_url = {url: series for series, url in manager.PAGE_SPECS}

        def fetch(page_url: str) -> bytes:
            self.assertIn(page_url, by_url)
            series = by_url[page_url]
            body = "\n".join(
                f'<a href="{url.replace("&", "\\\\u0026")}">download</a>'
                for url in by_series[series]
            )
            return body.encode()

        self.assertEqual(set(page_series), set(by_series))
        return fetch

    def test_snapshot_is_schema_valid_exact_and_denial_only(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.value)
        manager.validate(copy.deepcopy(self.value))
        self.assertEqual(
            {
                "archive_url_count": 53,
                "cad_archive_url_count": 44,
                "document_archive_url_count": 9,
                "live_only_url_count": 0,
                "page_count": 6,
                "tracked_exact_match": True,
                "tracked_only_url_count": 0,
            },
            self.value["summary"],
        )
        self.assertFalse(self.value["support_granted"])
        self.assertFalse(self.value["physical_motion_authority"])

    def test_snapshot_exactly_partitions_all_tracked_urls(self) -> None:
        observed = [
            (page["series"], url)
            for page in self.value["pages"]
            for url in page["archive_urls"]
        ]
        self.assertEqual(53, len(observed))
        self.assertEqual(53, len(set(observed)))
        self.assertEqual(set(self.tracked), set(observed))

    def test_offline_rebuild_with_exact_fake_pages_matches_identity(self) -> None:
        rebuilt = manager.build_snapshot(
            "2026-07-23T00:00:01Z",
            self.fake_fetcher(),
        )
        self.assertEqual(self.value["snapshot_id"], rebuilt["snapshot_id"])
        self.assertEqual(self.value["pages"], rebuilt["pages"])
        self.assertNotEqual(
            self.value["integrity"]["record_sha256"],
            rebuilt["integrity"]["record_sha256"],
        )

    def test_live_missing_or_extra_link_requires_change_control(self) -> None:
        for drift in ("missing", "extra"):
            with self.subTest(drift=drift), self.assertRaises(
                manager.DownloadIndexError
            ) as caught:
                manager.build_snapshot(
                    "2026-07-23T00:00:00Z",
                    self.fake_fetcher(drift),
                )
            self.assertIn("change control required", str(caught.exception))

    def test_failed_refresh_preserves_last_valid_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "snapshot.json"
            output.write_bytes(b"last-valid\n")
            with self.assertRaises(manager.DownloadIndexError):
                manager.refresh(
                    output,
                    "2026-07-23T00:00:00Z",
                    self.fake_fetcher("missing"),
                )
            self.assertEqual(b"last-valid\n", output.read_bytes())

    def test_digest_page_set_source_and_authority_mutations_fail(self) -> None:
        mutations = []
        digest = copy.deepcopy(self.value)
        digest["integrity"]["record_sha256"] = "0" * 64
        mutations.append(digest)
        page_set = copy.deepcopy(self.value)
        page_set["pages"][0]["archive_urls"].pop()
        manager.set_digest(page_set)
        mutations.append(page_set)
        source = copy.deepcopy(self.value)
        source["sources"]["catalog_sha256"] = "0" * 64
        manager.set_digest(source)
        mutations.append(source)
        authority = copy.deepcopy(self.value)
        authority["support_granted"] = True
        manager.set_digest(authority)
        mutations.append(authority)
        unexpected = copy.deepcopy(self.value)
        unexpected["unexpected"] = True
        manager.set_digest(unexpected)
        mutations.append(unexpected)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(
                manager.DownloadIndexError
            ):
                manager.validate(value)


if __name__ == "__main__":
    unittest.main()
