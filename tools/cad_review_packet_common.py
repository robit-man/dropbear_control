#!/usr/bin/env python3
"""Dependency-free policy shared by CAD review packet tools."""

from __future__ import annotations


PACKET_VERSION = "myactuator-cad-review-packet/1"
MANIFEST_VERSION = "myactuator-cad-review-packet-manifest/1"
AUTHORITY_FIELDS = (
    "heuristic_selects_output",
    "housing_member_identified",
    "output_member_identified",
    "joint_axis_identified",
    "simulation_supported",
)


def candidate_score(name: str | None) -> tuple[int, list[str]]:
    """Rank names for human review without conferring semantic authority."""
    if not name:
        return 0, []
    lowered = name.lower()
    terms = (
        ("输出", 12),
        ("output", 12),
        ("法兰", 8),
        ("flange", 8),
        ("shaft", 7),
        ("轴", 3),
        ("rotor", 3),
        ("转子", 5),
        ("端盖", 1),
        ("螺丝", -8),
        ("screw", -8),
        ("机座", -4),
        ("housing", -4),
    )
    matched = [term for term, _ in terms if term in lowered]
    return sum(weight for term, weight in terms if term in lowered), matched
