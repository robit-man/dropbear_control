# Dropbear PyTorch walking RL

This package is a small, dependency-light PPO baseline for walking policy
experiments. It is deliberately a constrained plant, not a second robot
model: the browser USD and Isaac asset remain the visual/physics authority.

The leg state uses the installed motor sources directly:

- hip pitch motor (`LL_hip_joint` / `RL_hip_joint`)
- knee motor (`LL_knee_actuator_joint` / `RL_knee_actuator_joint`)

The knee is not treated as an independent open-chain revolute. `FourBarLeg`
projects both motor coordinates through a planar four-bar closure and exposes
the resulting coupler angle and closure residual. The policy is penalized for
residual error and receives the residual in its observation, so invalid knee
motion cannot silently become a successful training sample.

The knee motor datum is also mechanically bounded: browser `180°` maps to
policy/ROS `0 rad` (locked), and `360°` maps to `π rad`. Negative knee
coordinates are clamped before the closed-chain plant is evaluated.

## Current status

The policy network, rollout buffer, generalized advantage estimation, clipped
PPO update, checkpoint path, four-bar projection, and knee-bound regressions
are implemented and unit-tested. This package does not currently roll out
against the full Dropbear USD, Isaac/PhysX contacts, the browser simulator, or
the ROS 2 trajectory controller. It should be treated as a reproducible
algorithm and constraint smoke test, not a trained walking policy.

## Run a smoke-training job

```bash
python3 -m rl.train_walk --updates 20 --steps 256 --device cpu
```

The checkpoint is written to `artifacts/rl/dropbear_ppo.pt` unless `--out` is
provided. For a GPU run, use `--device cuda`.

This is a research baseline. Before hardware passthrough, validate a policy in
the Isaac/PhysX Dropbear USD, replay the exact 12-joint trajectory through the
ROS 2 controller, and keep the existing guarded admission path enabled.
