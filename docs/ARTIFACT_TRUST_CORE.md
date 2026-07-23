# Signed-artifact transaction core

Status: `OFFLINE-REFERENCE`; no cryptographic verifier, persistent store, OTA
installer, durable audit sink, target profile, physical I/O or motion
authority is present.

The Python and allocation-free C++11 cores define the portable semantics
between a future vetted verifier/persistence adapter and the existing
configuration, calibration, firmware and evidence consumers.

## Boundary

```text
signed artifact bytes
  -> vetted platform/library verifier                         OPEN
  -> exact VerificationAssertion
  -> artifact transaction core                               IMPLEMENTED OFFLINE
  -> staged bytes written/read back by persistent adapter     OPEN
  -> exact DurableCommitReceipt + AuditCommitReceipt
  -> atomic active-generation transition
  -> independent schema/config/safety/update consumers
```

The core has no signature bytes, key bytes, secret fields, filesystem, NVS,
OTA, network or motor interface. A caller must never construct
`VerificationAssertion` from untrusted client claims.

## Stage contract

Staging requires:

- a selected platform profile, terminating trust anchor, verifier binding,
  persistent store binding and trusted current state;
- nonzero transaction, artifact, target, envelope and key-ID digests;
- exact artifact kind, non-reused key purpose, selected algorithm, target,
  envelope and artifact digest agreement between policy/candidate/assertion;
- successful signature/chain assertions and a non-revoked key;
- a security epoch at or above policy/current state; and
- a strictly increasing deployment sequence.

The core distinguishes rollback from “same version, different bytes.” A
successful stage stores only the bounded candidate descriptor and does not
change active state.

## Commit contract

Commit requires the exact staged transaction and:

- a write-complete, read-back-verified receipt bound to artifact, deployment
  sequence and security epoch;
- exact previous generation and next generation = previous + 1; and
- a durable audit receipt bound to transaction, artifact and next generation
  with a nonzero event digest.

Every denial preserves both active state and the staged candidate so a caller
may safely retry or explicitly abort. Only an exact complete commit changes
active state. Abort clears the candidate without changing active state.

These receipts are proof inputs, not proof implementations. A production
adapter must make them meaningful under power loss, storage corruption,
concurrent access and device reset.

## Reboot contract

Restore first clears volatile staging and resets the in-memory active view to
untrusted/disabled. It reconstructs an active generation only from an
integrity-verified persistent snapshot with verified durable-commit and audit
records, nonzero artifact/transaction identities, positive version/generation
and a current security epoch. Any ambiguity leaves generation zero and
integrity false.

## Evidence

`tests/artifact_trust/run_tests.sh` executes:

- one shared 48-case Python/native decision corpus;
- stage/commit/abort retry and state-preservation tests;
- four artifact-kind/key-purpose checks;
- reboot reconstruction and corrupted-snapshot denials;
- GCC ASan/UBSan and undefined-symbol allocation checks; and
- a native host-ABI size measurement (496-byte engine, 7,863-byte object text
  in the current toolchain).

This supplies offline evidence for `TST-SEC-003`; it does not complete
`SEC-003`. The selected platform profile, actual signature verification,
encrypted monotonic storage, power-loss tests, OTA integration and key
operations remain open.
