# Independent CAD review workbench — RMD-X X12-320

This is a local candidate-review aid. It cannot grant CAD, simulator, motor,
plant, firmware, HIL or robot support.

- Decision: `caddecision-7201eb1ae77673ed653f`
- Exact configuration: `cadcfg-a1d2e03798f1e51ebbdb`
- Exact source: `step-e7d99e7e0d9683017c1a` / `9b1710aef09916c8da02b4e6b750da6bbfe2ba44cad6ba03cd1b53e3858e5eea`
- Candidate output occurrences: `NAUO3`, `NAUO5`, `NAUO14`, `NAUO15`, `NAUO16`, `NAUO17`
- HTML workbench: [index.html](index.html)
- Local assembly overview: [overview](../../review_packets/step-e7d99e7e0d9683017c1a/overview.png)
- Local member sheet: [member sheet](../../review_packets/step-e7d99e7e0d9683017c1a/member-sheet.png)
- Local zero-pose split: [zero pose](../../candidate_exports/step-e7d99e7e0d9683017c1a/pose-+0deg.png)

## Questions that must be resolved for acceptance

1. [ ] Confirm whether NAUO4 and its eight M3 fasteners are stationary housing geometry or co-rotate with the output. (`5202cf94118a0fcc9294e47f190667ae03af7bb1c7c261c70b2c3eeab00b7c4e`)
2. [ ] Confirm whether NAUO14 through NAUO17 and NAUO5 co-rotate with the externally accessible output. (`04168e766b9b86553113b00312ad4c9b0a2209ae9ea328737c74db78dc91e1e5`)
3. [ ] Confirm the exact output reference plane and therefore the source-axis origin rather than assuming source Y equals zero. (`3e6ea64c4c80f3d9b17f00a0e77ed5cf80d6a3bd2f60856fc8aa2d89e6b19af3`)
4. [ ] Confirm the physical encoder-positive direction separately from the geometry-only right-hand +Z simulator convention. (`b90af292764732bbaecd0213f30b0c381ead21b7e57dc0786f23f715120673b0`)
5. [ ] Confirm the hypothesis for this exact no-brake/brake/package selector before merging any duplicate or sibling source. (`ea5040221731eff82818302c008f5524eb84aeafb28c811b8e8d7126292531b6`)

## Submission sequence

1. Open `index.html` locally, inspect every image and occurrence, answer every
   question and download the JSON decision.
2. Validate it with `python3 tools/manage_cad_review_decisions.py --validate <file>`.
3. Place only a validated submitted decision in
   `assets/myactuator/cad_decisions/`; drafts remain generated templates.
4. An accepted geometry decision still grants no support. Rebuild and verify
   released artifacts, update the exact V2 ledger, regenerate consumers and run
   the full gate.
