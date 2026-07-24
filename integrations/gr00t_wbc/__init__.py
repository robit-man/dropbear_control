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
from .g1_shadow_decoder import (
    G1ShadowDecoder,
    G1ShadowDecoderError,
    G1ShadowDecoderUnavailable,
)
from .policy_client import (
    G1SonicPolicyClient,
    G1SonicPolicyClientError,
    G1SonicProtocolError,
    G1SonicServerError,
    G1SonicTransportTimeout,
    G1SonicTransportUnavailable,
    SafePolicyWireSerializer,
    policy_client_contract,
    validate_unitree_g1_sonic_response,
)

__all__ = [
    "ACTION_COUNT",
    "ACTION_NAMES",
    "CONTRACT",
    "OBSERVATION_DIM",
    "USD_JOINT_NAMES",
    "DropbearOrderConverter",
    "G1ShadowDecoder",
    "G1ShadowDecoderError",
    "G1ShadowDecoderUnavailable",
    "G1SonicPolicyClient",
    "G1SonicPolicyClientError",
    "G1SonicProtocolError",
    "G1SonicServerError",
    "G1SonicTransportTimeout",
    "G1SonicTransportUnavailable",
    "SafePolicyWireSerializer",
    "UpstreamSonicActionAdapter",
    "policy_client_contract",
    "validate_unitree_g1_sonic_response",
    "verify_source_assets",
]
