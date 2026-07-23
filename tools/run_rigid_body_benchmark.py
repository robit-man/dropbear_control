#!/usr/bin/env python3
"""Run the exact, headless generic rigid-body benchmark.

The fixture validates simulator machinery only.  It is intentionally unrelated
to a MYACTUATOR product or the Dropbear mechanism, and its report structurally
retains zero exact-model, physical, support, and motion authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))

from myactuator_lib.simulation_runtime import (  # noqa: E402
    SimulationAdmissionReason,
    SimulationRuntimeCatalog,
    SimulationSelection,
    SimulationUseCase,
)
from myactuator_lib.trace_interchange import (  # noqa: E402
    build_trace,
    canonical_json,
    chain_events,
    validate_trace,
)


LOCK_PATH = ROOT / "tools/rigid-body-engine-lock.json"
LOCK_SCHEMA = ROOT / "schemas/rigid-body-engine-lock.schema.json"
REPORT_SCHEMA = ROOT / "schemas/rigid-body-benchmark-report.schema.json"
FIXTURE_PATH = ROOT / "tests/rigid_body_benchmark/generic_fixture.xml"
DEFAULT_OUTPUT_DIR = ROOT / "generated/myactuator/rigid_body_benchmark"
TRACE_NAME = "trace.json"
REPORT_NAME = "report.json"
ZERO_SHA256 = "0" * 64

STEP_COUNT = 2500
TICK_PERIOD_NS = 1_000_000
SAMPLE_PERIOD_TICKS = 10
JOINT_RESPONSE_MINIMUM_RAD = 0.1
CONTACT_PENETRATION_MAXIMUM_M = 0.01
SETTLED_PENETRATION_MAXIMUM_M = 0.0001
CLOSED_CHAIN_RESIDUAL_MAXIMUM_M = 0.00001
CLOSED_CHAIN_RESPONSE_MINIMUM_RAD = 0.000001

COMMANDS = (
    (0, (0.05, 0.05, -0.05)),
    (800, (-0.03, -0.035, 0.035)),
    (1600, (0.0, 0.0, 0.0)),
)
JOINTS = (
    ("generic-drive-joint", "drive_joint"),
    ("generic-loop-joint-a", "joint_a"),
    ("generic-loop-joint-b", "joint_b"),
)


class RigidBodyBenchmarkError(RuntimeError):
    """The lock, fixture, benchmark, report, or tracked output is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RigidBodyBenchmarkError(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def digest(value: Mapping[str, Any], integrity_key: str = "integrity") -> str:
    payload = copy.deepcopy(dict(value))
    payload[integrity_key]["record_sha256"] = ZERO_SHA256
    return sha256(canonical(payload))


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RigidBodyBenchmarkError(f"cannot read {path}: {error}") from error
    require(isinstance(value, dict), f"{path}: root must be an object")
    return value


def validate_schema(value: Mapping[str, Any], schema_path: Path, label: str) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise RigidBodyBenchmarkError(
            f"{label} schema failure at "
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )


def _binary_path(artifact: str) -> Path:
    package_dir = Path(mujoco.__file__).resolve().parent
    if artifact == "libmujoco-linux-x86-64":
        candidates = tuple(package_dir.glob("libmujoco.so.*"))
    elif artifact == "mujoco-python-structs-cpython-312-linux-x86-64":
        candidates = tuple(package_dir.glob("_structs*.so"))
    elif artifact == "numpy-multiarray-umath-cpython-312-linux-x86-64":
        candidates = (Path(np.core._multiarray_umath.__file__).resolve(),)
    else:
        raise RigidBodyBenchmarkError(f"unknown locked artifact: {artifact}")
    require(len(candidates) == 1, f"{artifact}: expected one installed artifact")
    return candidates[0]


def load_engine_lock(path: Path = LOCK_PATH) -> dict[str, Any]:
    value = read_json(path)
    validate_schema(value, LOCK_SCHEMA, "engine lock")
    require(
        value["integrity"]["record_sha256"] == digest(value),
        "engine lock record digest mismatch",
    )
    libc_name, libc_version = platform.libc_ver()
    actual_platform = {
        "system": platform.system(),
        "machine": platform.machine(),
        "python_implementation": platform.python_implementation(),
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "libc_name": libc_name,
        "libc_version": libc_version,
    }
    require(
        value["platform"] == actual_platform,
        f"platform differs from exact engine lock: {actual_platform}",
    )
    engine = value["executed_engine"]
    require(
        importlib.metadata.version(engine["package"]) == engine["version"],
        "MuJoCo package version differs from engine lock",
    )
    require(mujoco.__version__ == engine["version"], "MuJoCo API version drift")
    for binary in engine["binaries"]:
        path_value = _binary_path(binary["artifact"])
        require(path_value.stat().st_size == binary["size_bytes"], "engine binary size drift")
        require(
            sha256(path_value.read_bytes()) == binary["sha256"],
            "engine binary hash drift",
        )
    for dependency in value["dependencies"]:
        require(
            importlib.metadata.version(dependency["package"])
            == dependency["version"],
            "benchmark dependency version drift",
        )
        binary = dependency["binary"]
        path_value = _binary_path(binary["artifact"])
        require(
            path_value.stat().st_size == binary["size_bytes"],
            "dependency binary size drift",
        )
        require(
            sha256(path_value.read_bytes()) == binary["sha256"],
            "dependency binary hash drift",
        )
    executed = [
        candidate
        for candidate in value["candidates"]
        if candidate["benchmark_status"] == "executed_generic_fixture"
    ]
    require(
        len(executed) == 1
        and executed[0]["candidate_id"] == engine["engine_id"]
        and executed[0]["availability"] == "installed_exact",
        "engine lock executed-candidate identity drift",
    )
    require(
        all(not claim for claim in value["claims"].values()),
        "engine lock contains an authority promotion",
    )
    return value


def _state_digest(data: mujoco.MjData) -> str:
    return sha256(
        canonical(
            {
                "time_s": float(data.time),
                "qpos": [float(value) for value in data.qpos],
                "qvel": [float(value) for value in data.qvel],
                "ctrl": [float(value) for value in data.ctrl],
            }
        )
    )


def _command_payload(
    sequence: int,
    tick: int,
    actuator_id: str,
    target_nm: float,
) -> dict[str, Any]:
    return {
        "command": {
            "sequence": sequence,
            "issued_tick": tick,
            "deadline_tick": tick + 801,
            "actuator_id": actuator_id,
            "mode": "joint_effort",
            "target_si": target_nm,
            "target_unit": "Nm",
            "maximum_absolute_target_si": 1.0,
        }
    }


def _joint_state(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    actuator_id: str,
    joint_name: str,
    tick: int,
) -> dict[str, Any]:
    joint_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, joint_name
    )
    require(joint_id >= 0, f"fixture joint missing: {joint_name}")
    qpos_address = int(model.jnt_qposadr[joint_id])
    dof_address = int(model.jnt_dofadr[joint_id])
    return {
        "state": {
            "sample_tick": tick,
            "actuator_id": actuator_id,
            "position_rad": float(data.qpos[qpos_address]),
            "velocity_rad_s": float(data.qvel[dof_address]),
            "effort_nm": float(data.qfrc_actuator[dof_address]),
            "qaxis_current_a": None,
            "temperature_k": None,
            "validity": "valid",
            "source": "mujoco-locked-engine",
            "fault_code": "no-fault",
            "provenance_refs": (
                "fixture:generic-rigid-body-fixture-v1",
                "engine-lock:generic-rigid-body-benchmark-linux-x86-64",
                f"joint:{joint_name}",
            ),
        }
    }


