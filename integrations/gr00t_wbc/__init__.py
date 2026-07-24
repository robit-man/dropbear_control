"""Dropbear integration overlay for NVIDIA GR00T Whole-Body Control.

The package is intentionally dependency-free.  Isaac Lab, PyTorch, CUDA and
TensorRT are runtime dependencies of the pinned upstream project, not of the
contract and motion-reference validation tools in this overlay.
"""

from .embodiment import (
    ACTION_COUNT,
    ACTION_NAMES,
    CONTRACT,
    OBSERVATION_DIM,
    USD_JOINT_NAMES,
    verify_source_assets,
)
from .order_converter import DropbearOrderConverter
from .action_adapter import UpstreamSonicActionAdapter

__all__ = [
    "ACTION_COUNT",
    "ACTION_NAMES",
    "CONTRACT",
    "OBSERVATION_DIM",
    "USD_JOINT_NAMES",
    "DropbearOrderConverter",
    "UpstreamSonicActionAdapter",
    "verify_source_assets",
]
