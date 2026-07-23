# Solution profile

## Classification

Brownfield embedded robotics platform with safety-relevant physical actuation,
mixed real-time/non-real-time execution, versioned vendor protocols, large CAD
assets, web diagnostics, host middleware, and simulation/HIL needs.

## Recommended shape

- **Architecture:** layered ports/adapters around a canonical robot/joint and
  motor capability schema.
- **Embedded:** deterministic ESP32 gateway per owned CAN segment; native
  actuator protocol codecs; one command arbiter; explicit safety state machine.
- **Host:** transport-independent device API and robot hardware interface;
  diagnostics and web tools are consumers, not alternate control paths.
- **Simulation:** byte-accurate protocol emulator, parameterized actuator plant,
  and engine-neutral robot description feeding one or more rigid-body backends.
- **Assets:** immutable vendor-source tier plus reviewed runtime visual,
  collision, and articulated-link tiers.
- **Delivery:** evidence-gated vertical slices, beginning with one unloaded,
  current-limited motor and ending with whole-body behavior.

## Quality-attribute priorities

| Priority | Attribute | Driving scenario |
|---:|---|---|
| 1 | Safety | Host, bus, sensor, or task failure causes a bounded transition to verified motor-off |
| 2 | Correctness | Units, signs, IDs, modes, protocol versions, and status correlation are unambiguous |
| 3 | Determinism | Six joints per bus meet measured command/status deadlines without diagnostic starvation |
| 4 | Observability | Every command/state/fault is timestamped, attributable, and recordable for replay |
| 5 | Testability | The same driver/controller cases run against emulator, simulator, and HIL |
| 6 | Maintainability | New motor/firmware support is data plus a codec/capability module, not copied stack logic |
| 7 | Asset fidelity | Scale, axis, housing/output segmentation and provenance are regression-tested |

## Suggested repository boundaries

```text
schema/                 canonical robot, joint, motor capability schemas
protocol/               vendor codecs and golden vectors
firmware/gateway/       platform-independent core + ESP32 adapters
host/                   transport/device API and robot hardware plugin
sim/protocol/           byte/timing/fault emulator
sim/plant/              actuator parameter and dynamics models
robot/dropbear/         URDF/xacro, transmissions, limits, sensors
assets/sources/         tracked manifests; vendor files in artifact storage
assets/runtime/         reviewed visual/collision/articulated outputs
tools/cad/              reproducible conversion and validation
tests/{unit,sil,hil}/    common scenarios and evidence capture
web/                    catalog, diagnostics, telemetry, authorized bench UI
```

## Non-goals for the first vertical slice

- all 44 hardware models working at once;
- EtherCAT before CAN behavior is proven;
- autonomous gait or whole-body control before safety/timing gates;
- high-fidelity thermal identification without test data;
- automatic output-shaft segmentation claimed correct without CAD review;
- preserving current internal APIs when they conflict with protocol truth.

## First vertical slice

One exact Dropbear motor model on a current-limited unloaded bench, using its
actual firmware protocol, with:

- official-source codec and vectors;
- real CAN TX/RX and status polling;
- disable/enable/stop/torque plus faults and lease timeout;
- shared host/firmware schema and structured logs;
- a protocol emulator running the same driver tests;
- reviewed housing/output CAD asset and axis;
- HIL evidence for boot, link loss, malformed frames, bus loss, over-limit
  commands, fault clear, and physical power removal.

This slice is the template for subsequent models and the six-joint leg.
