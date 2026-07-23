# Dropbear chain-of-trust design

Status: architecture baseline accepted; all production roots and adapters
unprovisioned. This design does not authorize hardware access or motion.

## Trust termination and recursion

Every verification path must terminate outside the mutable artifact it
verifies:

```text
chip ROM -> reviewed eFuse Secure Boot root -> signed bootloader/application
                                             |
                                             +-> embedded public operational roots
                                                  -> signed config/calibration

external operator CA -> authenticated operator/service certificate
device non-exportable key + reviewed certificate -> authenticated device peer
offline/HSM evidence root -> signed release/evidence manifest
```

The current repository has hashes and schema validation but no provisioned
root. A manifest hash cannot authenticate the manifest that supplies that same
hash. A public root embedded in application firmware becomes trustworthy only
after the ROM/eFuse/application path is independently established.

## Root and key purposes

| Purpose | Required termination/custody | May be reused? | Current state |
|---|---|---:|---|
| Firmware release | Classic-ESP32 Secure Boot V2 eFuse root; release private key offline/HSM or remote signer | no | unassigned |
| Configuration release | Public root inside authenticated firmware; signer offline/HSM | no | unassigned |
| Calibration release | Public root inside authenticated firmware; signer offline/HSM | no | unassigned |
| Evidence release | Offline evidence root/HSM or signing service | no | unassigned |
| Device TLS identity | Non-exportable device/secure-element key plus certificate | no | unassigned |
| Operator identity CA | External identity-provider/CA custody | no | unassigned |
| Audit seal | Separate protected signing/sealing service or device key | no | unassigned |

Key IDs, public-key fingerprints and evidence references may be stored.
Private key bytes may not enter this repository, firmware images, environment
variables, command arguments or logs.

## Verification flows

### Boot and firmware update

1. ROM/eFuse verifies the boot chain.
2. The selected OTA adapter verifies target, artifact kind, digest, signing
   key/purpose and signature before staging.
3. Staging never changes the active slot.
4. Commit requires a durable monotonic security-version update and exact audit
   receipt.
5. Boot validation and application health decide rollback. Anti-rollback
   separately prevents returning below the accepted security version.
6. Any ambiguous/torn state boots disabled and enters reviewed recovery; it
   never “continues anyway.”

### Configuration and calibration

1. A vetted verifier asserts signature/chain/target/purpose/digest validity.
2. Schema, exact configuration identity, source/graph generations,
   applicability and safety semantics are checked independently.
3. A candidate is written to encrypted persistent storage.
4. Activation is atomic and requires monotonic generation/security epoch plus
   a durable audit receipt.
5. Reboot reconstructs state only from an integrity-verified committed record.
6. Failure preserves the last accepted record and leaves actuation disabled.

### Host/operator session

1. ESP-TLS authenticates the device and operator/service peer under distinct
   identities.
2. Certificate status, scope and expiry produce an authentication assertion.
3. The post-auth authorization core applies exact role/action, revocation,
   replay, configuration/source/graph, lease and safety checks.
4. Gateway arbitration and physical safety remain separate mandatory gates.

Authentication never implies authorization, and authorization never implies
safe motion.

## Recovery, rotation and revocation

- Recovery cannot bypass signature, peer authentication or monotonic state.
- Lost/corrupt trust state enters disabled reprovisioning under an independently
  reviewed local procedure.
- Root rotation uses an overlap window signed by the old accepted root, with a
  separately reviewed emergency path for root compromise.
- Revocation state is versioned, durable and fail-closed when freshness cannot
  be established.
- Device replacement receives a new device identity; identities are not cloned.
- Firmware, config, calibration, evidence, TLS and audit keys rotate
  independently.

## Current blockers

The exact capability intake records zero selected profiles/roots/keys and
disabled Secure Boot, flash encryption, boot anti-rollback, encrypted NVS and
secure-element use. No authenticated transport, artifact verifier, persistent
replay store, durable audit sink or OTA installer is bound. Physical chip/eFuse
state is unknown.

