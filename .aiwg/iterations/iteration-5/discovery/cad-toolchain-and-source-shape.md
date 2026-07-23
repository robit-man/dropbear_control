# CAD toolchain and source-shape discovery

Assessment date: 2026-07-22

## Source cache

The ignored vendor cache is present and `tools/build_asset_manifests.py`
re-hashes it successfully against the tracked manifests. The 53 STEP paths are
therefore real local vendor source files, not the six zero-byte legacy web
placeholders under `web/assets/models/`.

| Measure | Observed |
|---|---:|
| Catalog models | 44 |
| STEP variants | 53 |
| Unique STEP SHA-256 values | 48 |
| Byte-identical duplicate groups | 5 |
| Assembly-labelled variants | 26 |
| Flattened variants | 27 |
| Total STEP bytes | 284,822,978 |
| Smallest source | 362,233 bytes |
| Largest source | 75,219,363 bytes |

The duplicate pairs are retained because their archive paths/revisions are
distinct provenance even when the extracted geometry bytes match.

## Lexical source observations

The current assembly classification is deliberately narrow: presence of
`NEXT_ASSEMBLY_USAGE_OCCURRENCE`. Across the sources, static Part 21 tokens
show 27 `CONFIG_CONTROL_DESIGN` files and 26 automotive-design variants (one
with an explicit AP214 descriptor). Product/member names in many assemblies
contain GB-family encoded Chinese bytes inside otherwise Part 21 text, so a
review tool should retain raw strings and offer a reversible GB18030 decoded
candidate rather than destructively rewriting source files.

Length-unit tokens are consistent with `.MILLI.,.METRE.` in 52 variants. The
flattened FL-FLO/FL-85-23 source contains `$,.METRE.` instead. These are unit
candidates, not accepted scales: the inspector cannot prove which geometric
context is authoritative or that placements were applied correctly.

Raw `CARTESIAN_POINT` extrema can help find gross scale anomalies, but they
mix local coordinate systems in assemblies and must be labelled
`untransformed`. They cannot establish an authoritative bounding box, origin,
joint axis or member separation.

## Available conversion environment

At iteration start, no `FreeCADCmd`, FreeCAD Python module, OpenCascade/OCP, CadQuery, Blender,
OpenSCAD, MeshLab, Assimp, Gmsh, Trimesh or GLTF helper is installed in the
current environment. Python, NumPy and SciPy are available. Therefore the
first slice can produce trustworthy lexical/source evidence and strict review
gates, but it cannot yet import B-Reps, resolve assembly placements, tessellate
or export GLB.

The conversion dependency must be isolated and pinned. A successful package
install alone is insufficient: the iteration must record the OpenCascade
kernel/importer version, assembly semantics, tessellation tolerances, coordinate
conversion and deterministic artifact hashes.

## Toolchain decision and import result

The isolated `.venv` now contains CadQuery 2.8.0 with `cadquery-ocp`
7.9.3.1.1 / OpenCascade 7.9.3.1. `requirements-cad-lock.txt` pins 44 resolved
packages and `tools/cad-wheel-lock.tsv` pins the exact CPython 3.12 x86-64 Linux
wheel filename, SHA-256 and byte size for each. `tools/cad-toolchain-lock.json`
also freezes STEP/mesh settings and authority limits.

The synthetic articulation proof exposed that passing `unit="MM"` and
`outputUnit="M"` to the GLB path did not scale stored accessor coordinates.
The accepted conversion contract therefore explicitly scales the OpenCascade
millimetre B-Rep by 0.001 before GLB export and verifies accessor bounds in
metres. The proof preserves a fixed housing, rotates only an asymmetric output
about +Z, round-trips separate STEP B-Reps and emits GLB 2.0 files. It contains
no vendor geometry and creates no model support.

A process-isolated sweep then imported all 48 unique hashes / 53 provenance
variants successfully; all report valid topology and faces. Forty-eight
variant rows contain closed solids. Five are shell-only: both X6-8 paths,
CEM-25, CEM-45 and FL-85-23. Those five can be rendered but cannot become
collision geometry without reviewed healing or solidification evidence.

## Immediate implications

- Do not copy the zero-byte web placeholders into simulator assets.
- Do not label a product-name substring as the output member without visual
  confirmation and retained entity references.
- Do not reuse a millimetre default for FL-85-23 or any ambiguous context.
- Do not treat an assembly relationship as a revolute joint definition.
- Do not convert flattened geometry into two links without reviewed
  segmentation evidence.
- Preserve source paths and hashes even when duplicate geometry shares cached
  inspection results.
