from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from integrations.gr00t_wbc.embodiment import ACTION_NAMES
from integrations.gr00t_wbc.motion_reference import (
    MotionReferenceError,
    convert_policy,
    main,
    validate_reference,
    write_csv_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "web/assets/rl/dropbear-walk-reference.json"


@pytest.fixture(scope="module")
def converted():
    return convert_policy(json.loads(SOURCE.read_text()), source_name=str(SOURCE))


def test_checked_in_walk_converts_to_exact_50_hz_reference(converted):
    assert converted["schema"] == "dropbear-sonic-motion-reference-v1"
    assert converted["sampleRateHz"] == 50
    assert tuple(converted["jointOrder"]) == ACTION_NAMES
    assert converted["frameCount"] == len(converted["frames"])
    assert converted["frameCount"] == 399
    assert converted["frames"][0]["timeSec"] == 0.0
    assert converted["frames"][1]["timeSec"] == 0.02
    assert converted["frames"][-1]["timeSec"] == 7.96

    report = validate_reference(converted, project_root=ROOT)
    assert report["valid"] is True
    assert report["sampleRateHz"] == 50
    assert report["frameCount"] == 399
    assert report["maximumReducedClosureResidualM"] < 1e-8
    assert report["fullPassiveProjectionAuthority"] == "Isaac/PhysX"


def test_conversion_interpolates_the_25_hz_source(converted):
    source = json.loads(SOURCE.read_text())
    first = source["frames"][0]["q"][0]
    second = source["frames"][1]["q"][0]
    expected_midpoint = (first + second) / 2.0
    assert converted["frames"][1]["jointPositionRad"][0] == pytest.approx(
        expected_midpoint
    )


def test_csv_bundle_has_22_motor_columns_and_matching_frames(converted, tmp_path):
    write_csv_bundle(converted, tmp_path)
    expected = {
        "joint_pos.csv",
        "joint_vel.csv",
        "body_pos.csv",
        "body_quat.csv",
        "metadata.txt",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    with (tmp_path / "joint_pos.csv").open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == [f"joint_{index}" for index in range(22)]
    assert len(rows) == converted["frameCount"] + 1
    assert len(rows[1]) == 22
    with (tmp_path / "body_pos.csv").open(newline="") as stream:
        body_rows = list(csv.reader(stream))
    assert body_rows[0] == ["body_0_x", "body_0_y", "body_0_z"]
    metadata = (tmp_path / "metadata.txt").read_text(encoding="utf-8")
    assert "Body part indexes:\n[0]" in metadata
    assert f"Total timesteps: {converted['frameCount']}" in metadata


def test_validator_rejects_order_timeline_and_knee_lock_drift(converted):
    bad = json.loads(json.dumps(converted))
    bad["jointOrder"][0], bad["jointOrder"][1] = (
        bad["jointOrder"][1],
        bad["jointOrder"][0],
    )
    with pytest.raises(MotionReferenceError, match="jointOrder"):
        validate_reference(bad, project_root=ROOT)

    bad = json.loads(json.dumps(converted))
    bad["frames"][1]["timeSec"] = 0.021
    with pytest.raises(MotionReferenceError, match="50 Hz timeline"):
        validate_reference(bad, project_root=ROOT)

    bad = json.loads(json.dumps(converted))
    bad["frames"][3]["jointPositionRad"][4] = -0.01
    with pytest.raises(ValueError, match="left_knee"):
        validate_reference(bad, project_root=ROOT)


def test_cli_converts_writes_csv_and_validates(tmp_path):
    output = tmp_path / "reference.json"
    csv_dir = tmp_path / "csv"
    assert main(
        [
            "convert",
            "--input",
            str(SOURCE),
            "--output",
            str(output),
            "--csv-dir",
            str(csv_dir),
        ]
    ) == 0
    assert output.is_file()
    assert (csv_dir / "joint_pos.csv").is_file()
    assert main(["validate", "--input", str(output)]) == 0


def test_cli_returns_nonzero_for_incompatible_input(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "wrong"}))
    output = tmp_path / "reference.json"
    assert main(
        ["convert", "--input", str(bad), "--output", str(output)]
    ) == 2
    assert not output.exists()


def test_reference_json_schema_is_well_formed():
    schema = json.loads(
        (
            ROOT
            / "integrations/gr00t_wbc/schemas/"
            "dropbear-sonic-motion-reference-v1.schema.json"
        ).read_text()
    )
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["properties"]["sampleRateHz"]["const"] == 50
    assert schema["$defs"]["number22"]["minItems"] == 22
    assert schema["$defs"]["number22"]["maxItems"] == 22
