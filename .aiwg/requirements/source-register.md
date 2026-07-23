# Controlled source register

Baseline: P0–P1 offline, 2026-07-22. A source being registered does not make
every model or firmware supported. Claims are accepted only through the tuple
and evidence rules in [support-evidence-schema.md](support-evidence-schema.md).

| ID | Source and pinned identity | Authority / permitted use | Current evidence state |
|---|---|---|---|
| SRC-001 | [`assets/myactuator/catalog.tsv`](../../assets/myactuator/catalog.tsv), 44 rows, plus [`download_index_snapshot.json`](../../assets/myactuator/download_index_snapshot.json), six pages/53 normalized links observed 2026-07-23 | Official MYACTUATOR download index observation; product/archive navigation identity only | Live set exactly matched 44 CAD + 9 document URLs; archive bytes remain separately pinned and cached |
| SRC-002 | [`assets/myactuator/documents.tsv`](../../assets/myactuator/documents.tsv), 9 document sets | Official download index snapshot; document-set identity only | Archive/PDF bytes pinned in `document_archives.tsv` and `document_files.tsv`; 32 PDFs cached separately |
| SRC-003 | Canonical codec source `CAN BUS Motor Motion Protocol V4.4 260520.pdf`, SHA-256 `15731a29c60771f0066fa0b2c7a7609de76edc53fbc8757035d2389d7a5dc3d2`; RMD-X archive edition `260425`, SHA-256 `2e0e73a994cf3b15209b9c592654af9724c03bc4c991c3744fab3c08dfd5eecd` | Primary source for a native RMD classic-CAN V4.4 **offline codec hypothesis**; package placement is not model/firmware applicability | 260520 bytes are identical in RH/CEM/RMD-H packages and correct the 260425 A2 `DATA[1]` typo; 34 vectors reviewed/executable; hardware captures missing |
| SRC-004 | `X-V2-protocol-manual`, rev `250213`, protocol V4.2 | Primary source candidate for applicable X-V2 firmware | Cached; applicability to physical inventory unknown |
| SRC-005 | `X-V3-protocol-manual`, rev `250213`, protocol V4.2 | Primary source candidate for applicable X-V3 firmware | Cached; applicability to physical inventory unknown |
| SRC-006 | `RH-dual-encoder-V4.4`, rev `260716` | Primary RH product/protocol candidate | Cached; model/firmware applicability and brake behavior unverified |
| SRC-007 | `L-V3-protocol-manual`, rev `251029` | Primary RMD-L product/protocol candidate | Cached; model/firmware applicability unverified |
| SRC-008 | `CEM-protocol-manual`, rev `260520` | Primary CEM product/protocol candidate | Cached; model/firmware applicability unverified |
| SRC-009 | `H-S3-protocol-manual`, rev `260520` | Primary RMD-H product/protocol candidate | Cached; model/firmware applicability unverified |
| SRC-010 | `FL-user-manual`, rev `251119` | Primary FL mechanical/electrical candidate | Cached; exact native control interface not baselined |
| SRC-011 | `FLO-user-manual`, rev `20241210` | Primary FLO mechanical/electrical candidate | Cached; exact native control interface not baselined |
| SRC-012 | [`source_archives.tsv`](../../assets/myactuator/source_archives.tsv) and [`step_manifest.tsv`](../../assets/myactuator/step_manifest.tsv): 44 vendor CAD archives and 53 extracted STEP identities | Primary geometry packages; acquisition identity only | 26 assembly-preserving and 27 flattened; all simulation-review fields open; no separately named output shaft; redistribution review required |
| SRC-013 | [`MYACTUATOR_LIBRARY_ASSESSMENT.md`](../../docs/MYACTUATOR_LIBRARY_ASSESSMENT.md), repo `d33490c9` plus preserved dirty work | Audited current-library observations; not a vendor source | Accepted as P0 gap baseline |
| SRC-014 | [`DROPBEAR_CONTROL_STACK_NOTES.md`](../../docs/DROPBEAR_CONTROL_STACK_NOTES.md), upstream commit `13cf5ecaa39b8b89c794fe905dcea0490cfa7726` | Audited Dropbear source observations | Accepted as migration/gap baseline, not hardware proof |
| SRC-015 | [`CONTROL_STACK_TARGET.md`](../../docs/CONTROL_STACK_TARGET.md) | Proposed target architecture and delivery sequence | Input to SAD/ADRs; governed by this baseline |
| SRC-016 | Physical Dropbear inventory: motor labels, serials, drive firmware, wiring, IDs, power limits | Required primary applicability evidence | **Missing / P0 physical hold** |
| SRC-017 | Timestamped CAN captures from each supported exact tuple | Required implementation/bench evidence | **Missing / no powered testing authorized** |
| SRC-018 | Reviewed native CAD assembly or vendor clarification identifying housing and output member | Required asset articulation evidence | **Missing for all 44 models** |
| SRC-019 | Calibrated bench/HIL records, fixtures, instruments, stop path, environmental conditions | Required validation evidence | **Missing / no HIL claim permitted** |
| SRC-020 | Canonical Dropbear `robot.yaml`, reviewed joint registry and generated-artifact provenance | Required cross-layer source of truth | **Not yet created** |

## Source-handling rules

1. Vendor URL, package revision and SHA-256 identify acquisition; the extracted
   filename alone is insufficient.
2. A product manual supplies ratings, not proof that a particular installed
   drive uses a protocol revision.
3. Audit findings are admissible for risk and regression-test creation, never
   for a “hardware verified” support state.
4. Machine-extracted PDF text is a navigation aid. Each golden vector records
   manual title/revision, section/table/page and reviewer.
5. Later vendor packages do not silently replace pinned sources. A source
   update raises change control against affected requirement, codec, asset and
   evidence IDs.