def run_once(lock: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture_bytes = FIXTURE_PATH.read_bytes()
    fixture_sha = sha256(fixture_bytes)
    runner_sha = sha256(Path(__file__).read_bytes())
    model = mujoco.MjModel.from_xml_path(str(FIXTURE_PATH))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    require(model.nv == 9, "fixture DOF count drift")
    require(model.nu == 3, "fixture actuator count drift")
    require(model.neq == 1, "fixture equality constraint count drift")
    require(
        abs(float(model.opt.timestep) - TICK_PERIOD_NS / 1e9) <= 1e-15,
        "fixture time step drift",
    )

    initial_sha = _state_digest(data)
    records: list[tuple[int, str, Mapping[str, Any]]] = [
        (
            0,
            "configured",
            {
                "fixture_id": "generic-rigid-body-fixture-v1",
                "fixture_sha256": fixture_sha,
                "engine_lock_id": lock["lock_id"],
                "engine_lock_sha256": sha256(LOCK_PATH.read_bytes()),
                "seed": 0,
                "reset_generation": 1,
                "initial_state_sha256": initial_sha,
            },
        )
    ]
    for actuator_id, joint_name in JOINTS:
        records.append(
            (
                0,
                "joint-state-read",
                _joint_state(model, data, actuator_id, joint_name, 0),
            )
        )
    command_sequence = 1
    for control_index, (actuator_id, _joint_name) in enumerate(JOINTS):
        records.append(
            (
                0,
                "command-accepted",
                _command_payload(
                    command_sequence,
                    0,
                    actuator_id,
                    COMMANDS[0][1][control_index],
                ),
            )
        )
        command_sequence += 1
    data.ctrl[:] = COMMANDS[0][1]

    drive_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "drive_joint"
    )
    drive_qpos = int(model.jnt_qposadr[drive_id])
    loop_qpos = tuple(
        int(
            model.jnt_qposadr[
                mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, joint_name
                )
            ]
        )
        for joint_name in ("joint_a", "joint_b")
    )
    drop_body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "drop_body"
    )
    require(drop_body_id >= 0, "fixture drop body missing")

    maximum_drive_response = 0.0
    maximum_loop_response = 0.0
    minimum_contact_distance = math.inf
    settled_minimum_contact_distance = math.inf
    maximum_equality_residual = 0.0
    contact_observed = False
    all_state_finite = True
    command_index = 1

    for tick in range(1, STEP_COUNT + 1):
        if command_index < len(COMMANDS) and tick == COMMANDS[command_index][0] + 1:
            command_tick, targets = COMMANDS[command_index]
            for control_index, (actuator_id, _joint_name) in enumerate(JOINTS):
                records.append(
                    (
                        command_tick,
                        "command-accepted",
                        _command_payload(
                            command_sequence,
                            command_tick,
                            actuator_id,
                            targets[control_index],
                        ),
                    )
                )
                command_sequence += 1
            data.ctrl[:] = targets
            command_index += 1
        mujoco.mj_step(model, data)
        maximum_drive_response = max(
            maximum_drive_response, abs(float(data.qpos[drive_qpos]))
        )
        maximum_loop_response = max(
            maximum_loop_response,
            *(abs(float(data.qpos[address])) for address in loop_qpos),
        )
        finite_arrays = (
            data.qpos,
            data.qvel,
            data.qacc,
            data.ctrl,
            data.qfrc_actuator,
        )
        all_state_finite = all_state_finite and all(
            bool(np.isfinite(array).all()) for array in finite_arrays
        )
        equality_mask = data.efc_type == int(
            mujoco.mjtConstraint.mjCNSTR_EQUALITY
        )
        if bool(np.any(equality_mask)):
            maximum_equality_residual = max(
                maximum_equality_residual,
                float(np.max(np.abs(data.efc_pos[equality_mask]))),
            )
        for contact_index in range(data.ncon):
            contact_observed = True
            distance = float(data.contact[contact_index].dist)
            minimum_contact_distance = min(minimum_contact_distance, distance)
            if tick >= 2000:
                settled_minimum_contact_distance = min(
                    settled_minimum_contact_distance, distance
                )
        if tick % SAMPLE_PERIOD_TICKS == 0:
            for actuator_id, joint_name in JOINTS:
                records.append(
                    (
                        tick,
                        "joint-state-read",
                        _joint_state(
                            model, data, actuator_id, joint_name, tick
                        ),
                    )
                )

    final_height = float(data.xpos[drop_body_id, 2])
    metrics = {
        "steps": STEP_COUNT,
        "final_simulation_time_s": float(data.time),
        "maximum_drive_joint_response_rad": maximum_drive_response,
        "all_state_finite": all_state_finite,
        "contact_observed": contact_observed,
        "minimum_contact_distance_m": minimum_contact_distance,
        "settled_minimum_contact_distance_m": settled_minimum_contact_distance,
        "final_drop_body_height_m": final_height,
        "equality_constraint_count": int(model.neq),
        "maximum_loop_joint_response_rad": maximum_loop_response,
        "maximum_equality_residual_m": maximum_equality_residual,
    }
    records.append((STEP_COUNT, "benchmark-completed", {"metrics": metrics}))
    events = chain_events(records)
    engine = lock["executed_engine"]
    trace = build_trace(
        producer={
            "name": "myactuator-rigid-body-benchmark",
            "version": "1",
            "source_sha256": runner_sha,
        },
        subject={
            "kind": "generic_rigid_body_fixture",
            "subject_id": "subject-generic-rigid-body-fixture",
            "fixture_id": "generic-rigid-body-fixture-v1",
            "model_key": None,
            "series": None,
            "model": None,
            "configuration_id": None,
            "evidence_class": "synthetic-generic-fixture",
        },
        backend={
            "backend_id": "mujoco-generic-benchmark",
            "backend_kind": "rigid_body",
            "engine_name": engine["name"],
            "engine_version": engine["version"],
            "engine_binary_sha256": engine["binaries"][0]["sha256"],
            "use_case": "generic_rigid_body_benchmark",
            "deterministic_virtual_time": True,
            "command_capable": True,
            "exact_model_fidelity": False,
            "physically_validated": False,
            "physical_io": False,
        },
        source_generations={
            "catalog_sha256": None,
            "source_registry_sha256": None,
            "graph_registry_sha256": None,
        },
        tick_period_ns=TICK_PERIOD_NS,
        seed=0,
        reset_generation=1,
        initial_state_sha256=initial_sha,
        events=events,
    )
    return trace, metrics


