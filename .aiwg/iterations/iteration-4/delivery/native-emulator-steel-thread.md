# Iteration 4 delivery — native gateway/emulator steel thread

- Scope: hardware-free composition test only
- Positive fixture: synthetic exact V4.4 node/configuration identity
- Tracked Dropbear configuration: incomplete and motion-denied
- Physical support, bus delivery, plant or mechanical evidence: none

## Composition exercised

```text
Python CommandIntent / host-link V1 encoder
  -> native C++ V1 StreamParser + SessionReceiver
  -> typed request mapping for the synthetic fixture
  -> ConfigIdentityGuard + SafetySupervisor
  -> bounded GatewayCore fake-transport release
  -> canonical RMD CAN V4.4 request
  -> deterministic Python protocol-state emulator
  -> native response correlation
  -> explicit state-sample observation handoff
```

`tests/stack_v1_gateway/stack_bridge.cpp` is a test-only C++17 bridge because
it consumes the generated C++17 configuration projection. The production
host-link, configuration, safety, gateway and V4.4 cores remain C++11 and are
also built separately with stricter no-allocation/no-exception gates.

The positive route is deliberately not inferred from the catalog or tracked
Dropbear observation. It uses configuration ID `synthetic-v44-node1`, revision
`1`, digest `0x33` repeated 32 times, session `0x11223344`, node 1 and a
1.25 A q-axis-current command. That command becomes the reviewed V4.4 A1 raw
value 125 only inside the typed test mapper. There is no public raw frame or
vendor payload in host-link V1.

## Executable scenarios

Run `tests/stack_v1_gateway/run_tests.sh`. Six deterministic tests assert:

1. a valid synthetic typed command reaches native TX, receives correlated
   emulator state and records an explicit observation handoff;
2. the tracked Dropbear configuration remains link-typed but is rejected for
   motion because it has no native nodes and no authorization, producing no TX;
3. response drop expires the native correlation slot without response or
   observation credit;
4. response delay crosses the emulator/native deadline and is a deadline miss,
   not a late success;
5. an unexpected node is rejected without consuming the expected pending
   correlation; and
6. drive-fault injection remains protocol-emulator state and is not promoted
   to plant, hardware or mechanical evidence.

The sanitizer build currently ends with `STACK_V1_GATEWAY_EMULATOR_OK`.

## Disposition boundary

The test preserves link receipt, provisional gateway admission, native TX,
native response and explicit observation as separate events. `ADMITTED` does
not authorize motion, `NATIVE_TX` means only that the fake adapter received an
envelope, and `NATIVE_RESPONSE` means only that a V4.4 frame decoded and
correlated in time. `OBSERVED` is an explicit state-sample handoff supplied by
the test caller; it does not prove shaft position, delivered torque, motor-off
or any other physical state.

## Remaining production work

- authenticate and bind a real host byte transport;
- integrate static object ownership and tasks into the ESP32 runtime;
- implement real CAN/TWAI send-result, timestamped RX, arbitration-loss,
  retry, bus-off recovery and utilization evidence;
- replace synthetic routes only with observed exact actuator tuples and
  reviewed protocol applicability;
- connect native samples to a validity/age-aware state service;
- establish independently verified safe-action delivery and physical stop;
- add sourced actuator plants and articulated housing/output CAD before
  claiming simulator fidelity.

