# ADR-003: Pure, versioned native protocol codecs

- Status: Accepted
- Requirements: PRO-001..008, FW-006
- Work packages: WP-040, WP-050

## Decision

Separate revision-specific pure encode/decode cores from transport, clocks,
model constants and safety policy. Typed requests/responses are shared by host
reference tests and platform-independent ESP32-core tests; byte layouts are
not duplicated above the codec boundary.

## Consequences

Official vectors and malformed cases become deterministic offline evidence.
A new vendor revision is a new or explicitly compatible codec, not an in-place
reinterpretation. Physical applicability still requires exact-tuple capture.

