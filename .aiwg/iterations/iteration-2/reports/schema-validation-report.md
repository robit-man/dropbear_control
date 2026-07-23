# Iteration 2 schema validation report

- Executed: 2026-07-22T18:15:41-07:00
- Evidence class: offline
- Hardware commanded: no
- JSON Schema document parse: pass
- Example JSON parse: pass
- Dependency-free semantic validation: pass, 0 issues
- Draft 2020-12 schema self-check and example instance validation: pass using
  installed `jsonschema` 4.10.3
- Missing-required and additional-property structural negatives: pass
- Unit tests: pass, 23/23

Commands:

```bash
python3 -m json.tool schemas/dropbear-config.schema.json >/dev/null
python3 -m json.tool \
  schemas/examples/dropbear-observed-incomplete.json >/dev/null
python3 schemas/validate_dropbear_config.py \
  schemas/examples/dropbear-observed-incomplete.json
tests/schema/run_tests.sh
```

The tests cover exact canonical joint topology, five encoder observations per
leg role, missing hip-yaw external sensing, legacy-vs-native identifier
separation, uniqueness, ownership agreement, boundary-only aliases, no
wildcard tuples, unknown-to-unsupported propagation, provenance references,
digest tampering and incomplete-config enable rejection.
