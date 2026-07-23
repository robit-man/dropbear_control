# Test evidence bundle format

Each run writes an immutable directory named
`<UTC>-<test-id>-<result-id>/` containing `manifest.yaml`, `result.json`, logs
and referenced artifacts. Hashes are SHA-256. Paths in the manifest are
relative and must remain inside the bundle.

```yaml
schema: myactuator-evidence/v1
result_id: EV-<uuid>
test:
  id: TST-PRO-001
  version: <test-source-hash>
  title: <stable title>
  evidence_class: OFFLINE-UNIT  # controlled enum
  started_utc: <RFC3339>
  ended_utc: <RFC3339>
  monotonic_duration_ns: <integer>
subject:
  repository_revision: <git object id>
  dirty_state_sha256: <hash or null>
  configuration_hash: <hash or null>
  artifact_hashes: [{path: <relative>, sha256: <hex>}]
  support_key: null             # exact complete tuple for bench/HIL/robot
environment:
  runner: <host/CI/fixture id>
  os_arch: <value>
  tools: [{name: <value>, version: <value>, digest: <value>}]
  simulator: null               # name/version/parameters/seed when SIL
  hardware: null                # required object for BENCH/HIL/ROBOT
trace:
  requirements: [PRO-002, PRO-003]
  risks: [RSK-001]
  work_items: [WP-050-T02]
  gate: G1
sources:
  - id: SRC-003
    revision: "260703 / protocol V4.4 260425"
    locator: <section-table-page-or-file-hash>
execution:
  command: [<argv entries, never a shell string with secrets>]
  seed: null
  cases_total: 1
  cases_passed: 1
  cases_failed: 0
  cases_not_run: 0
result:
  disposition: PASS             # PASS|FAIL|NOT_RUN|ERROR
  expected: <machine-readable assertion summary>
  observed: <machine-readable observation summary>
  limitations: []
review:
  author: <identity>
  independent_reviewer: null
  reviewed_utc: null
  signature: null
supersedes: null
```

## Hardware object (mandatory above SIL)

Record motor manufacturer/model/serial/hardware revision/drive firmware,
protocol revision/mode, ESP32 board and firmware, bus adapter/transceiver,
wiring/termination, supply and configured current/voltage limits, fixture/load,
brake, independent cut, instruments with calibration dates, environmental
conditions, operator and approved procedure revision. Unknown fields make the
result ineligible for support promotion.

## Evidence validation rules

1. `evidence_class` must match the actual runner profile; the validator rejects
   missing hardware for BENCH/HIL/ROBOT.
2. `PASS` requires zero failed/error/required-not-run cases and hashes for all
   logs/artifacts. Process exit zero alone is insufficient.
3. A dirty worktree is allowed during development but its normalized diff hash
   is mandatory; releases require reviewed attribution.
4. Manual reviews (CAD articulation, hazard inspection) use the same manifest
   with signed checklist artifacts and at least one independent reviewer.
5. Secrets, raw credentials and private keys never enter evidence. Device
   serials may be access-controlled but remain stable identifiers.
6. Evidence is stale when a traced source, requirement, implementation,
   config, tool/fixture or exact tuple changes according to the dependency
   rules in [support-evidence-schema.md](../requirements/support-evidence-schema.md).

