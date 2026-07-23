#!/usr/bin/env python3
"""Generate the source-bound exact-tuple protocol applicability registry."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.protocol_applicability_decision import (  # noqa: E402
    ProtocolApplicabilityDecisionError,
    load_directory as load_decision_directory,
    validate as validate_applicability_decision,
)


CATALOG = ROOT / "assets/myactuator/catalog.tsv"
DOCUMENTS = ROOT / "assets/myactuator/documents.tsv"
ARCHIVES = ROOT / "assets/myactuator/document_archives.tsv"
FILES = ROOT / "assets/myactuator/document_files.tsv"
SOURCE_CLAIMS = (
    ROOT / "assets/myactuator/protocol_applicability/source_claims.tsv"
)
DECISION_DIRECTORY = (
    ROOT / "assets/myactuator/protocol_applicability/decisions"
)
SCHEMA = (
    ROOT / "schemas/myactuator-protocol-applicability-registry.schema.json"
)
OUTPUT = (
    ROOT / "generated/myactuator/protocol_applicability/registry.json"
)
VERSION = "myactuator-protocol-applicability-registry/2"
SOURCE_FILES = {
    "catalog_sha256": CATALOG,
    "documents_sha256": DOCUMENTS,
    "document_archives_sha256": ARCHIVES,
    "document_files_sha256": FILES,
    "source_claims_sha256": SOURCE_CLAIMS,
}
PROTOCOL_SCOPES = {"motor_motion_protocol", "fieldbus_protocol"}
EXPECTED_SCOPE_COUNTS = {
    "drive_manual": 3,
    "fieldbus_protocol": 3,
    "motor_motion_protocol": 7,
    "product_manual": 15,
    "sensor_interface": 3,
    "setup_manual": 1,
}


class ProtocolApplicabilityRegistryError(ValueError):
    """A source join, claim boundary or generated registry is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolApplicabilityRegistryError(message)


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


def stable_id(prefix: str, value: dict[str, str]) -> str:
    return prefix + sha_bytes(canonical_bytes(value))[:20]


def model_key(series: str, model: str) -> str:
    return stable_id("model-", {"model": model, "series": series})


def package_id(series: str, document_set: str, revision: str) -> str:
    return stable_id(
        "docpkg-",
        {
            "document_set": document_set,
            "package_revision": revision,
            "series": series,
        },
    )


def occurrence_id(row: dict[str, str]) -> str:
    return stable_id(
        "dococc-",
        {
            "document_set": row["document_set"],
            "file_sha256": row["file_sha256"],
            "series": row["series"],
            "vendor_relative_path": row["vendor_relative_path"],
        },
    )


def load_tsv(
    path: Path,
    columns: list[str],
    *,
    expected_rows: int | None = None,
) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            require(reader.fieldnames == columns, f"{path}: columns drift")
            rows = list(reader)
    except OSError as error:
        raise ProtocolApplicabilityRegistryError(
            f"cannot load {path}: {error}"
        ) from error
    if expected_rows is not None:
        require(
            len(rows) == expected_rows,
            f"{path}: expected {expected_rows} rows, found {len(rows)}",
        )
    require(
        all(
            value == value.strip() and "\n" not in value and "\r" not in value
            for row in rows
            for value in row.values()
        ),
        f"{path}: non-canonical field whitespace",
    )
    return rows


