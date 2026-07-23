# Secret-handling policy

This policy applies to firmware, host/ROS processes, simulators, CI, evidence
tools, support workflows and incident response.

## Never permitted

- private keys, seed phrases, raw credentials, bearer/session tokens or
  passphrases committed to the repository or generated evidence;
- secret values in environment variables, command-line arguments, process
  listings, shell history, logs, crash dumps or telemetry;
- long-lived secrets embedded in firmware source or ordinary mutable flash;
- copying a device identity key between controllers;
- logging stable raw hardware identifiers when a scoped digest is sufficient;
- “temporary” bypass credentials or recovery modes that skip verification.

## Required interfaces

- Offline/release signing accepts a key handle and reads the artifact through a
  file descriptor or a reviewed signing service/HSM API.
- Device TLS keys are generated/provisioned into a reviewed non-exportable
  facility. Applications receive a signing/TLS operation, not raw key bytes.
- Public certificates, public fingerprints, key IDs and rotation/revocation
  metadata are allowed when schema-bounded.
- Short-lived secret buffers use bounded ownership, are never copied into
  audit events and are zeroized where the vetted library/platform guarantees
  meaningful zeroization.
- Build and diagnostic failures report key ID/purpose and a redacted reason,
  never secret content.

## Audit and crash behavior

The audit contract records digest-only actor/session/auth/correlation/config/
source/graph/artifact context. It has no arbitrary payload or secret field.
Coredumps are considered sensitive because memory may contain session
material. The current default profile includes a coredump partition without a
selected confidentiality/export policy, so production selection remains
blocked.

## Provisioning and rotation

Provisioning is a separately authorized, witnessed operation with exact asset,
key purpose, public fingerprint, tool version, UTC time and result. Evidence
contains no private material. Rotation and revocation exercises must be
tabletop-tested before powered release. Failed or interrupted provisioning
leaves the controller unselected and actuation disabled.

