# Exact-tuple support and evidence schema

Support is computed for one exact tuple, never inferred from a family class or
a successful build.

```text
SupportKey = (
  manufacturer, model, hardware_revision, drive_firmware,
  protocol_name, protocol_revision, transport, control_mode
)
```

Unknown tuple fields are literal `UNKNOWN`, which forces `unsupported`.

## Required support record

| Field | Type / rule |
|---|---|
| `support_id` | Immutable `SUP-<series>-<model>-<ordinal>` |
| `key` | Complete `SupportKey`; no wildcards in accepted evidence |
| `catalog_source` | `SRC-001` row plus archive revision/SHA-256 |
| `protocol_sources[]` | Source IDs plus exact document revision and clause/table/page |
| `capabilities[]` | Individually named command/read/status/fault features; default empty |
| `units` | Wire scale, motor/output coordinate, sign, range, rounding and overflow policy per field |
| `limits` | Provenance-tagged current/voltage/velocity/position/thermal constraints |
| `codec_evidence[]` | Golden-vector result IDs for host and embedded implementations |
| `asset_evidence` | Source STEP hash, transform, housing/output members, axis/origin and visual/collision approvals |
| `sil_evidence[]` | Protocol emulator/plant results and simulator version |
| `bench_evidence[]` | Hardware, firmware, fixture, instruments and current-limited result; empty in P0–P1 |
| `hil_evidence[]` | Gateway/actuator timing and fault tests; empty in P0–P1 |
| `safety_evidence[]` | Motor-off, lease loss, fault latch and independent power-removal results |
| `limitations[]` | Explicit exclusions and unresolved uncertainties |
| `state` | One value from the state lattice below |
| `review` | Author, independent reviewer, UTC time and approving gate |

All test results conform to [evidence-format.md](../testing/evidence-format.md).

## State lattice

| State | Minimum evidence | Public wording allowed |
|---|---|---|
| `catalogued` | Catalog identity and archive integrity | “listed / CAD acquired” |
| `specified_offline` | Applicable official clauses and reviewed units/limits | “specified from revision …” |
| `codec_conformant_offline` | Independent golden vectors, boundaries and malformed cases on host + embedded core | “offline codec conformance” |
| `sil_validated` | Emulator and plant tests with declared uncertainty | “SIL validated for …” |
| `bench_validated` | Exact physical tuple and safe bench suite | “bench validated on exact tuple …” |
| `hil_validated` | Timing, disconnection, fault and stop injection through real gateway | “HIL validated on exact tuple …” |
| `robot_released` | Dropbear integration, operational limits and release gate | “released for Dropbear revision …” |
| `unsupported` | Missing/contradictory required field or revoked evidence | “unsupported” only |

States are monotonic only while all evidence remains current. A source,
firmware, configuration, code, fixture or requirement change marks dependent
records `stale`; stale records are treated as `unsupported` until rerun.

## Capability rule

Support is capability-specific. For example, a tuple may have offline support
for status decoding while brake release and current command remain
unsupported. The API response is the intersection of independently evidenced
capabilities; it never promotes the whole command set from a single vector.

## Initial catalog ledger

The 44 model identities below are `catalogued` for acquisition only. All exact
physical tuples are `unsupported` because `hardware_revision` and
`drive_firmware` are unknown. CAD articulation and output-shaft identity are
also unsupported for every row.

| Series | Models | Model count | STEP variants | Initial state |
|---|---|---:|---:|---|
| RMD-X | X12-320; X6-60; X15-450; X4-36; X6-7; X6-40; X8-25; X6-8; X10-40; X10-100; X2-7; X4-10; X8-32; X8-120 | 14 | 19 | catalogued / physical unsupported |
| RH | RH-14; RH-17; RH-20; RH-25; RH-32 | 5 | 9 | catalogued / physical unsupported |
| RMD-L | L-4005; L-4010; L-4015; L-5005; L-5010; L-5015; L-7015; L-7025; L-9015; L-9025 | 10 | 10 | catalogued / physical unsupported |
| CEM | CEM-25; CEM-45 | 2 | 2 | catalogued / physical unsupported |
| RMD-H | H-50-15; H-70-15; H-90-15 | 3 | 3 | catalogued / physical unsupported |
| FL/FLO | FL-38-08; FL-50-08; FL-50-15; FL-70-10; FL-70-16; FL-85-13; FL-85-23; FLO-50-15; FLO-70-15; FLO-90-15 | 10 | 10 | catalogued / physical unsupported |
| **Total** | **44 exact model names** | **44** | **53** | **0 hardware-supported** |

