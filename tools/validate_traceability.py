#!/usr/bin/env python3
"""Validate the P0-P1 requirements/design/work/test trace baseline."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AIWG = ROOT / ".aiwg"
REQUIREMENTS = AIWG / "requirements" / "system-requirements.md"
TRACE = AIWG / "requirements" / "traceability-matrix.md"
SOURCES = AIWG / "requirements" / "source-register.md"
TESTS = AIWG / "testing" / "test-catalog.md"
PLAN = AIWG / "planning" / "master-program-plan.md"
ADR_DIR = AIWG / "architecture" / "adr"

REQUIREMENT_RE = re.compile(r"^\| ([A-Z]{2,3}-\d{3}) \|[^|]+\| (.+?) \|", re.MULTILINE)
TRACE_RE = re.compile(r"^\| ([A-Z]{2,3}-\d{3}) \|", re.MULTILINE)
SOURCE_RE = re.compile(r"^\| (SRC-\d{3}) \|", re.MULTILINE)
TEST_RE = re.compile(r"^\| (TST-[A-Z]+-\d{3}) \|", re.MULTILINE)
WP_RE = re.compile(r"^\| WP-(\d{3}) \|", re.MULTILINE)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def fail(message: str) -> None:
    raise ValueError(message)


def unique(values: list[str], label: str) -> set[str]:
    result = set(values)
    if len(result) != len(values):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        fail(f"duplicate {label}: {', '.join(duplicates)}")
    return result


def expand_refs(text: str, prefix_pattern: str) -> set[str]:
    """Expand `PREFIX-001..003,005` references in a table cell/document."""
    prefix_re = re.compile(rf"({prefix_pattern})(\d{{3}})(?:\.\.(\d{{3}}))?")
    refs: set[str] = set()
    for match in prefix_re.finditer(text):
        prefix, start_text, end_text = match.groups()
        start = int(start_text)
        end = int(end_text or start_text)
        if end < start:
            fail(f"descending reference range: {match.group(0)}")
        refs.update(f"{prefix}{number:03d}" for number in range(start, end + 1))
    return refs


def validate_links() -> int:
    checked = 0
    for markdown in AIWG.rglob("*.md"):
        if "ralph" in markdown.parts:
            continue
        text = markdown.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            target = target.split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (markdown.parent / target).resolve()
            if not resolved.exists():
                fail(f"broken relative link in {markdown.relative_to(ROOT)}: {target}")
            checked += 1
    return checked


def main() -> int:
    requirements_text = REQUIREMENTS.read_text(encoding="utf-8")
    trace_text = TRACE.read_text(encoding="utf-8")
    source_text = SOURCES.read_text(encoding="utf-8")
    test_text = TESTS.read_text(encoding="utf-8")
    plan_text = PLAN.read_text(encoding="utf-8")

    requirement_rows = REQUIREMENT_RE.findall(requirements_text)
    requirement_ids = unique([row[0] for row in requirement_rows], "requirements")
    if len(requirement_ids) != 77:
        fail(f"expected 77 requirements; found {len(requirement_ids)}")
    missing_shall = [identifier for identifier, statement in requirement_rows if " shall " not in f" {statement.lower()} "]
    if missing_shall:
        fail(f"requirements without normative shall: {', '.join(missing_shall)}")

    trace_ids = unique(TRACE_RE.findall(trace_text), "trace rows")
    if trace_ids != requirement_ids:
        fail(
            "requirement/trace mismatch: "
            f"missing={sorted(requirement_ids - trace_ids)} "
            f"extra={sorted(trace_ids - requirement_ids)}"
        )

    source_ids = unique(SOURCE_RE.findall(source_text), "sources")
    if len(source_ids) != 20:
        fail(f"expected 20 sources; found {len(source_ids)}")
    referenced_sources = expand_refs(requirements_text, r"SRC-")
    unknown_sources = referenced_sources - source_ids
    if unknown_sources:
        fail(f"unknown requirement source references: {sorted(unknown_sources)}")

    test_ids = unique(TEST_RE.findall(test_text), "tests")
    if len(test_ids) != 140:
        fail(f"expected 140 tests; found {len(test_ids)}")
    referenced_tests = expand_refs(trace_text, r"TST-[A-Z]+-")
    unknown_tests = referenced_tests - test_ids
    if unknown_tests:
        fail(f"unknown trace test references: {sorted(unknown_tests)}")

    work_packages = unique(WP_RE.findall(plan_text), "work packages")
    expected_wps = {f"{number:03d}" for number in range(0, 200, 10)}
    if work_packages != expected_wps:
        fail(
            f"work-package mismatch: missing={sorted(expected_wps - work_packages)} "
            f"extra={sorted(work_packages - expected_wps)}"
        )

    adr_ids = unique(
        [path.name.split("-", 2)[1] for path in ADR_DIR.glob("ADR-*.md")],
        "ADRs",
    )
    expected_adrs = {f"{number:03d}" for number in range(1, 12)}
    if adr_ids != expected_adrs:
        fail(
            f"ADR mismatch: missing={sorted(expected_adrs - adr_ids)} "
            f"extra={sorted(adr_ids - expected_adrs)}"
        )

    links = validate_links()
    print(
        "TRACEABILITY_OK "
        f"requirements={len(requirement_ids)} trace_rows={len(trace_ids)} "
        f"sources={len(source_ids)} adrs={len(adr_ids)} "
        f"work_packages={len(work_packages)} tests={len(test_ids)} links={links}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"traceability validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
