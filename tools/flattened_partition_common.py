#!/usr/bin/env python3
"""Dependency-free policy shared by flattened STEP partition tools."""

from __future__ import annotations


PACKET_VERSION = "myactuator-flattened-partition-packet/1"
MANIFEST_VERSION = "myactuator-flattened-partition-manifest/1"
AUTHORITY_FIELDS = (
    "stable_component_ids_are_semantic",
    "housing_member_identified",
    "output_member_identified",
    "joint_axis_identified",
    "simulation_supported",
)


def disposition(component_kind: str, count: int) -> str:
    if component_kind == "shell":
        return "blocked_shell_only_re_source_or_reviewed_healing_required"
    if count == 1:
        return "blocked_inseparable_single_solid_re_source_or_face_partition_required"
    if count > 32:
        return "blocked_high_component_count_partition_ui_or_better_source_required"
    return "candidate_disconnected_solids_manual_partition_required"
