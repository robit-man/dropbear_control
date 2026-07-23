"""Fail-closed post-authentication authorization and audit reference.

This module deliberately does *not* authenticate a peer, verify a credential,
validate a signature, establish a secure transport, or authorize motor motion.
It consumes an identity assertion produced by a future vetted authentication
adapter and decides only whether a request may proceed to the independent
configuration, lease, safety, limit, scheduler, and protocol gates.

The numeric enums and denial order mirror
``firmware/esp32/src/security/security_authorization_core``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Role(IntEnum):
    OBSERVER = 1
    DIAGNOSTIC_OPERATOR = 2
    OPERATOR = 3
    SAFETY_OPERATOR = 4
    CONFIGURATION_MANAGER = 5
    FIRMWARE_MANAGER = 6
    EVIDENCE_REVIEWER = 7


class Action(IntEnum):
    READ_STATE = 1
    READ_DIAGNOSTICS = 2
    SUBMIT_MOTION = 3
    REQUEST_DISABLE = 4
    RESET_FAULT = 5
    STAGE_CONFIG = 6
    ACTIVATE_CONFIG = 7
    STAGE_FIRMWARE = 8
    ACTIVATE_FIRMWARE = 9
    SUBMIT_EVIDENCE = 10


class Target(IntEnum):
    OFFLINE = 1
    SIMULATION = 2
    PHYSICAL_LOCAL = 3
    PHYSICAL_REMOTE = 4


class SafetyState(IntEnum):
    BOOT = 0
    DISCOVERY = 1
    DISABLED = 2
    ARMED = 3
    ENABLED = 4
    SHUTDOWN = 5
    FAULT = 6


class DecisionCode(IntEnum):
    PASS_TO_NEXT_GATE = 0
    INVALID_REQUEST = 1
    NOT_AUTHENTICATED = 2
    IDENTITY_REVOKED = 3
    SESSION_NOT_YET_VALID = 4
    SESSION_EXPIRED = 5
    SESSION_MISMATCH = 6
    REPLAY_OR_REORDER = 7
    ROLE_ACTION_DENIED = 8
    PHYSICAL_ACTUATION_DISABLED = 9
    REMOTE_PHYSICAL_DISABLED = 10
    REMOTE_ADMIN_DISABLED = 11
    LOCAL_PRESENCE_REQUIRED = 12
    CONFIG_BINDING_MISSING = 13
    CONFIG_MISMATCH = 14
    SOURCE_BINDING_MISSING = 15
    SOURCE_MISMATCH = 16
    GRAPH_BINDING_MISSING = 17
    GRAPH_MISMATCH = 18
    LEASE_REQUIRED = 19
    SAFETY_ADMISSION_REQUIRED = 20
    ARTIFACT_INTEGRITY_REQUIRED = 21
    ROLLBACK_PROTECTION_REQUIRED = 22
    INDEPENDENT_APPROVAL_REQUIRED = 23
    APPROVER_NOT_DISTINCT = 24
    APPROVER_ROLE_DENIED = 25
    APPROVAL_SCOPE_MISMATCH = 26
    AUDIT_UNAVAILABLE = 27
    AUDIT_CAPACITY_EXHAUSTED = 28


_ROLE_ACTIONS: dict[Role, frozenset[Action]] = {
    Role.OBSERVER: frozenset({Action.READ_STATE}),
    Role.DIAGNOSTIC_OPERATOR: frozenset(
        {Action.READ_STATE, Action.READ_DIAGNOSTICS}
    ),
    Role.OPERATOR: frozenset(
        {
            Action.READ_STATE,
            Action.READ_DIAGNOSTICS,
            Action.SUBMIT_MOTION,
            Action.REQUEST_DISABLE,
        }
    ),
    Role.SAFETY_OPERATOR: frozenset(
        {
            Action.READ_STATE,
            Action.READ_DIAGNOSTICS,
            Action.REQUEST_DISABLE,
            Action.RESET_FAULT,
        }
    ),
    Role.CONFIGURATION_MANAGER: frozenset(
        {
            Action.READ_STATE,
            Action.READ_DIAGNOSTICS,
            Action.STAGE_CONFIG,
            Action.ACTIVATE_CONFIG,
        }
    ),
    Role.FIRMWARE_MANAGER: frozenset(
        {
            Action.READ_STATE,
            Action.READ_DIAGNOSTICS,
            Action.STAGE_FIRMWARE,
            Action.ACTIVATE_FIRMWARE,
        }
    ),
    Role.EVIDENCE_REVIEWER: frozenset(
        {Action.READ_STATE, Action.READ_DIAGNOSTICS, Action.SUBMIT_EVIDENCE}
    ),
}

_BINDING_ACTIONS = frozenset(
    {
        Action.SUBMIT_MOTION,
        Action.RESET_FAULT,
        Action.STAGE_CONFIG,
        Action.ACTIVATE_CONFIG,
        Action.STAGE_FIRMWARE,
        Action.ACTIVATE_FIRMWARE,
    }
)
_ARTIFACT_ACTIONS = frozenset(
    {
        Action.STAGE_CONFIG,
        Action.ACTIVATE_CONFIG,
        Action.STAGE_FIRMWARE,
        Action.ACTIVATE_FIRMWARE,
    }
)
_ACTIVATION_ACTIONS = frozenset(
    {Action.ACTIVATE_CONFIG, Action.ACTIVATE_FIRMWARE}
)
_REMOTE_ADMIN_ACTIONS = frozenset(
    {
        Action.RESET_FAULT,
        Action.STAGE_CONFIG,
        Action.ACTIVATE_CONFIG,
        Action.STAGE_FIRMWARE,
        Action.ACTIVATE_FIRMWARE,
    }
)


def _digest_valid(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value != "0" * 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class AuthorizationPolicy:
    expected_config_digest: str
    expected_source_generation_digest: str
    expected_graph_generation_digest: str
    physical_actuation_enabled: bool = False
    remote_physical_actuation_enabled: bool = False
    remote_administration_enabled: bool = False


@dataclass(frozen=True)
class IdentityAssertion:
    actor_digest: str
    session_digest: str
    authentication_context_digest: str
    role: Role
    authenticated: bool
    revoked: bool
    valid_from_ns: int
    valid_until_ns: int


@dataclass(frozen=True)
class ApprovalAssertion:
    actor_digest: str
    authentication_context_digest: str
    role: Role
    authenticated: bool
    revoked: bool
    valid_from_ns: int
    valid_until_ns: int
    scope_digest: str


@dataclass(frozen=True)
class AuthorizationRequest:
    action: Action
    target: Target
    safety_state: SafetyState
    session_digest: str
    correlation_digest: str
    sequence: int
    now_ns: int
    config_digest: str
    source_generation_digest: str
    graph_generation_digest: str
    artifact_digest: str
    lease_valid: bool
    safety_admission_ready: bool
    local_presence_verified: bool
    artifact_integrity_verified: bool
    rollback_guard_verified: bool
    approval: ApprovalAssertion | None = None


@dataclass(frozen=True)
class AuditEvent:
    ordinal: int
    actor_digest: str
    session_digest: str
    correlation_digest: str
    authentication_context_digest: str
    action: Action
    target: Target
    role: Role
    decision: DecisionCode
    safety_state: SafetyState
    sequence: int
    monotonic_time_ns: int
    config_digest: str
    source_generation_digest: str
    graph_generation_digest: str
    artifact_digest: str
    lease_valid: bool
    safety_admission_ready: bool


@dataclass(frozen=True)
class AuthorizationResult:
    code: DecisionCode
    audit_event: AuditEvent | None
    sequence_committed: bool
    proceed_to_next_gate: bool
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        if self.motion_authorized:
            raise ValueError("authorization core cannot grant motion authority")
        if self.proceed_to_next_gate != (
            self.code == DecisionCode.PASS_TO_NEXT_GATE
        ):
            raise ValueError("next-gate result disagrees with decision code")


class AuthorizationEngine:
    """One authenticated-session authorization guard with bounded audit lanes.

    The normal lane never overwrites. Once full, a request that would otherwise
    pass is denied. The dedicated safe-disable lane overwrites its oldest entry
    and increments a visible counter so diagnostic traffic cannot consume the
    safe-action audit reserve. Loss of either audit path fails closed; the
    caller must independently transition the safety supervisor toward shutdown.
    """

    def __init__(
        self,
        policy: AuthorizationPolicy,
        identity: IdentityAssertion,
        *,
        normal_audit_capacity: int = 16,
        safe_audit_capacity: int = 4,
    ) -> None:
        if not 1 <= normal_audit_capacity <= 16:
            raise ValueError("normal audit capacity must be in [1, 16]")
        if not 1 <= safe_audit_capacity <= 4:
            raise ValueError("safe audit capacity must be in [1, 4]")
        self.policy = policy
        self.identity = identity
        self.normal_audit_capacity = normal_audit_capacity
        self.safe_audit_capacity = safe_audit_capacity
        self.normal_audit: list[AuditEvent] = []
        self.safe_audit: list[AuditEvent] = []
        self.safe_audit_overwrite_count = 0
        self.unaudited_denial_count = 0
        self.last_sequence = 0
        self._ordinal = 0
        self.normal_audit_ready = True
        self.safe_audit_ready = True

    def set_audit_health(self, *, normal_ready: bool, safe_ready: bool) -> None:
        self.normal_audit_ready = bool(normal_ready)
        self.safe_audit_ready = bool(safe_ready)

    def authorize(self, request: AuthorizationRequest) -> AuthorizationResult:
        code, sequence_committed = self._evaluate(request)
        is_safe_pass = (
            code == DecisionCode.PASS_TO_NEXT_GATE
            and request.action == Action.REQUEST_DISABLE
        )

        if code == DecisionCode.PASS_TO_NEXT_GATE:
            if is_safe_pass and not self.safe_audit_ready:
                code = DecisionCode.AUDIT_UNAVAILABLE
                is_safe_pass = False
            elif not is_safe_pass and not self.normal_audit_ready:
                code = DecisionCode.AUDIT_UNAVAILABLE
            elif (
                not is_safe_pass
                and len(self.normal_audit) >= self.normal_audit_capacity
            ):
                code = DecisionCode.AUDIT_CAPACITY_EXHAUSTED

        event = self._event(request, code)
        stored: AuditEvent | None = None
        if is_safe_pass:
            if len(self.safe_audit) == self.safe_audit_capacity:
                del self.safe_audit[0]
                self.safe_audit_overwrite_count += 1
            self.safe_audit.append(event)
            stored = event
        elif self.normal_audit_ready and len(self.normal_audit) < self.normal_audit_capacity:
            self.normal_audit.append(event)
            stored = event
        else:
            self.unaudited_denial_count += 1

        return AuthorizationResult(
            code=code,
            audit_event=stored,
            sequence_committed=sequence_committed,
            proceed_to_next_gate=code == DecisionCode.PASS_TO_NEXT_GATE,
        )

    def _evaluate(
        self, request: AuthorizationRequest
    ) -> tuple[DecisionCode, bool]:
        policy = self.policy
        identity = self.identity
        if (
            not isinstance(identity.role, Role)
            or not isinstance(request.action, Action)
            or not isinstance(request.target, Target)
            or not isinstance(request.safety_state, SafetyState)
            or not all(
                _digest_valid(value)
                for value in (
                    policy.expected_config_digest,
                    policy.expected_source_generation_digest,
                    policy.expected_graph_generation_digest,
                    identity.actor_digest,
                    identity.session_digest,
                    identity.authentication_context_digest,
                    request.session_digest,
                    request.correlation_digest,
                )
            )
            or identity.valid_until_ns <= identity.valid_from_ns
            or request.sequence <= 0
            or request.now_ns < 0
        ):
            return DecisionCode.INVALID_REQUEST, False
        if not identity.authenticated:
            return DecisionCode.NOT_AUTHENTICATED, False
        if identity.revoked:
            return DecisionCode.IDENTITY_REVOKED, False
        if request.now_ns < identity.valid_from_ns:
            return DecisionCode.SESSION_NOT_YET_VALID, False
        if request.now_ns >= identity.valid_until_ns:
            return DecisionCode.SESSION_EXPIRED, False
        if request.session_digest != identity.session_digest:
            return DecisionCode.SESSION_MISMATCH, False
        if request.sequence <= self.last_sequence:
            return DecisionCode.REPLAY_OR_REORDER, False

        # A fresh authenticated request consumes its sequence even when a later
        # policy, safety, or audit gate denies it.
        self.last_sequence = request.sequence
        if request.action not in _ROLE_ACTIONS[identity.role]:
            return DecisionCode.ROLE_ACTION_DENIED, True

        physical = request.target in (
            Target.PHYSICAL_LOCAL,
            Target.PHYSICAL_REMOTE,
        )
        if request.action == Action.SUBMIT_MOTION and physical:
            if not policy.physical_actuation_enabled:
                return DecisionCode.PHYSICAL_ACTUATION_DISABLED, True
            if (
                request.target == Target.PHYSICAL_REMOTE
                and not policy.remote_physical_actuation_enabled
            ):
                return DecisionCode.REMOTE_PHYSICAL_DISABLED, True
        if (
            request.target == Target.PHYSICAL_REMOTE
            and request.action in _REMOTE_ADMIN_ACTIONS
            and not policy.remote_administration_enabled
        ):
            return DecisionCode.REMOTE_ADMIN_DISABLED, True
        if (
            physical
            and request.action
            in {
                Action.RESET_FAULT,
                Action.ACTIVATE_CONFIG,
                Action.ACTIVATE_FIRMWARE,
            }
            and not request.local_presence_verified
        ):
            return DecisionCode.LOCAL_PRESENCE_REQUIRED, True

        if request.action in _BINDING_ACTIONS:
            if not _digest_valid(request.config_digest):
                return DecisionCode.CONFIG_BINDING_MISSING, True
            if request.config_digest != policy.expected_config_digest:
                return DecisionCode.CONFIG_MISMATCH, True
            if not _digest_valid(request.source_generation_digest):
                return DecisionCode.SOURCE_BINDING_MISSING, True
            if (
                request.source_generation_digest
                != policy.expected_source_generation_digest
            ):
                return DecisionCode.SOURCE_MISMATCH, True
            if not _digest_valid(request.graph_generation_digest):
                return DecisionCode.GRAPH_BINDING_MISSING, True
            if (
                request.graph_generation_digest
                != policy.expected_graph_generation_digest
            ):
                return DecisionCode.GRAPH_MISMATCH, True

        if request.action == Action.SUBMIT_MOTION:
            if not request.lease_valid:
                return DecisionCode.LEASE_REQUIRED, True
            if not request.safety_admission_ready:
                return DecisionCode.SAFETY_ADMISSION_REQUIRED, True

        if request.action in _ARTIFACT_ACTIONS:
            if (
                not _digest_valid(request.artifact_digest)
                or not request.artifact_integrity_verified
            ):
                return DecisionCode.ARTIFACT_INTEGRITY_REQUIRED, True

        if request.action in _ACTIVATION_ACTIONS:
            if not request.rollback_guard_verified:
                return DecisionCode.ROLLBACK_PROTECTION_REQUIRED, True
            approval = request.approval
            if (
                approval is None
                or not approval.authenticated
                or approval.revoked
                or request.now_ns < approval.valid_from_ns
                or request.now_ns >= approval.valid_until_ns
                or not _digest_valid(approval.actor_digest)
                or not _digest_valid(approval.authentication_context_digest)
                or not _digest_valid(approval.scope_digest)
            ):
                return DecisionCode.INDEPENDENT_APPROVAL_REQUIRED, True
            if approval.actor_digest == identity.actor_digest:
                return DecisionCode.APPROVER_NOT_DISTINCT, True
            if approval.role != Role.EVIDENCE_REVIEWER:
                return DecisionCode.APPROVER_ROLE_DENIED, True
            if approval.scope_digest != request.artifact_digest:
                return DecisionCode.APPROVAL_SCOPE_MISMATCH, True

        return DecisionCode.PASS_TO_NEXT_GATE, True

    def _event(
        self, request: AuthorizationRequest, decision: DecisionCode
    ) -> AuditEvent:
        self._ordinal += 1
        identity = self.identity
        return AuditEvent(
            ordinal=self._ordinal,
            actor_digest=identity.actor_digest,
            session_digest=identity.session_digest,
            correlation_digest=request.correlation_digest,
            authentication_context_digest=identity.authentication_context_digest,
            action=request.action,
            target=request.target,
            role=identity.role,
            decision=decision,
            safety_state=request.safety_state,
            sequence=request.sequence,
            monotonic_time_ns=request.now_ns,
            config_digest=request.config_digest,
            source_generation_digest=request.source_generation_digest,
            graph_generation_digest=request.graph_generation_digest,
            artifact_digest=request.artifact_digest,
            lease_valid=request.lease_valid,
            safety_admission_ready=request.safety_admission_ready,
        )
