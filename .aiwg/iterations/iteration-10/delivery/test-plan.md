# Iteration 10 delivery test plan

Status: `COMPLETE-OFFLINE`

## Source-authority tests

- strict schema and canonical digest;
- exact commit/tree/inventory/config identity;
- primary source cannot be build/install derivative;
- expanded artifact requires exact generator/source chain;
- every selected divergent group has an explicit disposition;
- missing role, wildcard path, wrong object/hash/logical key and path escape
  deny;
- automation/self/nonindependent reviewer and invalid lifecycle deny;
- no submitted record means accepted count zero.

## Graph-decision tests

- exactly 161 known question IDs, no duplicate/missing/extra answer;
- exactly 12 canonical actuator subjects;
- all joint/link/constraint endpoints resolve;
- axes, transforms, signs, ratios and domains are finite/valid;
- activity and simulator-only classifications are closed enums;
- five/six cardinality, mimic/coupling and loop questions cannot be left
  implicit;
- reviewer/source/inventory/config/digest drift denies;
- no decision field grants CAD/motor/protocol/calibration/limit/motion support.

## Canonical graph tests

- synthetic valid tree, mimic and declared loop cases;
- disconnected component, multiple root, undeclared cycle, multi-parent tree,
  orphan endpoint, duplicate alias/ID and self-edge denials;
- duplicate actuator owner, unowned active coordinate and ambiguous coupling
  denial;
- exact DOF accounting and left/right explicitness;
- missing CAD/calibration/limit/route dependency stays non-ready;
- incomplete real Dropbear input returns zero graph/mappings.

## Projection and API tests

- byte-stable host/ROS/simulator/UI status parity;
- no candidate path becomes runtime URDF/transmission/mapping;
- exact query only, with no family/prefix/order fallback;
- backend-kind mismatch and missing backend deny;
- configure/activate/fault/deactivate/cleanup/reconnect fake lifecycle;
- no physical adapter success, raw native escape or bypass around readiness.

## Regression gates

- new focused suites run normal and adversarial lanes;
- native code, if added, runs warnings-as-errors and ASan/UBSan;
- generated outputs pass exact `--check`;
- 77-row traceability and catalog count remain exact;
- complete machine gate, web suites, ESP32 compile and whitespace pass.

## Results

- graph review/admission: 18 focused tests;
- four consumer projections: 11 focused tests;
- graph-gated hardware API: 17 focused tests;
- unpowered discovery preparation: 13 focused tests;
- new focused total: 59 tests;
- traceability: 77 requirements, 118 catalog tests, 48 relative links;
- complete offline gate: 52 ordered stages passed, including web and ESP32
  compile; and
- physical/bench/HIL/robot evidence: none.
