# Iteration 15 — platform-rooted security and durable artifact activation

Status: active long-haul WP-170 execution. Offline architecture/transaction
tranche complete; exact target provisioning, adapters and physical evidence
held.

## Objective and non-authority

Replace implicit `authenticated=true` / `artifact_integrity_verified=true`
assumptions with a complete, testable chain from exact ESP32 platform state to
authenticated sessions and atomically activated artifacts. Preserve
authentication, authorization, safety admission and independent power removal
as separate mandatory controls.

This iteration may inspect local toolchains and run offline tests/builds. It
may not read/program eFuses, provision a key, upload firmware, open a serial or
CAN device, energize a drive or authorize motion without a later explicit
physical-work authorization.

## Immutable evidence rules

- SDK/header availability is not feature enablement.
- Build configuration is not exact installed-chip/eFuse evidence.
- A bare digest or CRC is not authentication.
- A verifier assertion is not a verifier implementation.
- A persistence/audit receipt is not durable until an adapter proves
  power-loss and readback behavior.
- No private key, credential, passphrase or bearer token enters source,
  generated artifacts, environment variables, arguments, logs or coredumps.
- Synthetic positive fixtures prove lifecycle reachability only.
- Every pass remains support=false, physical I/O=false and motion=false.

## Gate sequence

| Gate | Work | Entry dependency | Exit evidence | Current state |
|---|---|---|---|---|
| S15.0 | Freeze threat, trust-boundary and secret-handling decisions | WP-170 authorization baseline | ADR-011, chain-of-trust, crypto register, secret policy and updated threat/risk rows | COMPLETE-OFFLINE |
| S15.1 | Bind exact current PlatformIO/Arduino/IDF/sdkconfig/partition profile | S15.0 | strict schemas, canonical candidate/status, drift checker, 10 adversarial tests, zero selected roots/keys/adapters | COMPLETE-OFFLINE |
| S15.2 | Define portable signed-artifact transaction semantics | S15.0..1 | 48 shared Python/native cases, sanitizer/allocation proof, exact stage/commit/abort/reboot state preservation | COMPLETE-OFFLINE |
| S15.3 | Observe exact installed controller security state | explicit unpowered physical authorization; inventory + CAN-controller identity | chip model/revision, redacted eFuse digest, secure-boot compatibility, flash mode, secure-element presence/provisioning and independent review | PHYSICAL-HOLD |
| S15.4 | Select cryptographic and identity adapters | S15.3 plus dependency/SBOM review | exact maintained libraries/platform APIs, algorithms/parameters, key handles, custody/rotation/revocation, target timing/RAM/flash and independent decision | OPEN |
| S15.5 | Implement authenticated host transport/session establishment | S15.4, WP-060 | mutual peer verification, certificate scope/revocation/expiry, fresh boot/session identity, legacy TLS disabled, negative/malformed/interoperability vectors | OPEN |
| S15.6 | Implement encrypted persistent replay and durable audit stores | S15.3..4 | dedicated partition, monotonic state, atomic dual-record/readback protocol, bounded audit export, coredump/retention controls, reset/brownout/torn-write campaign | OPEN |
| S15.7 | Integrate signed config/calibration/evidence and OTA adapters | S15.4..6, WP-030 | exact envelope verifier, separated key purposes, staged storage, anti-rollback, OTA A/B health/rollback, revoked/wrong-target/wrong-purpose/power-loss tests | OPEN |
| S15.8 | Compose authentication → authorization → gateway/safety call sites | S15.5..7, WP-070..080 | no legacy bypass, single typed ingress, last-moment recheck, endpoint default disabled, multi-client/load/DoS tests and safe-action capacity | OPEN |
| S15.9 | Exercise recovery and incident procedures | S15.5..8, authorized fixture/HIL | lost/revoked key, expired cert, corrupted state, failed OTA, audit outage, network isolation and disabled reprovisioning dry runs | PHYSICAL/OPERATIONS-HOLD |

Advancement is monotonic. A failure returns to the prior accepted profile or
disabled reprovisioning state; it never authorizes PAL, WebSerial, raw CAN,
unsigned firmware, TLS verification skip or “continue anyway.”

## S15.3 exact intake checklist

Before any eFuse read or controller interaction, record:

1. authorization record and permitted no-power/unpowered commands;
2. controller asset ID, board/module model/revision and custody;
3. read-only tool/command/version and output-redaction plan;
4. chip model/revision and Secure Boot V2 compatibility;
5. redacted eFuse state digest, not raw device-unique identifiers;
6. current bootloader/app/partition binary/config hashes;
7. Secure Boot, flash encryption mode/counter, boot anti-rollback and secure
   version;
8. encrypted NVS/security partition layout and coredump disposition;
9. secure-element exact part/provisioning state, if present;
10. rollback/recovery prerequisites and assurance that no write/provision
    operation is executed; and
11. independent reviewer identity, competence, UTC review and evidence refs.

Any unknown keeps `selected_profile_id=null`.

## S15.4 adapter decision checklist

For each firmware/config/calibration/evidence/TLS/audit purpose:

1. exact primitive/protocol construction and parameter sizes;
2. vetted implementation/package/source revision and license;
3. public trust termination and non-reused key ID/fingerprint;
4. private-key location class and responsible custodian;
5. provisioning ceremony and separation of duties;
6. rotation, overlap, revocation, compromise and destruction procedure;
7. nonce/randomness/trusted-time/boot-counter requirements;
8. target stack/heap/flash/WCET and failure behavior;
9. known-answer, wrong-key/purpose/target/version, malformed and
   interoperability vectors;
10. power-loss, reset, storage-full and audit-unavailable cases; and
11. migration/rollback compatibility and independent approval.

No implementation starts while an algorithm, root owner or recovery decision
is “TBD.”

## Cross-program release dependencies

Security completion alone cannot release motion. The later order remains:

1. finish S15.3–S15.8 and the WP-060 authenticated link;
2. select/implement the exact CAN adapter through M3 listen-only;
3. complete installed motor inventory and protocol applicability;
4. establish physical independent power removal and exact stop/brake behavior;
5. admit exact configuration, graph, limits, calibration and sensors;
6. execute one-motor then one-leg HIL gates;
7. finish all 53 CAD semantic reviews and 44 sourced plant sets;
8. select the canonical Dropbear graph and whole-robot backend;
9. run unchanged controller/estimator tests through replay/SIL/HIL; and
10. satisfy signed release, operations and robot gates.

The current objective frontier is still dominated by 0/44 accepted protocol
tuples, 0/53 accepted CAD configurations, 0/44 sourced plants, 0 active
Dropbear source/graph, 0/12 motion-ready actuators and all seven physical
verification holds.