def _dropbear_denial() -> dict[str, int | str | bool]:
    catalog = SimulationRuntimeCatalog.load()
    model = catalog._value["models"][0]
    selection = SimulationSelection(
        catalog.generation_sha256,
        model["model_key"],
        model["series"],
        model["model"],
        model["configuration_ids"][0],
        "dropbear-rigid-body-unavailable-v1",
        "rigid_body",
        SimulationUseCase.WHOLE_ROBOT_RIGID_BODY,
        False,
        False,
        True,
    )
    admission = catalog.admit(selection)
    require(not admission.allowed, "unavailable Dropbear backend was admitted")
    require(
        admission.reason is SimulationAdmissionReason.BACKEND_NOT_LOADABLE,
        "unavailable Dropbear backend denial reason drift",
    )
    descriptor = next(
        backend
        for backend in catalog._value["backends"]
        if backend["backend_id"] == selection.backend_id
    )
    require(not descriptor["runtime_loadable"], "Dropbear descriptor became loadable")

    graph_registry = read_json(
        ROOT / "generated/dropbear_graph_registry_v2/registry.json"
    )
    cad = read_json(ROOT / "generated/myactuator/cad/support_report.json")
    plant = read_json(ROOT / "generated/myactuator/plant/runtime_registry.json")
    active_graphs = graph_registry["summary"]["accepted_count"]
    accepted_cad = (
        cad["summary"]["geometry_configurations"]
        - cad["summary"]["configuration_statuses"].get("unsupported", 0)
    )
    admitted_plants = plant["summary"]["sourced_parameter_sets"]
    require(
        (active_graphs, accepted_cad, admitted_plants) == (0, 0, 0),
        "canonical scene dependencies changed; benchmark cannot infer admission",
    )
    return {
        "backend_id": selection.backend_id,
        "runtime_loadable": descriptor["runtime_loadable"],
        "admission_reason": admission.reason.value,
        "active_graph_count": active_graphs,
        "accepted_cad_configuration_count": accepted_cad,
        "admitted_real_plant_count": admitted_plants,
    }


