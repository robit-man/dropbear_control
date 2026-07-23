# MYACTUATOR source CAD catalog

`catalog.tsv` pins the 44 product packages exposed by MYACTUATOR's six
series download pages on 2026-07-22. Run the repository sync tool from the
project root to populate the ignored vendor cache:

```bash
tools/sync_myactuator_cad.sh
tools/sync_myactuator_docs.sh
```

The resulting layout is:

```text
assets/vendor/myactuator/<series>/<model>/
  source.url
  source.zip.sha256
  vendor/.../*.STEP
```

The current catalog produces 53 vendor STEP files for 44 named motor models.
RH brake/non-brake packages and several older RMD-X packages contain multiple
variants, so preserving every source STEP is intentional.

`download_index_snapshot.json` records the normalized archive-link set
observed on all six live vendor pages. On 2026-07-23 the live set matched the
tracked 44 CAD plus nine document URLs exactly. Check the snapshot offline, or
perform an explicit non-mutating live probe:

```bash
python3 tools/manage_myactuator_download_index.py
python3 tools/manage_myactuator_download_index.py --probe
```

`--refresh` replaces the snapshot only when the live and tracked sets are
exactly equal. Missing or additional links require source change control and
leave the prior snapshot untouched.

Two tracked evidence manifests make that ignored cache reproducible and
auditable without redistributing vendor geometry:

- `source_archives.tsv` records the exact SHA-256 of every one of the 44 source
  archives.
- `step_manifest.tsv` records the path, SHA-256, byte size and source STEP
  structure of all 53 variants. Its review columns deliberately remain
  `unreviewed` until scale, axis, origin, fixed housing and rotating output have
  been inspected.
- `document_archives.tsv` and `document_files.tsv` pin the nine manual packages
  and all 32 extracted PDFs by SHA-256. Package placement is provenance, not
  proof that a protocol applies to an installed motor/firmware tuple.

The Iteration 5 CAD evidence layer adds:

- `generated/myactuator/cad/step_inspection.json`: deterministic bounded Part
  21 schema/entity/member-name/unit/point inventory for all 53 exact sources;
- `assets/myactuator/cad_review.json`: strict 53-variant semantic review and
  44-model canonical-selection ledger, currently unsupported 0/44;
- `tools/cad-toolchain-lock.json`, `requirements-cad-lock.txt`, and
  `tools/cad-wheel-lock.tsv`: platform-specific CadQuery/OpenCascade package,
  wheel and conversion-setting pins;
- `generated/myactuator/cad/toolchain_proof.json`: synthetic separate-link
  STEP/GLB round-trip and articulation proof; and
- `generated/myactuator/cad/geometry_probe.json`: real-source OpenCascade
  import/topology/bounds evidence for 53/53 variants.

Regenerate the manifests only after an intentional catalog update, then verify
them offline:

```bash
python3 tools/build_asset_manifests.py --write
python3 tools/build_asset_manifests.py
```

When the ignored vendor cache is absent, the verifier checks the tracked
44/53 invariants. When it is present, it additionally hashes every archive and
STEP file and requires a byte-for-byte manifest match.

`documents.tsv` separately pins the nine series-specific protocol/manual
packages currently exposed alongside those products. Those files populate
`assets/vendor/myactuator/docs/` and are also ignored source evidence. The
catalog retains X V2, V3, and V4 rather than treating the newest protocol as
backward compatible without proof.

`protocol_applicability/source_claims.tsv` binds six exact protocol/interface
PDF hashes to bounded cover/catalog extraction claims. The generated
44-model/9-package/32-occurrence registry and independent host consumer are
documented in
[`../../docs/MYACTUATOR_PROTOCOL_APPLICABILITY.md`](../../docs/MYACTUATOR_PROTOCOL_APPLICABILITY.md).
Every claim is unreviewed and candidate-only; accepted applicability remains
0/44. The V2 exact-tuple lifecycle can ingest independently reviewed
installed-unit/source/command-response decisions from
`protocol_applicability/decisions/`; applicability acceptance never grants
complete motor support or motion authority.

`plant_source_facts/` is the controlled intake for exact model-specific
parameter observations from those pinned product manuals. The generated
44-model ledger expands the runtime plant contract into 1,496 parameter and
176 operating-envelope requirements, all currently null and blocking. It
preserves 106 exact model/manual candidate relationships without applying
family defaults. See
[`../../docs/MYACTUATOR_PLANT_EVIDENCE_LEDGER.md`](../../docs/MYACTUATOR_PLANT_EVIDENCE_LEDGER.md).

The generated local human handoff at
`generated/myactuator/evidence_intake/` binds all 53 CAD configurations and 44
plant models to the ignored source cache by exact SHA-256. Its 97 drafts cover
689 CAD questions and 1,672 plant requirements. Generated drafts remain
unsubmitted and cannot fill `cad_decisions/` or `plant_source_facts/`; see
[`../../docs/MYACTUATOR_EVIDENCE_INTAKE_HANDOFF.md`](../../docs/MYACTUATOR_EVIDENCE_INTAKE_HANDOFF.md).

