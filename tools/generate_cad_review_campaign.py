#!/usr/bin/env python3
"""Generate the local all-configuration MYACTUATOR CAD review campaign."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/myactuator/catalog.tsv"
INSPECTION = ROOT / "generated/myactuator/cad/step_inspection.json"
LEDGER = ROOT / "assets/myactuator/cad_review.json"
ASSEMBLY = ROOT / "generated/myactuator/cad/review_packet_manifest.json"
FLATTENED = ROOT / "generated/myactuator/cad/flattened_partition_manifest.json"
RUNTIME = ROOT / "generated/myactuator/cad/runtime_asset_registry.json"
SCHEMA = ROOT / "schemas/myactuator-cad-review-campaign.schema.json"
OUTPUT_DIR = ROOT / "generated/myactuator/cad/campaign"
OUTPUT = OUTPUT_DIR / "campaign.json"
INDEX = OUTPUT_DIR / "index.html"
VERSION = "myactuator-cad-review-campaign/1"
SOURCE_FILES = {
    "catalog_sha256": CATALOG,
    "inspection_sha256": INSPECTION,
    "cad_review_ledger_sha256": LEDGER,
    "assembly_packet_manifest_sha256": ASSEMBLY,
    "flattened_partition_manifest_sha256": FLATTENED,
    "runtime_asset_registry_sha256": RUNTIME,
}
QUESTIONS = (
    (
        "CADQ-HOUSING",
        "Which exact occurrences, components or reviewed face partition form the fixed housing?",
        "independent_geometry_review",
    ),
    (
        "CADQ-OUTPUT",
        "Which exact occurrences, components or reviewed face partition form the rotating output?",
        "independent_geometry_review",
    ),
    (
        "CADQ-RESIDUAL",
        "What is the explicit disposition of every source member not assigned to housing or output?",
        "independent_geometry_review",
    ),
    (
        "CADQ-UNIT",
        "What source length unit and exact scale-to-metre transform are evidenced?",
        "independent_geometry_review",
    ),
    (
        "CADQ-FRAME",
        "What rigid source-to-canonical transform is evidenced?",
        "independent_geometry_review",
    ),
    (
        "CADQ-AXIS",
        "What physical output axis is evidenced and in which source frame is it expressed?",
        "independent_geometry_review",
    ),
    (
        "CADQ-ORIGIN",
        "What physical reference plane or feature defines the output-joint origin?",
        "independent_geometry_review",
    ),
    (
        "CADQ-ZERO",
        "What physical assembly pose defines zero output angle?",
        "independent_geometry_review",
    ),
    (
        "CADQ-DIRECTION",
        "What evidence defines positive output rotation and its motor/encoder sign relation?",
        "independent_geometry_review",
    ),
    (
        "CADQ-ARTICULATION",
        "Does the housing remain fixed while only the complete output group articulates over the reviewed range?",
        "independent_geometry_review",
    ),
    (
        "CADQ-MESH",
        "What visual/collision topology, healing and simplification decisions are acceptable?",
        "independent_geometry_review",
    ),
    (
        "CADQ-MASS",
        "What qualified source establishes mass, center of mass and inertia for each link?",
        "qualified_mass_property_source",
    ),
    (
        "CADQ-LICENSE",
        "What license or vendor permission governs local and redistributed derived assets?",
        "license_or_vendor_permission",
    ),
)


class CadReviewCampaignError(ValueError):
    """A campaign source join, semantic rule or output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CadReviewCampaignError(message)


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


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadReviewCampaignError(f"cannot load {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def model_key(series: str, model: str) -> str:
    return "model-" + sha_bytes(
        canonical_bytes({"model": model, "series": series})
    )[:20]


def duplicate_id(step_sha256: str) -> str:
    return "duplicate-" + step_sha256[:20]


def digest_payload(value: dict[str, Any]) -> bytes:
    payload = copy.deepcopy(value)
    payload["integrity"]["record_sha256"] = "0" * 64
    return canonical_bytes(payload)


def set_digest(value: dict[str, Any]) -> None:
    value["integrity"]["record_sha256"] = sha_bytes(digest_payload(value))


def question_catalog() -> list[dict[str, str]]:
    return [
        {
            "question_id": identifier,
            "prompt": prompt,
            "required_evidence_class": evidence,
        }
        for identifier, prompt, evidence in QUESTIONS
    ]


def question_responses() -> list[dict[str, Any]]:
    return [
        {
            "question_id": identifier,
            "state": "unanswered",
            "response": None,
            "evidence_refs": [],
        }
        for identifier, _, _ in QUESTIONS
    ]


def assembly_packet(value: dict[str, Any]) -> dict[str, Any]:
    variant = value["variant_id"]
    base = f"generated/myactuator/cad/review_packets/{variant}"
    return {
        "packet_kind": "assembly_member_packet",
        "packet_json_path": f"{base}/packet.json",
        "packet_json_sha256": value["packet_json_sha256"],
        "overview_path": f"{base}/overview.png",
        "overview_sha256": value["overview_sha256"],
        "sheet_path": f"{base}/member-sheet.png",
        "sheet_sha256": value["member_sheet_sha256"],
        "local_materialization_required": True,
        "redistributable": False,
    }


def flattened_packet(value: dict[str, Any]) -> dict[str, Any]:
    variant = value["variant_id"]
    base = f"generated/myactuator/cad/flattened_review_packets/{variant}"
    return {
        "packet_kind": "flattened_component_packet",
        "packet_json_path": f"{base}/packet.json",
        "packet_json_sha256": value["packet_json_sha256"],
        "overview_path": f"{base}/overview.png",
        "overview_sha256": value["overview_sha256"],
        "sheet_path": f"{base}/largest-component-sheet.png",
        "sheet_sha256": value["largest_component_sheet_sha256"],
        "local_materialization_required": True,
        "redistributable": False,
    }


def flattened_lane(value: dict[str, Any]) -> tuple[str, str, bool]:
    disposition = value["partition_disposition"]
    if value["component_kind"] == "shell":
        return (
            "shell_healing_or_re_source",
            "Obtain a solid/native assembly or submit independently reviewed healing evidence before semantic partition.",
            False,
        )
    if value["component_count"] == 1:
        return (
            "flattened_face_partition_or_re_source",
            "Obtain a native assembly or define and independently review a reproducible face/body partition.",
            False,
        )
    if disposition.startswith("blocked_high_component_count"):
        return (
            "flattened_high_component_partition_or_re_source",
            "Use a specialized component-partition workbench or obtain a better native assembly.",
            False,
        )
    require(
        disposition
        == "candidate_disconnected_solids_manual_partition_required",
        f"{value['variant_id']}: unknown flattened disposition",
    )
    return (
        "flattened_disconnected_component_partition",
        "Independently assign every stable component to housing, output or an explicit residual disposition.",
        True,
    )


def build() -> dict[str, Any]:
    inspection = load_json(INSPECTION)
    ledger = load_json(LEDGER)
    assembly = load_json(ASSEMBLY)
    flattened = load_json(FLATTENED)
    runtime = load_json(RUNTIME)
    require(
        inspection.get("schema_version") == "myactuator-step-inspection/1",
        "inspection version drift",
    )
    require(
        ledger.get("schema_version") == "myactuator-cad-review/2",
        "CAD review ledger version drift",
    )
    require(
        assembly.get("schema_version")
        == "myactuator-cad-review-packet-manifest/1",
        "assembly packet version drift",
    )
    require(
        flattened.get("schema_version")
        == "myactuator-flattened-partition-manifest/1",
        "flattened packet version drift",
    )
    require(
        runtime.get("schema_version")
        == "myactuator-cad-runtime-asset-registry/1",
        "runtime asset registry version drift",
    )
    variants = {
        item["variant_id"]: item for item in inspection["variants"]
    }
    ledger_variants = {
        item["variant_id"]: item for item in ledger["variants"]
    }
    assembly_packets = {
        item["variant_id"]: item for item in assembly["packets"]
    }
    flattened_packets = {
        item["variant_id"]: item for item in flattened["packets"]
    }
    runtime_configs = {
        item["configuration_id"]: item for item in runtime["configurations"]
    }
    require(
        len(variants) == len(ledger_variants) == 53,
        "inspection/ledger variant coverage drift",
    )
    require(
        len(assembly_packets) == 26 and len(flattened_packets) == 27,
        "packet manifest coverage drift",
    )
    duplicate_by_variant: dict[str, str] = {}
    for group in inspection["duplicate_geometry_groups"]:
        identifier = duplicate_id(group["step_sha256"])
        for variant in group["variant_ids"]:
            require(
                variant not in duplicate_by_variant,
                "variant belongs to multiple duplicate groups",
            )
            duplicate_by_variant[variant] = identifier
    require(
        len(inspection["duplicate_geometry_groups"]) == 5
        and len(duplicate_by_variant) == 10,
        "duplicate geometry campaign coverage drift",
    )

    configurations: list[dict[str, Any]] = []
    for config in ledger["geometry_configurations"]:
        require(
            len(config["source_variant_ids"]) == 1,
            f"{config['configuration_id']}: campaign requires one exact source",
        )
        variant_id = config["source_variant_ids"][0]
        source = variants[variant_id]
        review = ledger_variants[variant_id]
        require(
            (config["series"], config["model"])
            == (source["series"], source["model"])
            == (review["series"], review["model"]),
            f"{config['configuration_id']}: source identity drift",
        )
        require(
            config["status"] == "unsupported"
            and config["selector_status"] == "unresolved"
            and review["review_status"] == "unreviewed",
            f"{config['configuration_id']}: campaign baseline promotion",
        )
        runtime_config = runtime_configs.get(config["configuration_id"])
        require(
            runtime_config is not None
            and runtime_config["source_variant_ids"] == [variant_id],
            f"{config['configuration_id']}: runtime configuration join drift",
        )
        reports = runtime_config["candidate_reports"]
        require(len(reports) <= 1, "multiple candidate reports per configuration")
        report_path = reports[0]["report_path"] if reports else None
        report_sha = reports[0]["report_sha256"] if reports else None
        if source["manifest_structure"] == "assembly":
            packet_source = assembly_packets.get(variant_id)
            require(packet_source is not None, f"{variant_id}: assembly packet missing")
            packet = assembly_packet(packet_source)
            candidate = {
                "review_lane": "assembly_member_semantic_review",
                "current_action": (
                    "Independently review every assembly occurrence, then establish unit, frame, axis, origin, zero and direction."
                ),
                "packet_reviewable_now": True,
                "candidate_export_path": report_path,
                "candidate_export_sha256": report_sha,
                "assembly_member_count": packet_source["member_count"],
                "positive_name_candidate_count": len(
                    packet_source["positive_name_candidates"]
                ),
                "flattened_component_kind": None,
                "flattened_component_count": None,
                "partition_disposition": None,
            }
        else:
            packet_source = flattened_packets.get(variant_id)
            require(packet_source is not None, f"{variant_id}: flattened packet missing")
            packet = flattened_packet(packet_source)
            lane, action, reviewable = flattened_lane(packet_source)
            candidate = {
                "review_lane": lane,
                "current_action": action,
                "packet_reviewable_now": reviewable,
                "candidate_export_path": report_path,
                "candidate_export_sha256": report_sha,
                "assembly_member_count": None,
                "positive_name_candidate_count": None,
                "flattened_component_kind": packet_source["component_kind"],
                "flattened_component_count": packet_source["component_count"],
                "partition_disposition": packet_source[
                    "partition_disposition"
                ],
            }
        configurations.append(
            {
                "configuration_id": config["configuration_id"],
                "model_key": model_key(config["series"], config["model"]),
                "series": config["series"],
                "model": config["model"],
                "variant_id": variant_id,
                "step_sha256": source["step_sha256"],
                "source_structure": source["manifest_structure"],
                "source_length_unit_candidate": source[
                    "length_unit_candidate"
                ],
                "duplicate_geometry_group_id": duplicate_by_variant.get(
                    variant_id
                ),
                "review_status": "unreviewed",
                "selector_status": "unresolved",
                "packet_evidence": packet,
                "candidate_state": candidate,
                "question_responses": question_responses(),
                "accepted_asset": False,
                "browser_releasable": False,
                "support_granted": False,
            }
        )
    lanes = Counter(
        item["candidate_state"]["review_lane"] for item in configurations
    )
    value = {
        "schema_version": VERSION,
        "campaign_id": "myactuator-all-exact-configurations-cad-review-v1",
        "authority": "local_review_navigation_and_unanswered_questions_only",
        "sources": {
            name: sha_file(path) for name, path in SOURCE_FILES.items()
        },
        "policy": {
            "local_only": True,
            "packet_ranking_is_not_semantic_selection": True,
            "stable_component_id_is_not_semantic_selection": True,
            "duplicate_bytes_retain_independent_configuration_review": True,
            "shell_is_not_collision_geometry": True,
            "candidate_export_is_not_accepted_geometry": True,
            "all_questions_require_independent_human_evidence": True,
            "redistribution_requires_separate_approval": True,
            "campaign_never_grants_support": True,
        },
        "summary": {
            "model_count": len(
                {(item["series"], item["model"]) for item in configurations}
            ),
            "configuration_count": len(configurations),
            "variant_count": len(
                {item["variant_id"] for item in configurations}
            ),
            "assembly_configuration_count": lanes[
                "assembly_member_semantic_review"
            ],
            "flattened_configuration_count": len(configurations)
            - lanes["assembly_member_semantic_review"],
            "shell_only_configuration_count": lanes[
                "shell_healing_or_re_source"
            ],
            "currently_packet_reviewable_count": sum(
                item["candidate_state"]["packet_reviewable_now"]
                for item in configurations
            ),
            "blocked_re_source_or_specialized_partition_count": sum(
                not item["candidate_state"]["packet_reviewable_now"]
                for item in configurations
            ),
            "candidate_export_available_count": sum(
                item["candidate_state"]["candidate_export_path"] is not None
                for item in configurations
            ),
            "duplicate_geometry_group_count": len(
                inspection["duplicate_geometry_groups"]
            ),
            "duplicate_geometry_configuration_count": len(
                duplicate_by_variant
            ),
            "question_count_per_configuration": len(QUESTIONS),
            "unanswered_question_count": (
                len(configurations) * len(QUESTIONS)
            ),
            "accepted_configuration_count": 0,
            "browser_releasable_configuration_count": 0,
        },
        "question_catalog": question_catalog(),
        "configurations": configurations,
        "accepted_configuration_ids": [],
        "support_granted": False,
        "physical_motion_authority": False,
        "integrity": {"record_sha256": "0" * 64},
    }
    set_digest(value)
    return value


def load_schema() -> dict[str, Any]:
    return load_json(SCHEMA)


def validate(value: dict[str, Any], *, verify_sources: bool = True) -> None:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise CadReviewCampaignError(
            "campaign schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    require(
        value["integrity"]["record_sha256"]
        == sha_bytes(digest_payload(value)),
        "campaign record digest drift",
    )
    if verify_sources:
        for source_id, path in SOURCE_FILES.items():
            require(
                value["sources"][source_id] == sha_file(path),
                f"campaign source changed: {source_id}",
            )
    expected_questions = [item[0] for item in QUESTIONS]
    require(
        [item["question_id"] for item in value["question_catalog"]]
        == expected_questions,
        "campaign question catalog drift",
    )
    configurations = value["configurations"]
    require(
        len({item["configuration_id"] for item in configurations}) == 53
        and len({item["variant_id"] for item in configurations}) == 53,
        "campaign configuration/variant identity drift",
    )
    for item in configurations:
        require(
            item["model_key"] == model_key(item["series"], item["model"]),
            f"{item['configuration_id']}: model key drift",
        )
        require(
            [row["question_id"] for row in item["question_responses"]]
            == expected_questions
            and all(
                row["state"] == "unanswered"
                and row["response"] is None
                and not row["evidence_refs"]
                for row in item["question_responses"]
            ),
            f"{item['configuration_id']}: question promotion/drift",
        )
        for path_key in (
            "packet_json_path",
            "overview_path",
            "sheet_path",
        ):
            path = item["packet_evidence"][path_key]
            require(
                not path.startswith("/")
                and ".." not in Path(path).parts
                and "://" not in path,
                f"{item['configuration_id']}: unsafe/nonlocal packet path",
            )
        candidate = item["candidate_state"]
        require(
            (candidate["candidate_export_path"] is None)
            == (candidate["candidate_export_sha256"] is None),
            f"{item['configuration_id']}: partial candidate export identity",
        )
        if item["source_structure"] == "assembly":
            require(
                candidate["review_lane"]
                == "assembly_member_semantic_review"
                and candidate["assembly_member_count"] is not None
                and candidate["flattened_component_count"] is None,
                f"{item['configuration_id']}: assembly lane drift",
            )
        else:
            require(
                candidate["review_lane"]
                != "assembly_member_semantic_review"
                and candidate["assembly_member_count"] is None
                and candidate["flattened_component_count"] is not None,
                f"{item['configuration_id']}: flattened lane drift",
            )
        require(
            item["review_status"] == "unreviewed"
            and item["selector_status"] == "unresolved"
            and not item["accepted_asset"]
            and not item["browser_releasable"]
            and not item["support_granted"],
            f"{item['configuration_id']}: campaign authority promotion",
        )
    duplicate = [
        item
        for item in configurations
        if item["duplicate_geometry_group_id"] is not None
    ]
    require(
        len(duplicate) == 10
        and len(
            {item["duplicate_geometry_group_id"] for item in duplicate}
        )
        == 5
        and all(
            count == 2
            for count in Counter(
                item["duplicate_geometry_group_id"] for item in duplicate
            ).values()
        ),
        "duplicate geometry independence drift",
    )
    lanes = Counter(
        item["candidate_state"]["review_lane"] for item in configurations
    )
    expected_summary = {
        "model_count": 44,
        "configuration_count": 53,
        "variant_count": 53,
        "assembly_configuration_count": lanes[
            "assembly_member_semantic_review"
        ],
        "flattened_configuration_count": 53
        - lanes["assembly_member_semantic_review"],
        "shell_only_configuration_count": lanes[
            "shell_healing_or_re_source"
        ],
        "currently_packet_reviewable_count": sum(
            item["candidate_state"]["packet_reviewable_now"]
            for item in configurations
        ),
        "blocked_re_source_or_specialized_partition_count": sum(
            not item["candidate_state"]["packet_reviewable_now"]
            for item in configurations
        ),
        "candidate_export_available_count": sum(
            item["candidate_state"]["candidate_export_path"] is not None
            for item in configurations
        ),
        "duplicate_geometry_group_count": 5,
        "duplicate_geometry_configuration_count": 10,
        "question_count_per_configuration": 13,
        "unanswered_question_count": 689,
        "accepted_configuration_count": 0,
        "browser_releasable_configuration_count": 0,
    }
    require(value["summary"] == expected_summary, "campaign summary drift")
    require(
        not value["accepted_configuration_ids"]
        and not value["support_granted"]
        and not value["physical_motion_authority"],
        "campaign authority promotion",
    )


def local_href(repository_path: str) -> str:
    prefix = "generated/myactuator/cad/"
    require(repository_path.startswith(prefix), "non-CAD campaign path")
    return "../" + repository_path.removeprefix(prefix)


def render_index(value: dict[str, Any]) -> str:
    rows: list[str] = []
    for item in value["configurations"]:
        packet = item["packet_evidence"]
        candidate = item["candidate_state"]
        group = item["duplicate_geometry_group_id"] or "unique"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(item['configuration_id'])}</code></td>"
            f"<td>{html.escape(item['series'])}</td>"
            f"<td>{html.escape(item['model'])}</td>"
            f"<td><code>{html.escape(item['variant_id'])}</code></td>"
            f"<td>{html.escape(item['source_structure'])}</td>"
            f"<td>{html.escape(candidate['review_lane'])}</td>"
            f"<td>{'packet review' if candidate['packet_reviewable_now'] else 'blocked/specialized'}</td>"
            f"<td><a href='{html.escape(local_href(packet['overview_path']))}'>overview</a> "
            f"<a href='{html.escape(local_href(packet['sheet_path']))}'>sheet</a> "
            f"<a href='{html.escape(local_href(packet['packet_json_path']))}'>packet JSON</a></td>"
            f"<td><code>{html.escape(group)}</code></td>"
            f"<td>{len(item['question_responses'])} unanswered</td>"
            f"<td>{html.escape(candidate['current_action'])}</td>"
            "</tr>"
        )
    summary = html.escape(json.dumps(value["summary"], indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MYACTUATOR all-configuration CAD review campaign</title>
<style>
body {{ font: 14px/1.4 system-ui,sans-serif; margin: 24px; color: #18212b; }}
.hold {{ border: 2px solid #9a6700; background: #fff8c5; padding: 12px; max-width: 1100px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
th,td {{ border: 1px solid #c7ced6; padding: 5px; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #eef2f6; }}
code,pre {{ background: #eef2f6; }} pre {{ padding: 10px; width: max-content; }}
</style>
</head>
<body>
<h1>MYACTUATOR CAD semantic-review campaign</h1>
<div class="hold"><strong>Local navigation only.</strong> All 53 configurations remain unreviewed and unsupported. Names, component IDs, packets, candidate exports and this index grant no geometry, simulator, motor or redistribution authority. Each configuration has 13 unanswered questions requiring independent evidence.</div>
<h2>Exact campaign summary</h2>
<pre>{summary}</pre>
<p><a href="campaign.json">Canonical campaign JSON</a></p>
<table>
<thead><tr><th>Configuration</th><th>Series</th><th>Model</th><th>Source</th><th>Structure</th><th>Lane</th><th>Readiness</th><th>Local evidence</th><th>Duplicate group</th><th>Questions</th><th>Next action</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body>
</html>
"""


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
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build()
    validate(value)
    json_content = canonical_bytes(value)
    html_content = render_index(value).encode("utf-8")
    if args.check:
        require(OUTPUT.read_bytes() == json_content, "campaign JSON is stale")
        require(INDEX.read_bytes() == html_content, "campaign index is stale")
    else:
        atomic_write(OUTPUT, json_content)
        atomic_write(INDEX, html_content)
    summary = value["summary"]
    print(
        "CAD_REVIEW_CAMPAIGN_OK "
        f"configs={summary['configuration_count']} "
        f"assembly={summary['assembly_configuration_count']} "
        f"flattened={summary['flattened_configuration_count']} "
        f"reviewable={summary['currently_packet_reviewable_count']} "
        f"blocked={summary['blocked_re_source_or_specialized_partition_count']} "
        f"questions={summary['unanswered_question_count']} accepted=0 support=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError, CadReviewCampaignError) as error:
        print(f"CAD review campaign failed: {error}", file=os.sys.stderr)
        raise SystemExit(1)