def build_report(
    lock: Mapping[str, Any],
    trace: Mapping[str, Any],
    metrics: Mapping[str, Any],
    trace_bytes: bytes,
) -> dict[str, Any]:
    require(metrics["all_state_finite"], "nonfinite rigid-body state")
    require(
        abs(metrics["final_simulation_time_s"] - 2.5) <= 1e-9,
        "fixed-step final time mismatch",
    )
    require(
        metrics["maximum_drive_joint_response_rad"]
        >= JOINT_RESPONSE_MINIMUM_RAD,
        "articulated joint response is below contract",
    )
    require(metrics["contact_observed"], "ground contact was not observed")
    require(
        metrics["minimum_contact_distance_m"]
        >= -CONTACT_PENETRATION_MAXIMUM_M,
        "maximum contact penetration exceeded",
    )
    require(
        metrics["settled_minimum_contact_distance_m"]
        >= -SETTLED_PENETRATION_MAXIMUM_M,
        "settled contact penetration exceeded",
    )
    require(
        0.039 <= metrics["final_drop_body_height_m"] <= 0.041,
        "contact fixture final height is outside tolerance",
    )
    require(
        metrics["maximum_loop_joint_response_rad"]
        >= CLOSED_CHAIN_RESPONSE_MINIMUM_RAD,
        "closed-chain fixture did not respond to bounded effort",
    )
    require(
        metrics["maximum_equality_residual_m"]
        <= CLOSED_CHAIN_RESIDUAL_MAXIMUM_M,
        "closed-chain residual exceeded",
    )
    denial = _dropbear_denial()
    report: dict[str, Any] = {
        "schema_version": "rigid-body-benchmark-report/1",
        "benchmark_id": "generic-rigid-body-benchmark-v1",
        "authority": "offline_synthetic_benchmark_only",
        "contract": {
            "step_count": STEP_COUNT,
            "tick_period_ns": TICK_PERIOD_NS,
            "sample_period_ticks": SAMPLE_PERIOD_TICKS,
            "deterministic_runs": 2,
            "joint_response_minimum_rad": JOINT_RESPONSE_MINIMUM_RAD,
            "contact_penetration_maximum_m": CONTACT_PENETRATION_MAXIMUM_M,
            "settled_penetration_maximum_m": SETTLED_PENETRATION_MAXIMUM_M,
            "closed_chain_residual_maximum_m": (
                CLOSED_CHAIN_RESIDUAL_MAXIMUM_M
            ),
            "closed_chain_response_minimum_rad": (
                CLOSED_CHAIN_RESPONSE_MINIMUM_RAD
            ),
        },
        "engine_lock": {
            "lock_id": lock["lock_id"],
            "lock_sha256": sha256(LOCK_PATH.read_bytes()),
            "engine_id": lock["executed_engine"]["engine_id"],
            "engine_version": lock["executed_engine"]["version"],
            "engine_binary_sha256": lock["executed_engine"]["binaries"][0][
                "sha256"
            ],
            "candidate_count": len(lock["candidates"]),
            "executed_candidate_count": sum(
                item["benchmark_status"] == "executed_generic_fixture"
                for item in lock["candidates"]
            ),
        },
        "fixture": {
            "fixture_id": "generic-rigid-body-fixture-v1",
            "fixture_sha256": sha256(FIXTURE_PATH.read_bytes()),
            "generic": True,
            "degrees_of_freedom": 9,
            "actuator_count": 3,
            "equality_constraint_count": 1,
        },
        "trace": {
            "schema_version": trace["schema_version"],
            "trace_id": trace["trace_id"],
            "trace_file_sha256": sha256(trace_bytes),
            "record_sha256": trace["integrity"]["record_sha256"],
            "event_chain_sha256": trace["integrity"]["event_chain_sha256"],
            "event_count": trace["summary"]["event_count"],
            "command_count": trace["summary"]["command_count"],
            "state_count": trace["summary"]["state_count"],
        },
        "cases": {
            "engine_lock": {
                "result": "PASS",
                "verified_binary_count": len(lock["executed_engine"]["binaries"]),
                "verified_dependency_count": len(lock["dependencies"]),
            },
            "headless_execution": {
                "result": "PASS",
                "rendering_requested": False,
                "display_required": False,
                "model_load_count": 2,
            },
            "fixed_step_articulation": {
                "result": "PASS",
                "steps": metrics["steps"],
                "final_simulation_time_s": metrics["final_simulation_time_s"],
                "maximum_drive_joint_response_rad": metrics[
                    "maximum_drive_joint_response_rad"
                ],
                "all_state_finite": metrics["all_state_finite"],
            },
            "contact_stability": {
                "result": "PASS",
                "contact_observed": metrics["contact_observed"],
                "minimum_contact_distance_m": metrics[
                    "minimum_contact_distance_m"
                ],
                "settled_minimum_contact_distance_m": metrics[
                    "settled_minimum_contact_distance_m"
                ],
                "final_drop_body_height_m": metrics[
                    "final_drop_body_height_m"
                ],
            },
            "closed_chain": {
                "result": "PASS",
                "equality_constraint_count": metrics[
                    "equality_constraint_count"
                ],
                "maximum_loop_joint_response_rad": metrics[
                    "maximum_loop_joint_response_rad"
                ],
                "maximum_equality_residual_m": metrics[
                    "maximum_equality_residual_m"
                ],
            },
            "deterministic_replay": {
                "result": "PASS",
                "run_count": 2,
                "byte_equal_trace": True,
                "run_record_sha256s": [
                    trace["integrity"]["record_sha256"],
                    trace["integrity"]["record_sha256"],
                ],
            },
            "joint_state_parity": {
                "result": "PASS",
                "joint_count": len(JOINTS),
                "position_unit": "rad",
                "velocity_unit": "rad/s",
                "effort_unit": "Nm",
                "validity_explicit": True,
                "ros_runtime_loaded": False,
            },
            "workflow": {
                "result": "PASS",
                "single_command": (
                    "python3 tools/run_rigid_body_benchmark.py --check"
                ),
                "atomic_outputs": True,
                "network_required": False,
                "physical_io": False,
            },
            "unavailable_dropbear_descriptor": {
                "result": "PASS",
                "backend_id": denial["backend_id"],
                "runtime_loadable": denial["runtime_loadable"],
                "admission_reason": denial["admission_reason"],
            },
            "canonical_scene_admission": {
                "result": "PASS",
                "active_graph_count": denial["active_graph_count"],
                "accepted_cad_configuration_count": denial[
                    "accepted_cad_configuration_count"
                ],
                "admitted_real_plant_count": denial[
                    "admitted_real_plant_count"
                ],
                "canonical_scene_executed": False,
            },
        },
        "summary": {
            "case_count": 10,
            "passed_case_count": 10,
            "failed_case_count": 0,
            "result": "PASS",
        },
        "dropbear": {
            "production_engine_selected": False,
            "canonical_scene_available": False,
            "canonical_scene_executed": False,
            "blockers": [
                "active_canonical_graph_absent",
                "accepted_articulated_cad_absent",
                "admitted_real_motor_plants_absent",
                "equivalent_candidate_engine_benchmarks_pending",
                "ros_cpp_runtime_handoff_pending",
            ],
        },
        "claims": {
            "generic_fixture_passed": True,
            "production_engine_selected": False,
            "canonical_dropbear": False,
            "exact_model_fidelity": False,
            "physically_validated": False,
            "support_granted": False,
            "physical_motion_authority": False,
            "physical_io": False,
        },
        "integrity": {"record_sha256": ZERO_SHA256},
    }
    report["integrity"]["record_sha256"] = digest(report)
    validate_report(report, trace=trace, trace_bytes=trace_bytes)
    return report


