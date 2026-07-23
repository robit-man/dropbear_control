# Listen-only CAN capture evidence lane

Place append-only JSONL captures here only after the hardware setup, operator,
firmware binary and adapter configuration are identified. Each line must
validate against `schemas/myactuator-can-listen-capture-record.schema.json` and
the whole stream must pass:

```bash
python3 tools/validate_can_capture.py path/to/capture.jsonl
```

A valid capture proves that a particular listen-only setup observed a lossless
sequence of standard CAN frames with monotonic timestamps. IDs shaped like
V4.4 requests/responses are counted only as review candidates. The capture does
not prove motor identity, firmware, protocol applicability, physical behavior,
motion authorization or library support. No physical capture is present in the
repository at this iteration.
