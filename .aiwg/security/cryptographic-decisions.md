# Cryptographic decision register

Cryptographic code is not implemented in-house. Selection means binding an
exact vetted platform/library adapter, algorithm profile, key purpose,
target/version policy and test evidence.

| ID | Decision | Status | Rationale / open evidence |
|---|---|---|---|
| CRY-001 | SHA-256 for content identity and source binding | accepted for integrity indexing, not authentication | Already used across exact-source records; a bare digest has no signer identity |
| CRY-002 | ESP32 firmware candidate: ESP-IDF Secure Boot V2 RSA-PSS-3072/SHA-256 | conditional | Official classic-ESP32 platform path; exact chip revision/eFuse/provisioning and release signer custody remain unobserved |
| CRY-003 | Use flash encryption in release mode with Secure Boot | required, unconfigured | Current profile has both disabled; development-mode behavior is not a production selection |
| CRY-004 | Bootloader anti-rollback plus application rollback | required, unconfigured | Current profile has app rollback only; authenticity and minimum security version are distinct |
| CRY-005 | ESP-TLS/mbedTLS mutual peer authentication at TLS 1.2 minimum | candidate, unbound | Current package has mbedTLS and TLS 1.2 but also TLS 1.0/1.1; no peer-verifying adapter/certificate policy exists |
| CRY-006 | TLS 1.0 and TLS 1.1 forbidden in selected production profile | accepted policy | Prevents selecting the observed legacy-enabled SDK profile |
| CRY-007 | Config/calibration/evidence signature algorithms | open | Select only after exact verifier, target cost, library maintenance and key lifecycle review; do not reuse firmware key |
| CRY-008 | Seven distinct key purposes | accepted policy | Limits cross-protocol and cross-artifact compromise; enforced by intake semantics |
| CRY-009 | Private keys non-exportable or offline/HSM/signing-service held | accepted policy | No private material in repository, image, environment, argv or logs |
| CRY-010 | CRC-32C remains framing error detection only | accepted | Host-link CRC does not authenticate a peer or message |
| CRY-011 | Persistent replay/audit protection requires durable commit receipts | open adapter | In-memory replay and bounded audit policy are insufficient across reboot/power loss |

## Algorithm-selection gate

For every still-open signature/AEAD/KDF choice, the review must record:

- asset and threat addressed;
- exact primitive/mode/parameter sizes and protocol construction;
- vetted implementation and version;
- target timing, RAM/flash and worst-case behavior;
- key generation, custody, provisioning, rotation, revocation and destruction;
- nonce/randomness/clock requirements;
- known-answer, negative, malformed, rollback, power-loss and interoperability
  tests; and
- migration and failure/recovery behavior.

No placeholder algorithm becomes production merely because an SDK header or
binary is installed.

