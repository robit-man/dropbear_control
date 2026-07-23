# Exact-tuple protocol applicability decisions

Only independently reviewed, `submitted` JSON records belong in this
directory. Drafts are generated outside the controlled directory with:

```bash
python3 tools/manage_protocol_applicability_decisions.py \
  --write-template /tmp/protocol-decision.json \
  --model-key MODEL_KEY \
  --protocol-occurrence-id OCCURRENCE_ID \
  --hardware-revision EXACT_REVISION \
  --drive-firmware EXACT_FIRMWARE \
  --installed-unit-id EXACT_UNIT_ID \
  --transport classic_can \
  --control-mode EXACT_CONTROL_MODE
```

An accepted decision requires independent installed-inventory, source-review,
command/response capture, and decision-review identities. A listen-only
capture is useful evidence but cannot establish command/control-mode
applicability. Acceptance grants no complete motor support and no motion
authority.
