# ADR-011: Platform-rooted security with separated key purposes

- Status: Accepted architecture; target profile and adapters unselected
- Requirements: ROB-007, SEC-001..005, CFG-003..004
- Work packages: WP-030, WP-060, WP-170, WP-180

## Decision

Terminate the classic-ESP32 firmware chain at reviewed Secure Boot V2 eFuse
state, combine it with release-mode flash encryption and bootloader
anti-rollback, and bind operational public roots through authenticated
firmware. Use separately owned keys for firmware, configuration, calibration,
evidence, device TLS identity, operator CA and audit sealing. Use vetted
platform/library adapters rather than project-defined cryptography.

An exact source-bound security profile must prove toolchain configuration,
partitioning, physical chip revision/eFuse state, key custody, adapter
bindings, independent review and durable persistence before selection. Profile
selection grants neither physical support nor motion authority.

## Consequences

The currently installed `esp32dev` build profile is an observed candidate, not
a production security profile: Secure Boot, flash encryption, boot
anti-rollback, NVS encryption and secure-element use are disabled; TLS
1.0/1.1 remain compiled; no persistent security-state partition or production
adapter is bound. Remote actuation remains disabled.

Firmware and operational artifacts cannot share a signing key. Recovery cannot
bypass verification. Bare hashes and CRCs remain useful integrity/error
detection inputs but are not authentication.

