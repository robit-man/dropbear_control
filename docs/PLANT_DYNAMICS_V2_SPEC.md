# Deterministic actuator plant dynamics V2 specification

Status: implemented offline equation and scheduling contract.

V1 intentionally admits only a conservative, exactly representable subset of
the 38 sourced plant semantics. V2 extends the equation core without changing
V1 behavior or weakening V1 admission. It remains single-actuator offline SIL,
not physical validation, motor support, HIL evidence or motion authority.

## Closed scope

V2 must represent:

- distinct forward and reverse transmission efficiencies;
- continuous and bounded one-shot peak output torque;
- maximum motor and output speed;
- winding and case temperature limits;
- position quantization;
- deterministic position, velocity and current noise;
- command delay with bounded jitter;
- a state-sample period distinct from the current-loop/solver period;
- arbitrary feedback delay with bounded jitter; and
- exact snapshot/replay of all hidden timing, queue, peak and sensor state.

The source facts remain immutable. Supply voltage, ambient temperature,
position bounds, load bound, transmission damping, current-controller gain,
winding/case derate thresholds and semantics selections remain explicit
reviewed execution-profile choices.

## Fixed-step time and event semantics

The electrical/mechanical/thermal solver advances on the exact rational period
`current_loop_period_s`. Decimal input is converted from its canonical decimal
text to a rational number before scheduling.

Commands are submitted at the current solver boundary. Their eligibility time
is:

```text
issued_time + command_delay + selected_command_jitter
```

The command becomes active at the first solver boundary at or after that
eligibility time. This is an explicit current-loop boundary rule, not an
integer-step rewrite of the source delay.

Commands may carry an exclusive solver-step deadline supplied by the host
session. A command that first becomes eligible at or after its deadline is
discarded and can never become active. When jitter reorders commands, the
highest non-expired sequence wins; an older sequence can never overwrite a
newer active command. Expired and stale/superseded counts are distinct
diagnostics.

Sensor captures occur at exact rational multiples of
`state_sample_period_s`. When a capture lies inside a solver interval, the
state is linearly interpolated between the interval endpoints. A captured
sample becomes eligible at:

```text
capture_time + feedback_delay + selected_feedback_jitter
```

It becomes externally visible at the first solver boundary at or after that
eligibility time. The sample retains both exact capture/eligibility times and
the actual delivery boundary. The last delivered sample is held between
deliveries. Before the first delivery, feedback is explicitly unavailable.
Delivery is sequence-monotonic: a late older sample is counted as stale and
cannot replace newer visible feedback.

V2 requires `state_sample_period_s >= current_loop_period_s`; higher-rate
sensor dynamics need a smaller solver period or another adapter version.

## Deterministic jitter and noise

No process-global pseudo-random generator is used. Every variate is a pure
counter-based function of:

- the reset seed;
- a closed stream name;
- command or sample sequence; and
- a lane number.

SHA-256 supplies uniform bits. Delay jitter uses a bounded uniform variate in
`[-delay_jitter_s, +delay_jitter_s]`, then clamps the resulting delay at zero.
The execution profile states whether the sourced jitter applies to command
delay, feedback delay or both.

Sensor noise uses a specified SHA-256 Box–Muller transform with independent
position, velocity and current streams. Each result is:

```text
observed = quantize_or_identity(true_value + standard_deviation * z)
```

Only position has a sourced quantization fact. Velocity/current remain
unquantized after their sourced noise. A zero standard deviation consumes no
authority and produces exact zero noise.

## Electrical state

At each solver step:

```text
back_emf = Ke * rotor_velocity
voltage_request =
    R * target_current
  + back_emf
  + Kp * (target_current - current)
voltage = clamp(voltage_request, -supply_voltage, +supply_voltage)
di/dt = (voltage - R * current - back_emf) / L
current_next = clamp(current + dt * di/dt, +/- max_qaxis_current)
motor_torque = clamp(Kt * current_next, +/- Kt * max_qaxis_current)
```

Thermal derating bounds the active target current. A winding or case shutdown
condition forces the derate to zero.

## Elastic transmission and directional efficiency

Backlash, torsional spring and damping match the V1 definitions. The profile
selects `transmission_torque_sign` as the V2 direction basis:

```text
efficiency =
    forward_efficiency  when transmission_torque >= 0
    reverse_efficiency  when transmission_torque < 0

reflected_motor_load =
    transmission_torque / (gear_ratio * efficiency)
```

The selected basis and both sourced efficiencies are retained in diagnostics
and the runtime contract. They are never averaged.

## Continuous and peak torque

`continuous_only` clamps transmission torque to the sourced continuous output
limit.

`peak_one_shot_per_reset` may use the sourced peak limit only while:

```text
peak_time_used + dt <= peak_duration
```

A step counts against the budget only when the applied absolute transmission
torque exceeds the continuous limit. The budget never recovers before reset,
because the source contract has no reviewed cooldown/recovery fact. Once
exhausted, the continuous limit applies. A future recovery model requires a
new reviewed semantic and adapter version.

## Mechanical, friction and limits

The V1 semi-implicit Euler ordering is retained. V2 additionally clamps rotor
velocity to sourced maximum motor speed and output velocity to the
intersection of sourced maximum output speed and the reviewed operating
envelope. Position bounds and external load bound are reviewed scenario
limits. Coulomb/viscous friction and hard-stop behavior remain explicit.

## Thermal state

The two-node winding/case network retains V1 equations. V2 has separate
reviewed winding and case derate thresholds and separate sourced maximum
temperatures. The command derate is the minimum of both linear derates.
Either maximum produces thermal shutdown.

## State, diagnostics and snapshot closure

Each step reports:

- physical state and delivered sample, if any;
- active and applied command sequence;
- exact command eligibility/activation timing;
- selected directional efficiency;
- continuous/peak torque limit and cumulative peak time;
- capture/delivery counters;
- all saturation, position, thermal and finite-state flags; and
- the V2 solver/noise/jitter algorithm identities.

Snapshots bind the complete configuration digest and contain every hidden
queue, rational clock, sequence, seed, peak budget, pending sample and latest
delivered sample. Restore rejects missing/extra fields, digest drift,
non-dense sequences, time regression, invalid state and foreign
configuration. A restored run must produce the same canonical trace as an
uninterrupted run.

## Authority boundary

The V2 equation core and all synthetic fixtures permanently carry:

```text
support_granted = false
physical_validation = false
physical_io = false
motion_authority = false
```

The separately versioned V2 runtime adapter binds reviewed exact-model facts
and profiles to this engine without changing these false authority fields.
An admitted contract remains sourced SIL evidence until separately authorized
physical correlation and independent review are complete.
