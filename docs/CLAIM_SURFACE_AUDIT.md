# Claim-surface audit

`TST-CLM-003` is a deterministic static check over the repository surfaces
that people and software can reasonably mistake for a support statement:
controlled specifications, public documentation, host and embedded APIs,
ROS interfaces, web UI, schemas, command-line tools and generated consumer
views.

The audit exists because acquisition, compilation and simulation answer
different questions from installed-unit support. A downloaded STEP file
establishes source availability only. A successful build establishes
compile-time compatibility only. Offline unit tests, SIL, emulation and
generic rigid-body fixtures establish only their declared offline evidence
class. None grants exact motor/firmware applicability, physical plant
correlation, HIL evidence, safe motion authority or robot release.

## Closed scope

The exact 20 roots, four path exclusions, five generated/build directory
exclusions and three nonsemantic binary suffixes live in
`tools/claim-surface-policy.json`. The verifier rejects any change to those
sets. Test fixtures and raw vendor/reference evidence are outside the
semantic surface roots. In-scope PNG, GLB and STEP files are not interpreted
as prose, but every such file is still path, size and SHA-256 bound into the
input manifest.

The scanner and policy are excluded from their own lexical scan because the
scanner necessarily contains the phrases it rejects. Both are independently
hashed as verifier entities. The live offline-gate report is excluded because
it changes while the gate executes and already has its own schema, stage and
artifact checks. No arbitrary path exclusion, inline suppression, warning
mode or exception list exists.

## Rules and result

Nine lexical rules reject universal/family claims, acquisition promotion,
build promotion, simulation-to-physical promotion, direct physical authority
and unconditional authority language. Explicit denials such as “not
supported” remain legal. Three structured rules reject true authority
booleans, nonzero physical/support counts and positive support/readiness
statuses in JSON consumer surfaces.

The canonical report records every scanned text/JSON source, every
nonsemantic binary, surface classification, byte count, SHA-256, rule count
and finding. Its Entity–Activity–Agent provenance binds the scope policy and
input manifest to the exact scanner implementation. A passing report requires
zero findings and zero exceptions and always keeps support, physical action
and motion authority false.

This is a misuse and regression control, not a proof that every sentence is
semantically correct. Exact support still requires the independently reviewed
installed-unit tuple and downstream physical gates.