def load_inputs() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, dict[str, str]],
]:
    catalog = load_tsv(
        CATALOG,
        ["series", "model", "package_revision", "archive_url"],
        expected_rows=44,
    )
    documents = load_tsv(
        DOCUMENTS,
        ["series", "document_set", "package_revision", "archive_url"],
        expected_rows=9,
    )
    archives = load_tsv(
        ARCHIVES,
        [
            "series",
            "document_set",
            "package_revision",
            "archive_filename",
            "archive_sha256",
            "archive_url",
        ],
        expected_rows=9,
    )
    files = load_tsv(
        FILES,
        [
            "series",
            "document_set",
            "vendor_relative_path",
            "file_sha256",
            "bytes",
        ],
        expected_rows=32,
    )
    claim_rows = load_tsv(
        SOURCE_CLAIMS,
        [
            "file_sha256",
            "document_scope",
            "title",
            "revision",
            "applicable_driver",
            "transports",
            "command_scope",
            "claim_locator",
            "evidence_state",
        ],
        expected_rows=6,
    )
    claims = {row["file_sha256"]: row for row in claim_rows}
    require(len(claims) == len(claim_rows), "source claim hash is not unique")
    require(
        all(len(value) == 64 for value in claims),
        "source claim contains invalid SHA-256",
    )
    require(
        len({(row["series"], row["model"]) for row in catalog}) == 44,
        "catalog model identity is not unique",
    )
    return catalog, documents, archives, files, claims


def classify_file(
    row: dict[str, str],
    claims: dict[str, dict[str, str]],
) -> dict[str, Any]:
    source = claims.get(row["file_sha256"])
    name = Path(row["vendor_relative_path"]).name
    if source is not None:
        claim = {
            "document_scope": source["document_scope"],
            "title": source["title"],
            "revision": source["revision"] or None,
            "applicable_driver": source["applicable_driver"] or None,
            "transports": (
                source["transports"].split("|")
                if source["transports"]
                else []
            ),
            "command_scope": source["command_scope"],
            "claim_locator": source["claim_locator"],
            "evidence_state": source["evidence_state"],
            "human_reviewed": False,
            "applicability_authority": False,
        }
    elif name == "MC Series Brushless Servo Driver Manual-240611.pdf":
        claim = {
            "document_scope": "drive_manual",
            "title": name.removesuffix(".pdf"),
            "revision": None,
            "applicable_driver": None,
            "transports": [],
            "command_scope": "drive_configuration",
            "claim_locator": "vendor filename",
            "evidence_state": "source_filename_unreviewed",
            "human_reviewed": False,
            "applicability_authority": False,
        }
    elif name == "Setup Software InstructionManual-V3-241125.pdf":
        claim = {
            "document_scope": "setup_manual",
            "title": name.removesuffix(".pdf"),
            "revision": None,
            "applicable_driver": None,
            "transports": [],
            "command_scope": "setup_software",
            "claim_locator": "vendor filename",
            "evidence_state": "source_filename_unreviewed",
            "human_reviewed": False,
            "applicability_authority": False,
        }
    else:
        require(
            "manual" in name.casefold(),
            f"{row['vendor_relative_path']}: unclassified document",
        )
        require(
            "interface manual" not in name.casefold()
            and "protocol" not in name.casefold(),
            f"{row['vendor_relative_path']}: scoped source claim missing",
        )
        claim = {
            "document_scope": "product_manual",
            "title": name.removesuffix(".pdf"),
            "revision": None,
            "applicable_driver": None,
            "transports": [],
            "command_scope": "product_characteristics",
            "claim_locator": "vendor filename",
            "evidence_state": "source_filename_unreviewed",
            "human_reviewed": False,
            "applicability_authority": False,
        }
    require(
        claim["document_scope"] not in PROTOCOL_SCOPES
        or bool(claim["transports"]),
        f"{name}: protocol source has no transport claim",
    )
    require(
        claim["document_scope"] != "sensor_interface"
        or claim["command_scope"] == "sensor_electrical_interface",
        f"{name}: sensor interface scope promotion",
    )
    return claim


