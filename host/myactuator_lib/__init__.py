"""MYACTUATOR/Dropbear host-side prototype and offline reference cores.

The package contains legacy transport/device/ROS scaffolding plus separately
evidenced offline components. Importability or catalog coverage does not prove
that a physical model/firmware/transport/control-mode tuple is supported.

Package layout (built incrementally):
    myactuator_lib.transport   — bus abstractions (CAN / RS485 / EtherCAT)
    myactuator_lib.device      — per-product motor device drivers
    myactuator_lib.protocol    — legacy 64-byte prototype framing
    myactuator_lib.rmd_v44     — official-source pure V4.4 codec reference
    myactuator_lib.protocol_applicability — exact source/applicability denial
    myactuator_lib.simulation_runtime — evidence-aware simulator catalog
    myactuator_lib.simulation_session — deterministic simulator lifecycle
    myactuator_lib.trace_interchange — canonical backend-neutral traces
    myactuator_lib.ros2_control_core — ROS-independent control semantics
    myactuator_lib.support     — exact-tuple evidence/decision policy
    myactuator_lib.rmd_v44_emulator — protocol-state SIL, not a motor plant
    myactuator_lib.hostlink_v1 — bounded typed link reference, no I/O/authority
    myactuator_lib.gateway_session — bounded async lifecycle over injected I/O
    myactuator_lib.security_authorization — post-auth least-privilege/audit core
    myactuator_lib.artifact_trust — verifier-neutral staged/durable artifact core
    myactuator_lib.can_adapter_intake — reviewed no-I/O adapter manifests
    myactuator_lib.cad_assets  — exact reviewed local CAD admission boundary
    myactuator_lib.actuator_plant — conservative deterministic V1 plant core
    myactuator_lib.actuator_plant_v2 — event-scheduled deterministic V2 core
    myactuator_lib.multi_actuator_plant_v2 — transactional synthetic V2 bank
    myactuator_lib.plant_runtime_adapter — typed reviewed V1 source adapter
    myactuator_lib.plant_runtime_adapter_v2 — typed reviewed V2 source adapter
    myactuator_lib.plant_models — typed backend and sourced-plant selection
    myactuator_lib.calibration — exact-subject calibration evidence admission
    myactuator_lib.limits      — multi-provenance exact limit intersection
    myactuator_lib.joint_observation — host/native observation parity reference
    myactuator_lib.dropbear_readiness — generated exact actuator denial view
    myactuator_lib.dropbear_source_authority — denial-only source-role status
    myactuator_lib.dropbear_source_registry_v2 — replayed source lifecycle
    myactuator_lib.dropbear_graph — parity-checked denial-only graph views
    myactuator_lib.dropbear_graph_lifecycle_v2 — registry-generation graph views
    myactuator_lib.dropbear_hardware_api — graph-gated typed joint API contract
    myactuator_lib.ros         — incomplete ROS 2 scaffolding

The firmware counterpart lives in ``firmware/esp32``. Files under
``contracts/`` record legacy intent and are not authoritative protocol
evidence. New protocol implementations require pinned official sources,
revision-exact applicability and shared host/native conformance vectors.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "MyActuatorError",
    "TransportError",
    "ProtocolError",
    "DeviceError",
    "__version__",
]


class MyActuatorError(Exception):
    """Base exception for all myactuator_lib errors."""


class TransportError(MyActuatorError):
    """Raised when a transport (CAN/RS485/EtherCAT) operation fails."""


class ProtocolError(MyActuatorError):
    """Raised when a wire-protocol encode/decode or CRC check fails."""


class DeviceError(MyActuatorError):
    """Raised when a device-level command is rejected or times out."""
