# Iteration 6 verification report — exact CAD candidate foundation

- Iteration disposition: `COMPLETE-OFFLINE-CANDIDATE-FOUNDATION`
- Verification date: 2026-07-22
- Unified gate: `OFFLINE_GATE_OK`
- Accepted vendor CAD configurations: 0/53
- Supported vendor models: 0/44
- Browser-loadable CAD configurations: 0/53
- Physical/plant/HIL evidence: none

## Delivery evidence

| Outcome | Result | Evidence |
|---|---|---|
| Exact geometry selectors | PASS foundation | CAD review V2 covers all 53 source variants exactly once through 53 provenance-preserving unresolved configurations; 44 model aggregates remain unsupported |
| Assembly packets | PASS candidate evidence | 26/26 local packets; exact source hashes and every STEP relationship/product retained; nested H-50-15 distinguishes 17 relationships from 15 renderable leaves |
| Flattened packets | PASS candidate evidence | 27/27 exact packets; 1,628 stable solid/shell component records and local overview/largest-component renders |
| Fail-closed dispositions | PASS | five shell-only, two single-solid, five high-component-count and 15 disconnected-solid/manual-partition dispositions; no topology ID is semantic |
| Real export mechanics | PASS candidate pilot | X12-320 hypothesis exports 12-leaf housing and six-leaf output STEP, metre GLBs, and -30/0/+30 output-only rigid poses with 109,818 output triangles and <=0.001 mm observed deviation |
| Semantic member/axis review | OPEN | X12 retains five explicit member/origin/sign questions; no exact configuration is accepted |
| Consumer enforcement | PASS denial contract | Generated registry covers 44 models/53 variants/53 configurations, denies X12 candidate, exposes zero browser assets and agrees with zero Dropbear CAD bindings |
| Toy plant non-promotion | PASS | Browser dynamics require `synthetic-demo-no-physical-fidelity` and reject physical support/source promotion |
| Traceability | PASS | 77 requirements, 77 rows, 20 sources, 10 ADRs, 20 work packages, 96 test definitions and 48 links |
| ESP32 compile | PASS compile-only | 22,360 B RAM (6.8%); 299,213 B flash (22.8%) |

## Acceptance matrix

I6-D01, I6-D02, I6-D03 and I6-D09 are complete at candidate-foundation
evidence. I6-D04 and I6-D05 remain open because no independent semantic
housing/output/origin/sign review is complete. I6-D06 through I6-D08 are proven
on synthetic geometry and exercised on one real but explicitly unaccepted X12
hypothesis; they are not released-asset evidence. I6-D10 passes only for the
offline foundation and denial controls, not for 44/44 model completion.

## Gate statement

The iteration may close because every generated claim remains bounded by its
evidence and the full offline repository gate is green. It does not satisfy the
G4 44-model asset exit, establish an output shaft for any motor, authorize
redistribution, validate actuator plants, bind Dropbear joints, wire the new
ESP32 gateway into the user runtime, or authorize powered operation.
