# ADR-005: Versioned binary host link with semantic dispositions

- Status: Accepted for offline Python/native V1; authenticated transport binding open
- Requirements: LNK-001..005
- Work packages: WP-060, WP-110

## Decision

Use bounded binary framing with major/minor version, explicit length/type,
sequence, monotonic time, CRC and stream resynchronization. Commands carry
config identity and lease; responses distinguish receipt, admission, TX,
native response and observed state.

## Consequences

The existing 64-byte prototype can supply parser regressions but is not frozen
as the production contract. Compatibility negotiation and corrupt-stream tests
are mandatory before replacing it.

The Iteration 3 reference freezes a 72-byte network-order header, bounded typed
payload, CRC-32C and session/config replay gate in
`host/myactuator_lib/hostlink_v1.py`; the exact layout and limitations are in
`.aiwg/iterations/iteration-3/delivery/host-link-v1.md`. Link acceptance never
authorizes motion.

Iteration 4 adds a platform-independent C++11 implementation at
`firmware/esp32/src/hostlink/hostlink_v1.*`, a 32-frame shared Python/native
accept/reject corpus and a bounded async Python session. The native receiver
exposes only typed messages and always returns `motion_authorized=false`.
Native command parsing now composes offline with the config identity guard,
safety supervisor, fake scheduler and V4.4 emulator on a synthetic exact test
tuple. The tracked incomplete Dropbear configuration remains denied.

This decision does not select or authenticate a real byte transport. Serial,
USB or TCP binding, peer authentication, persistent anti-replay state,
backpressure/reconnect policy on a real adapter, ESP32 runtime ownership and
target memory/WCET evidence remain required before production binding.
