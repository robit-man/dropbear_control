# Passive USB controller role diagnosis

Observed on the AGX Xavier on 2026-09-15. No serial or CAN bytes were
transmitted during these checks.

## Result

All three USB interfaces enumerate as Silicon Labs CP2102 bridges with the
same factory serial number, `0001`. Device names and `/dev/serial/by-id` are
therefore insufficient for assigning controller roles.

| Stable hub path | Linux tty | Passive payload | Assigned role |
|---|---|---|---|
| `1.1` | `/dev/ttyUSB0` | Continuous strict five-value degree CSV | Left leg |
| `1.2` | `/dev/ttyUSB1` | Continuous strict five-value degree CSV | Right leg |
| `1.4` | `/dev/ttyUSB2` | No unsolicited bytes | Neck candidate |

The two leg assignments are corroborated by the prior host convention that
the streaming controller now at `ttyUSB1` is the right leg, the observed
physical default stance, and the fact that the other stream has the same leg
firmware payload. The neck source reports `DEVICE=NECK` only in response to a
`HEALTH` or `STATUS` command, so silence is expected on an unopened passive
link. Its identity remains a candidate until a separately authorized
non-motion health query is performed.

## Live observation evidence

After correcting the service configuration to paths `1.1` and `1.2`, both
sides report `fresh: true`, continuously increasing sequences, and zero read
errors. The API remains `mode: read_only`, `writeCapable: false`, and
`txBytes: 0`. Hip yaw is unavailable on both legs because the deployed CSV
contains five external sensor fields and no yaw field.

The default-stance captures found a bimodal left inner-calf reading spanning
roughly `56°..164°` in the latest five-second sample, with an earlier excursion
to `204°`. The right-knee channel jumped among modes near `0°`, `28°`, and
`58°`, including wrap samples near `359°`, while the robot remained in its
straight-leg pose. The browser records these raw values but holds both model
joints. This prevents an implausible sensor transition from jerking the
closed-loop linkage on screen. Both channels need wiring, supply, sensor, ADC,
and linkage correlation during a controlled passive-motion check.

The fixed capture is only a fallback. The operator workflow is to place both
straight legs in the known baseline pose, enter the measured torso-forward
angle (currently about `7°`), and click **ZERO MODEL FROM CURRENT POSE**. That
stores browser-only offsets from both fresh streams. It does not alter ESP32
calibration or transmit any byte to the controllers.

## Why the initial diagnosis was wrong

The first service launch used an old role table that labeled path `1.4` as the
left leg and path `1.1` as the neck. Path `1.4` opened read-only without errors
but emitted no bytes, which looked like a stalled leg firmware path. A passive
three-port inventory then showed that path `1.1` was already producing the leg
CSV stream. No firmware failure was required to explain the missing dashboard
state; the host role assignment was stale.