def candidate_document_sets(series: str, model: str) -> list[str]:
    if series == "RMD-X":
        require(model.startswith("X"), f"{series}/{model}: model prefix drift")
        return [
            "X-V2-protocol-manual",
            "X-V3-protocol-manual",
            "X-V4-protocol-manual",
        ]
    if series == "RH":
        require(model.startswith("RH-"), f"{series}/{model}: model prefix drift")
        return ["RH-dual-encoder-V4.4"]
    if series == "RMD-L":
        require(model.startswith("L-"), f"{series}/{model}: model prefix drift")
        return ["L-V3-protocol-manual"]
    if series == "CEM":
        require(model.startswith("CEM-"), f"{series}/{model}: model prefix drift")
        return ["CEM-protocol-manual"]
    if series == "RMD-H":
        require(model.startswith("H-"), f"{series}/{model}: model prefix drift")
        return ["H-S3-protocol-manual"]
    if series == "FL-FLO" and model.startswith("FL-"):
        return ["FL-user-manual"]
    if series == "FL-FLO" and model.startswith("FLO-"):
        return ["FLO-user-manual"]
    raise ProtocolApplicabilityRegistryError(
        f"{series}/{model}: no exact candidate document-set rule"
    )


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def build() -> dict[str, Any]:
    catalog, documents, archives, files, claims = load_inputs()
    document_by_key = {
        (row["series"], row["document_set"]): row for row in documents
    }
    archive_by_key = {
        (row["series"], row["document_set"]): row for row in archives
    }
    require(
        len(document_by_key) == 9 and len(archive_by_key) == 9,
        "document package identity is not unique",
    )
    require(
        set(document_by_key) == set(archive_by_key),
        "document/archive package join is not exact",
    )
    for key, document in document_by_key.items():
        archive = archive_by_key[key]
        require(
            document["package_revision"] == archive["package_revision"]
            and document["archive_url"] == archive["archive_url"],
            f"{key}: document/archive provenance drift",
        )

    package_ids = {
        key: package_id(
            key[0],
            key[1],
            document_by_key[key]["package_revision"],
        )
        for key in document_by_key
    }
    occurrence_rows: list[dict[str, Any]] = []
    files_by_package: dict[tuple[str, str], list[dict[str, Any]]] = {
        key: [] for key in document_by_key
    }
    for row in files:
        key = (row["series"], row["document_set"])
        require(key in document_by_key, f"{key}: file has no document package")
        value = {
            "occurrence_id": occurrence_id(row),
            "package_id": package_ids[key],
            "series": row["series"],
            "document_set": row["document_set"],
            "vendor_relative_path": row["vendor_relative_path"],
            "file_name": Path(row["vendor_relative_path"]).name,
            "file_sha256": row["file_sha256"],
            "bytes": int(row["bytes"]),
            "source_claim": classify_file(row, claims),
        }
        occurrence_rows.append(value)
        files_by_package[key].append(value)
    require(
        len({row["occurrence_id"] for row in occurrence_rows}) == 32,
        "document occurrence identity is not unique",
    )
    require(
        set(claims) <= {row["file_sha256"] for row in occurrence_rows},
        "source claim references an absent document",
    )

    package_by_set = {
        key[1]: package_ids[key] for key in document_by_key
    }
    require(
        len(package_by_set) == 9,
        "document_set is not globally unique",
    )
    model_rows: list[dict[str, Any]] = []
    for row in catalog:
        candidate_sets = candidate_document_sets(row["series"], row["model"])
        candidate_packages = [package_by_set[value] for value in candidate_sets]
        candidate_protocols = [
            file["occurrence_id"]
            for document_set in candidate_sets
            for file in files_by_package[(row["series"], document_set)]
            if file["source_claim"]["document_scope"] in PROTOCOL_SCOPES
        ]
        blockers = [
            "exact_hardware_revision_missing",
            "exact_drive_firmware_missing",
            "independent_applicability_decision_missing",
        ]
        if not candidate_protocols:
            blockers.append("candidate_motor_control_protocol_source_missing")
        model_rows.append(
            {
                "model_key": model_key(row["series"], row["model"]),
                "series": row["series"],
                "model": row["model"],
                "package_revision": row["package_revision"],
                "candidate_package_ids": candidate_packages,
                "candidate_protocol_occurrence_ids": candidate_protocols,
                "applicability_status": "unsupported",
                "accepted_decision_ids": [],
                "support_granted": False,
                "blockers": blockers,
            }
        )
    models_by_key = {row["model_key"]: row for row in model_rows}
    require(len(models_by_key) == 44, "model key is not unique")

    package_rows: list[dict[str, Any]] = []
    for key, document in document_by_key.items():
        archive = archive_by_key[key]
        identifier = package_ids[key]
        package_rows.append(
            {
                "package_id": identifier,
                "series": key[0],
                "document_set": key[1],
                "package_revision": document["package_revision"],
                "archive_filename": archive["archive_filename"],
                "archive_sha256": archive["archive_sha256"],
                "file_occurrence_ids": [
                    row["occurrence_id"] for row in files_by_package[key]
                ],
                "candidate_model_keys": [
                    row["model_key"]
                    for row in model_rows
                    if identifier in row["candidate_package_ids"]
                ],
                "applicability_authority": False,
            }
        )

    scopes = Counter(
        row["source_claim"]["document_scope"] for row in occurrence_rows
    )
    packages_by_id = {
        row["package_id"]: row for row in package_rows
    }
    try:
        submitted_decisions, decision_hashes = load_decision_directory(
            DECISION_DIRECTORY,
            models_by_key,
            {row["occurrence_id"]: row for row in occurrence_rows},
            packages_by_id,
        )
    except ProtocolApplicabilityDecisionError as error:
        raise ProtocolApplicabilityRegistryError(str(error)) from error
    accepted_decisions = sorted(
        (
            decision
            for decision in submitted_decisions
            if decision["review"]["status"] == "accepted"
        ),
        key=lambda decision: decision["decision_id"],
    )
    accepted_by_model: dict[str, list[dict[str, Any]]] = {}
    for decision in accepted_decisions:
        accepted_by_model.setdefault(
            decision["subject"]["model_key"], []
        ).append(decision)
    for model in model_rows:
        accepted = accepted_by_model.get(model["model_key"], [])
        if accepted:
            model["applicability_status"] = "accepted"
            model["accepted_decision_ids"] = [
                decision["decision_id"] for decision in accepted
            ]
            model["blockers"] = [
                "applicability_is_exact_tuple_scoped",
                "complete_motor_support_not_granted",
                "physical_motion_authority_not_granted",
            ]
    value = {
        "schema_version": VERSION,
        "artifact_id": "myactuator-protocol-applicability-registry",
        "authority": "source_index_and_reviewed_exact_tuple_applicability_only",
        "sources": {
            **{
                name: sha_file(path)
                for name, path in SOURCE_FILES.items()
            },
            "decision_file_sha256": decision_hashes,
        },
        "policy": {
            "package_placement_is_candidate_only": True,
            "filename_or_extraction_is_not_applicability": True,
            "duplicate_bytes_retain_occurrence_provenance": True,
            "sensor_interface_is_not_motor_motion_protocol": True,
            "exact_model_hardware_firmware_protocol_transport_mode_required": True,
            "no_family_generation_or_latest_fallback": True,
            "human_review_required_for_acceptance": True,
            "source_drift_revokes": True,
            "applicability_never_grants_motor_support": True,
        },
        "summary": {
            "model_count": len(model_rows),
            "document_package_count": len(package_rows),
            "document_file_occurrence_count": len(occurrence_rows),
            "unique_document_file_count": len(
                {row["file_sha256"] for row in occurrence_rows}
            ),
            "candidate_model_package_relationship_count": sum(
                len(row["candidate_package_ids"]) for row in model_rows
            ),
            "candidate_model_protocol_relationship_count": sum(
                len(row["candidate_protocol_occurrence_ids"])
                for row in model_rows
            ),
            "source_claim_scope_counts": dict(sorted(scopes.items())),
            "accepted_applicability_count": len(accepted_decisions),
            "accepted_model_count": len(accepted_by_model),
            "supported_model_count": 0,
        },
        "document_packages": package_rows,
        "document_file_occurrences": occurrence_rows,
        "models": model_rows,
        "accepted_applicability_decisions": accepted_decisions,
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    return value


def load_schema() -> dict[str, Any]:
    try:
        value = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProtocolApplicabilityRegistryError(
            f"cannot load schema: {error}"
        ) from error
    require(isinstance(value, dict), "schema root must be an object")
    return value


def validate(
    value: dict[str, Any],
    *,
    verify_sources: bool = True,
    decision_directory: Path | None = DECISION_DIRECTORY,
) -> None:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise ProtocolApplicabilityRegistryError(
            "schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "registry record digest drift",
    )
    if verify_sources:
        for source_id, path in SOURCE_FILES.items():
            require(
                value["sources"][source_id] == sha_file(path),
                f"registry source changed: {source_id}",
            )

    packages = {
        row["package_id"]: row for row in value["document_packages"]
    }
    occurrences = {
        row["occurrence_id"]: row
        for row in value["document_file_occurrences"]
    }
    models = {row["model_key"]: row for row in value["models"]}
    require(
        len(packages) == 9 and len(occurrences) == 32 and len(models) == 44,
        "registry identity/count drift",
    )
    listed_occurrences = [
        occurrence
        for package in packages.values()
        for occurrence in package["file_occurrence_ids"]
    ]
    require(
        len(listed_occurrences) == 32
        and len(set(listed_occurrences)) == 32
        and set(listed_occurrences) == set(occurrences),
        "document files are not partitioned by package exactly once",
    )
    for occurrence in occurrences.values():
        package = packages[occurrence["package_id"]]
        require(
            (occurrence["series"], occurrence["document_set"])
            == (package["series"], package["document_set"]),
            f"{occurrence['occurrence_id']}: package identity mismatch",
        )
        claim = occurrence["source_claim"]
        require(
            not claim["human_reviewed"]
            and not claim["applicability_authority"],
            f"{occurrence['occurrence_id']}: source claim promotion",
        )
        require(
            claim["document_scope"] != "sensor_interface"
            or claim["command_scope"] == "sensor_electrical_interface",
            f"{occurrence['occurrence_id']}: sensor scope promotion",
        )

    for model in models.values():
        require(
            model["model_key"] == model_key(model["series"], model["model"]),
            f"{model['model_key']}: model identity digest drift",
        )
        candidate_packages = set(model["candidate_package_ids"])
        require(
            all(
                model["model_key"] in packages[identifier]["candidate_model_keys"]
                for identifier in candidate_packages
            ),
            f"{model['model_key']}: package/model relation is not symmetric",
        )
        expected_sets = candidate_document_sets(
            model["series"], model["model"]
        )
        require(
            [packages[identifier]["document_set"] for identifier in model["candidate_package_ids"]]
            == expected_sets,
            f"{model['model_key']}: candidate package selection drift",
        )
        for identifier in model["candidate_protocol_occurrence_ids"]:
            occurrence = occurrences[identifier]
            require(
                occurrence["package_id"] in candidate_packages
                and occurrence["source_claim"]["document_scope"]
                in PROTOCOL_SCOPES,
                f"{model['model_key']}: non-protocol/cross-package candidate",
            )
        require(
            not model["support_granted"],
            f"{model['model_key']}: model support promotion",
        )
    for package in packages.values():
        require(
            len(package["candidate_model_keys"])
            == len(set(package["candidate_model_keys"]))
            and all(
                package["package_id"]
                in models[identifier]["candidate_package_ids"]
                for identifier in package["candidate_model_keys"]
            ),
            f"{package['package_id']}: model/package relation is not symmetric",
        )

    embedded_decisions = value["accepted_applicability_decisions"]
    decision_ids = [decision["decision_id"] for decision in embedded_decisions]
    require(
        len(decision_ids) == len(set(decision_ids)),
        "accepted applicability decision identity is not unique",
    )
    accepted_by_model: dict[str, list[str]] = {}
    for decision in embedded_decisions:
        subject = decision.get("subject", {})
        model = models.get(subject.get("model_key"))
        occurrence = occurrences.get(subject.get("protocol_occurrence_id"))
        package = packages.get(subject.get("package_id"))
        require(model is not None, "accepted decision model is absent")
        require(occurrence is not None, "accepted decision source is absent")
        require(package is not None, "accepted decision package is absent")
        try:
            validate_applicability_decision(
                decision,
                model,
                occurrence,
                package,
            )
        except ProtocolApplicabilityDecisionError as error:
            raise ProtocolApplicabilityRegistryError(str(error)) from error
        require(
            decision["record_state"] == "submitted"
            and decision["review"]["status"] == "accepted"
            and decision["applicability_established"],
            "registry embeds a non-accepted decision",
        )
        accepted_by_model.setdefault(
            subject["model_key"], []
        ).append(decision["decision_id"])
    for model in models.values():
        identifiers = sorted(accepted_by_model.get(model["model_key"], []))
        require(
            model["accepted_decision_ids"] == identifiers,
            f"{model['model_key']}: accepted decision projection drift",
        )
        if identifiers:
            require(
                model["applicability_status"] == "accepted"
                and model["blockers"]
                == [
                    "applicability_is_exact_tuple_scoped",
                    "complete_motor_support_not_granted",
                    "physical_motion_authority_not_granted",
                ],
                f"{model['model_key']}: accepted applicability state drift",
            )
        else:
            expected_blockers = [
                "exact_hardware_revision_missing",
                "exact_drive_firmware_missing",
                "independent_applicability_decision_missing",
            ]
            if not model["candidate_protocol_occurrence_ids"]:
                expected_blockers.append(
                    "candidate_motor_control_protocol_source_missing"
                )
            require(
                model["applicability_status"] == "unsupported"
                and model["blockers"] == expected_blockers,
                f"{model['model_key']}: unsupported applicability state drift",
            )

    if verify_sources and decision_directory is not None:
        try:
            submitted, decision_hashes = load_decision_directory(
                decision_directory,
                models,
                occurrences,
                packages,
            )
        except ProtocolApplicabilityDecisionError as error:
            raise ProtocolApplicabilityRegistryError(str(error)) from error
        accepted = sorted(
            (
                decision
                for decision in submitted
                if decision["review"]["status"] == "accepted"
            ),
            key=lambda decision: decision["decision_id"],
        )
        require(
            value["sources"]["decision_file_sha256"] == decision_hashes,
            "applicability decision file hash drift",
        )
        require(
            embedded_decisions == accepted,
            "accepted applicability decision directory projection drift",
        )

    summary = value["summary"]
    scopes = Counter(
        row["source_claim"]["document_scope"]
        for row in occurrences.values()
    )
    require(dict(sorted(scopes.items())) == EXPECTED_SCOPE_COUNTS, "source scope partition drift")
    expected = {
        "model_count": len(models),
        "document_package_count": len(packages),
        "document_file_occurrence_count": len(occurrences),
        "unique_document_file_count": len(
            {row["file_sha256"] for row in occurrences.values()}
        ),
        "candidate_model_package_relationship_count": sum(
            len(row["candidate_package_ids"]) for row in models.values()
        ),
        "candidate_model_protocol_relationship_count": sum(
            len(row["candidate_protocol_occurrence_ids"])
            for row in models.values()
        ),
        "source_claim_scope_counts": dict(sorted(scopes.items())),
        "accepted_applicability_count": len(embedded_decisions),
        "accepted_model_count": len(accepted_by_model),
        "supported_model_count": 0,
    }
    require(summary == expected, "registry summary drift")
    require(
        not value["support_granted"]
        and not value["physical_motion_authority"],
        "registry authority promotion",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the tracked generated registry is current",
    )
    args = parser.parse_args()
    value = build()
    validate(value)
    content = canonical_bytes(value)
    if args.check:
        try:
            tracked = OUTPUT.read_bytes()
        except OSError as error:
            raise ProtocolApplicabilityRegistryError(
                f"cannot read generated registry: {error}"
            ) from error
        require(tracked == content, "generated applicability registry is stale")
    else:
        atomic_write(OUTPUT, content)
    print(
        "protocol applicability registry: "
        f"{value['summary']['model_count']} models, "
        f"{value['summary']['document_package_count']} packages, "
        f"{value['summary']['document_file_occurrence_count']} PDF occurrences, "
        f"{value['summary']['accepted_applicability_count']} accepted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