The generated program coverage view at
`generated/myactuator/coverage_dashboard/` joins the controlled model/CAD/
plant/applicability artifacts back to all requirements, tests, work packages
and gates. It currently reports 90 implemented-offline, 37 planned and seven
physical-hold verification items and only 3/15 full-objective criteria met.
It grants no review, support, release or motion authority; see
[`../../docs/MYACTUATOR_COVERAGE_DASHBOARD.md`](../../docs/MYACTUATOR_COVERAGE_DASHBOARD.md).

Source pages audited on 2026-07-22 and link-set re-probed on 2026-07-23:

- [download hub](https://www.myactuator.com/dowload) (the live URL is spelled
  `dowload`; `/download` returns 404)
- [RMD-X](https://www.myactuator.com/downloads-xseries)
- [RH](https://www.myactuator.com/downloads-rhseries)
- [RMD-L](https://www.myactuator.com/downloads-lseries)
- [CEM](https://www.myactuator.com/%E5%89%AF%E6%9C%AC-downloads-hm-series)
- [RMD-H](https://www.myactuator.com/downloads-hseries)
- [FL/FLO](https://www.myactuator.com/downloads-flseries)

These files are source geometry, not simulation-ready assets. Twenty-six are
STEP assemblies and 27 are flattened STEP models. None of the archives exposes
a separately named output-shaft STEP. A reviewed conversion stage must identify
the fixed housing and rotating output member, establish the joint frame/axis,
and export canonical `housing.glb` and `output.glb` links. Flattened models need
manual body/face segmentation or better source assemblies from the vendor.

The pinned kernel imports all 53 variants with valid topology. Forty-eight
variants contain one or more closed solids. Five are shell-only and therefore
not collision candidates without explicit healing/solidification evidence:
both byte-identical X6-8 source paths, CEM-25, CEM-45, and FL-85-23. Static
source tokens report millimetres for 52 variants and metres for FL-85-23;
OpenCascade normalizes imported bounds to its millimetre working unit, but the
review ledger still requires an explicit source-unit decision. GLB generation
must explicitly scale OpenCascade millimetres by 0.001; the locked exporter
unit parameters alone did not change stored accessor coordinates.

Run the CAD evidence checks with:

```bash
tests/cad_inspection/run_tests.sh
tests/cad_review/run_tests.sh
tests/cad_toolchain/run_tests.sh
tests/cad_import/run_tests.sh
```

The V2 review ledger groups source variants only through explicit exact-
configuration selectors. Its default migration creates one unresolved selector
per source variant, so brake/non-brake packages and duplicate geometry cannot
inherit acceptance from a marketing model or matching file hash. The current
ledger covers all 53 variants and intentionally supports 0/44 models.

For assembly-backed sources, generate local candidate-review images with the
pinned CAD environment:

```bash
.venv/bin/python tools/render_cad_review_packet.py --all-assemblies
```

Packets are source-hash-bound and join every rendered member to the exact STEP
occurrence and product identity. Name scoring only orders visual candidates; it
does not select a housing, output member, joint axis, or supported simulator
asset. Packet images remain ignored pending explicit redistribution rights.

The all-configuration local campaign joins those 26 assembly packets with all
27 flattened packets and assigns every exact configuration a review/blocker
lane plus 13 unanswered semantic questions. See
[`../../docs/MYACTUATOR_CAD_REVIEW_CAMPAIGN.md`](../../docs/MYACTUATOR_CAD_REVIEW_CAMPAIGN.md).

Flattened STEP files use a separate topology-inventory path:

```bash
.venv/bin/python tools/render_flattened_partition_packet.py --all-flattened
```

This assigns reproducible IDs to every imported closed solid, or to shells when
no closed solid exists, and renders the 12 largest components for local review.
Disconnected solids are not assumed to be housing/output links: single-solid,
high-component-count and shell-only sources receive explicit fail-closed re-
source/partition/healing dispositions. The tracked manifest retains component
metrics and hashes, while vendor-derived packet images remain ignored.

The real-geometry candidate exporter consumes only an explicitly unresolved
hypothesis. The current X12-320 pilot is rebuilt with:

```bash
.venv/bin/python tools/export_cad_candidate.py \
  --hypothesis assets/myactuator/cad_hypotheses/x12-320-step-e7d99e7e0d9683017c1a.json \
  --write-report
```

It preserves selected occurrences as separate STEP leaves, exports metre-scaled
GLB, and verifies housing immobility plus output-only rigid poses at -30/0/+30
degrees. The tracked report retains all unresolved member/origin/sign questions
and is structurally `accepted_asset=false`, `support_granted=false`; it is a
pipeline proof on real source geometry, not an accepted X12 simulator asset.

`tests/cad_import/reprobe.sh` performs the long, process-isolated import sweep
again. The normal import test validates the exact source/inspection/toolchain-
bound evidence record without paying that full cost on every edit.

The current archive/document/geometry cache is deliberately ignored because it
occupies roughly 794 MB and MYACTUATOR does not publish an explicit
redistribution license on the download pages. Confirm redistribution rights and use Git LFS or an
artifact registry before committing vendor geometry.
