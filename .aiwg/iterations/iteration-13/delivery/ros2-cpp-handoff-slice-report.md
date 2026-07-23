# Iteration 13 ROS 2 C++ handoff verification

Status: `PASS / G13.5 SOFTWARE HANDOFF CLOSED`

## Outcome

The Jazzy C++ handoff now compiles, installs and loads without physical
hardware. Its ROS-free semantic core produces byte-identical behavior vectors
to the existing Python core for descriptors, lifecycle, read validity, write
admission and generation revocation. The installed plugin has no transport or
native-command surface and fails closed because authority and concrete
session-adapter dependencies are intentionally absent.

This closes the software handoff contract, not canonical robot control.

## Exact environment

- Ubuntu 24.04 / Linux x86-64 / glibc 2.39;
- ROS 2 Jazzy;
- `ros2_control` 4.45.2;
- `pluginlib` 5.4.5;
- `rclcpp` / `rclcpp_lifecycle` 28.1.21;
- GCC 13.3.0 / CMake 3.28.3 / C++17 / colcon-core 0.21.0;
- 9 exact Debian package versions;
- 4 exact ABI-library hashes; and
- 3 exact framework/API-header hashes.

Lock:
`tools/ros2-cpp-environment-lock.json`

Whole lock SHA-256:
`ce4d99ba05ad71d33d9590c554ce25e4661f59ba5b2babc992b60d14495fd23b`

## Delivered surface

- ament package `myactuator_dropbear_hardware`;
- pure C++ semantic core and typed descriptor/session/lease/read/write values;
- thin framework-managed `hardware_interface::SystemInterface`;
- pluginlib manifest and installed shared library;
- exact URDF descriptor fixture;
- native semantic-core and plugin-load CTests;
- Python/C++ live parity and mutation/static tests;
- exact environment-lock and handoff-report schemas/generators; and
- public build, API, lifecycle and remaining-dependency documentation.

## Focused evidence

- environment lock: PASS, 9 packages / 4 ABI files / 3 API headers;
- colcon build: PASS;
- native CTest: 2/2 PASS;
- repository handoff suite: 6/6 PASS;
- report cases: 10/10 PASS;
- parity transcript: 6/6 lines equal;
- traceability: 77 requirements / 130 catalog tests PASS;
- physical I/O: false;
- physical adapter present: false;
- canonical Dropbear admitted: false; and
- support/motion authority: false.

Tracked parity SHA-256:
`8d235b1467f829c1d47e5de69ab81eb214d62f3f7e317cbc6b9ed4e1d55201c8`

Tracked handoff report SHA-256:
`12a68c9a6b5c77983fd214e622b57536ac2a2a1ae21ff8498e16a6625eeb6283`

## F01–F08 closure

| Item | Evidence |
|---|---|
| F01 environment lock | Exact OS/tool/package/ABI/header record validates and drifts closed |
| F02 C++ descriptor | Field vectors equal live Python dataclass order; validation is exact |
| F03 lifecycle parity | Five successful transition vectors agree byte-for-byte |
| F04 read validity | Stale/missing/faulted/source records agree; plugin maps invalid scalar state to NaN |
| F05 write admission | Generation/deadline/limit/success/replay dispositions agree |
| F06 thin plugin | Static denial scan and architecture expose no native transport escape |
| F07 no-hardware build | Clean colcon build plus semantic/plugin CTests require no device |
| F08 package/API | ament export, plugin manifest, fixture and public handoff guide exist |

## Remaining authority boundary

No live generation provider, accepted graph-generated descriptor, renewable
lease authority or concrete gateway-backed `SessionPort` exists. The shipped
generation provider and session port therefore deny configuration. Adding
those components requires accepted source/graph mappings and a separately
reviewed integration slice; it is not an implementation detail hidden inside
this plugin.