def validate_report(
    report: Mapping[str, Any],
    *,
    trace: Mapping[str, Any],
    trace_bytes: bytes,
) -> None:
    validate_schema(report, REPORT_SCHEMA, "benchmark report")
    require(
        report["integrity"]["record_sha256"] == digest(report),
        "benchmark report record digest mismatch",
    )
    validate_trace(trace)
    require(
        report["trace"]["trace_file_sha256"] == sha256(trace_bytes),
        "benchmark trace file hash mismatch",
    )
    require(
        report["trace"]["record_sha256"]
        == trace["integrity"]["record_sha256"],
        "benchmark trace record hash mismatch",
    )
    require(
        report["trace"]["event_chain_sha256"]
        == trace["integrity"]["event_chain_sha256"],
        "benchmark event-chain hash mismatch",
    )
    require(
        all(case["result"] == "PASS" for case in report["cases"].values()),
        "benchmark report contains a failed case",
    )
    require(
        report["summary"]
        == {
            "case_count": len(report["cases"]),
            "passed_case_count": len(report["cases"]),
            "failed_case_count": 0,
            "result": "PASS",
        },
        "benchmark summary mismatch",
    )
    require(
        not any(
            report["claims"][key]
            for key in (
                "production_engine_selected",
                "canonical_dropbear",
                "exact_model_fidelity",
                "physically_validated",
                "support_granted",
                "physical_motion_authority",
                "physical_io",
            )
        ),
        "benchmark report contains an authority promotion",
    )


