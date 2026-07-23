# Brownfield codebase analysis report

The detailed audit is maintained in three linked reports:

- [MYACTUATOR library completeness](../../docs/MYACTUATOR_LIBRARY_ASSESSMENT.md)
- [Dropbear low-level audit](../../docs/DROPBEAR_CONTROL_STACK_NOTES.md)
- [Target control and simulation architecture](../../docs/CONTROL_STACK_TARGET.md)

## Analysis summary

- Repository structure suggests a complete multi-family stack, but the active
  motor, transport, device and simulator implementations are mostly stubs or
  synthetic models.
- Compile and loopback checks pass and are retained as baseline regressions;
  they do not exercise actuator communication.
- Product and CAD coverage was materially understated. The official catalog
  currently has 44 models and 53 STEP variants rather than six families.
- Dropbear's prototype contains reusable hardware/workflow knowledge alongside
  critical command-ownership, stop-path, parser, persistence, feedback and
  security defects.
- The central architectural gap is a canonical joint/configuration contract and
  an explicit stateful boundary between motor drive, ESP32 gateway, host robot
  interface, control, planning and simulation.

## Recommended disposition

Retain existing code as a labeled prototype and regression source. Begin a new
production path with one exact motor vertical slice, safety state machine,
official protocol evidence, protocol emulator, and real TX/RX before expanding
family coverage or building higher-level motion behavior.
