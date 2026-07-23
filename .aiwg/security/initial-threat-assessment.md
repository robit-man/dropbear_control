# Initial cyber-physical threat assessment

Scope: operator/diagnostic clients, host, ESP32 gateway, native bus/drives,
configuration/update pipeline, simulator/replay and evidence. This is an
initial design assessment, not penetration or safety certification. Physical
hazards remain governed by [risk-register.md](../risks/risk-register.md) and G0.

## Assets and trust boundaries

| Asset | Required property | Boundary |
|---|---|---|
| Human/mechanical safety | No unauthorized or stale actuation; bounded safe action | Independent power cut <-> software stack |
| Command authority/lease | Authentic source, least privilege, fresh session/config and one owner | Clients/network <-> host; host link <-> ESP32 |
| Robot/config/calibration | Integrity, applicability, atomic update and rollback | Build/evidence store <-> deployed host/ESP32 |
| Firmware/toolchain | Provenance, integrity, reproducibility and rollback | Developer/CI/vendor dependencies <-> device |
| Telemetry/fault evidence | Authentic context, ordering, availability and safe retention | Drive/bus <-> gateway <-> host/evidence store |
| Exact support claims | Traceable, class-correct and resistant to stale/forged evidence | Test runners/reviewers <-> release/UI/API |
| Native CAN bus | Exclusive authorized scheduler ownership and fault visibility | ESP32 transport <-> multi-drop actuators |

## Threat scenarios and required controls

| ID | Scenario / consequence | Primary controls | Verification | Residual/open issue |
|---|---|---|---|---|
| THR-001 | Unauthenticated network client uses current Flask-style endpoint to command motion | Remote actuation disabled; authenticated identity; least privilege; gateway lease/safety admission | TST-ROB-007, TST-SEC-001 | Python/native post-auth policy is green; identity/bootstrap, secure transport and endpoint composition remain open |
| THR-002 | Authorized diagnostic client escalates to enable/reset/config/update | Separate action roles; deny-by-default policy; gateway validates every action | TST-SEC-001..002 | Closed offline role matrix and safe-audit reserve are green; real multi-client isolation and local recovery remain open |
| THR-003 | Captured valid command is replayed/reordered after reconnect or reboot | Session-bound monotonic sequence, bounded expiry, config/lease binding; encrypted durable monotonic security state | TST-LNK-007, TST-SAF-004, TST-SEC-003 | In-memory controls are green; persistent store adapter and power-loss proof remain open |
| THR-004 | Serial corruption/injection produces a valid-looking command | Version/length/CRC, bounded parser/resync, semantic admission | TST-LNK-001..003,007 | CRC is error detection, not source authentication |
| THR-005 | Host compromise sends unsafe but syntactically valid values | ESP32 local exact limits, state, lease, discontinuity and health checks; physical cut | TST-SAF-005,007,009 | Local policy quality depends on physical evidence |
| THR-006 | Competing controller/session steals a joint or drives all IDs | Unique registry owner; atomic lease; one scheduler TX task; no enabled preemption | TST-CFG-002, TST-SAF-003, TST-DBR-002..003 | Local maintenance override policy open |
| THR-007 | Malicious/failed diagnostics flood starves control or stop | Bounded queues/rates; event priority; safe-action reservation; resource metrics | TST-SAF-008, TST-SEC-002 | Hardware timing evidence open |
| THR-008 | Config/calibration is modified, partially written or rolled back to unsafe version | Signed/integrity-checked schema, atomic activation, monotonic policy, hash admission, rollback | TST-CFG-003,005, TST-SEC-003 | Root/key/persistence architecture is explicit; vetted verifier/store adapters and power-loss proof remain open |
| THR-009 | Firmware/dependency/vendor artifact is substituted | Pinned digests, reproducible build, signed release/update, isolated vendor evidence, platform-rooted boot chain | TST-SRC-004, TST-SEC-003,005 | Exact profile proves current Secure Boot/flash encryption/anti-rollback are disabled; target provisioning and adapter implementation remain open |
| THR-010 | Native bus node impersonates configured actuator or injects response | Exact identity where available, request correlation, timing/behavior anomaly, physical bus control | TST-PRO-007, TST-HW-001 | Classic CAN lacks origin authentication; physical mitigation required |
| THR-011 | Fault/telemetry is suppressed so controller continues on stale state | Sample age/validity, response budgets, independent local trips, latched fault | TST-SAF-005,007, TST-FW-003 | Drive/local sensor independence to verify |
| THR-012 | Evidence/result class is forged or offline result promoted to HIL | Immutable signed manifests, runner/fixture identity, exact tuple, review, class validator | TST-CLM-002..003, TST-REL-002,005 | Evidence signing/attestation open |
| THR-013 | Logs, arguments, environment or coredumps leak secrets or stable hardware identity | Structured allowlist/redaction, no secrets in env/argv, non-exportable/offline keys, sensitive-coredump policy, seeded-secret scan | TST-SEC-004 | Digest-only bounded event and handling policy are green; durable sink, coredump disposition, retention and runtime scan remain open |
| THR-014 | Browser/UI compromise bypasses host API through direct serial/native bus | Network segmentation; no UI bus access; gateway is final admission authority | TST-HST-004, TST-SEC-002 | Deployment topology open |
| THR-015 | Denial of service/reboot clears fault then resumes motion | Persisted fault policy, boot always disabled, explicit authorized reset, no auto-reenable | TST-SAF-001,006 | Persistence semantics require hazard review |

## Security decisions before powered work

WP-170 now has an executable closed role/action matrix, default-disabled local
and remote physical policy, exact generation/lease/safety prerequisites,
independent activation review, bounded digest-only audit contract, a
non-circular chain-of-trust design and an exact installed-profile intake. The
tracked profile has zero selected roots/keys/adapters and confirms that Secure
Boot, flash encryption, boot anti-rollback and encrypted NVS are disabled while
legacy TLS remains compiled. It still must provision and independently review
an exact target; bind device/operator authentication, verifier, replay, audit
and OTA adapters; prove power-loss behavior; define local recovery/retention;
and establish deployment segmentation. See
[SECURITY_AUTHORIZATION_BOUNDARY.md](../../docs/SECURITY_AUTHORIZATION_BOUNDARY.md)
and [ESP32_SECURITY_PLATFORM_INTAKE.md](../../docs/ESP32_SECURITY_PLATFORM_INTAKE.md).

## Safety interaction

Authentication never substitutes for admission, limits, leases or independent
power removal. Conversely, an emergency disable path may be authorized more
broadly than enable but must be rate-bounded and auditable so it cannot starve
safe action. Security failures that affect command/config/state integrity are
P0 safety events and transition according to
[safety-state-machine.md](../architecture/safety-state-machine.md).