def generate() -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    lock = load_engine_lock()
    first_trace, first_metrics = run_once(lock)
    second_trace, second_metrics = run_once(lock)
    first_bytes = canonical_json(first_trace)
    second_bytes = canonical_json(second_trace)
    require(first_bytes == second_bytes, "repeated benchmark traces differ")
    require(
        canonical(first_metrics) == canonical(second_metrics),
        "repeated benchmark metrics differ",
    )
    report = build_report(lock, first_trace, first_metrics, first_bytes)
    report_bytes = canonical(report)
    return first_trace, first_bytes, report, report_bytes


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        staged = Path(temporary.name)
    staged.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and fail if tracked artifacts differ",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    args = parser.parse_args()
    try:
        trace, trace_bytes, report, report_bytes = generate()
        trace_path = args.output_dir / TRACE_NAME
        report_path = args.output_dir / REPORT_NAME
        if args.check:
            require(trace_path.is_file(), f"missing generated trace: {trace_path}")
            require(report_path.is_file(), f"missing generated report: {report_path}")
            require(trace_path.read_bytes() == trace_bytes, "generated trace drift")
            require(report_path.read_bytes() == report_bytes, "generated report drift")
        else:
            atomic_write(trace_path, trace_bytes)
            atomic_write(report_path, report_bytes)
        print(
            "rigid-body benchmark: "
            f"{report['summary']['result']} "
            f"cases={report['summary']['passed_case_count']}/"
            f"{report['summary']['case_count']} "
            f"events={trace['summary']['event_count']} "
            f"trace={trace['trace_id']} "
            "dropbear=DENIED"
        )
        return 0
    except (RigidBodyBenchmarkError, OSError, ValueError) as error:
        print(f"rigid-body benchmark failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
