# Dropbear PyTorch walking RL

This package provides a compact PPO teaching plant for local walking-policy
experiments. It uses the exact dashboard motor order—12 leg sources followed
by 10 arm sources—and exports deterministic rollouts that the full browser USD
can replay while training continues.

It is intentionally not a replacement for the Dropbear USD in Isaac/PhysX.
The local plant makes policy iteration, reward shaping, falling, contact
timing, closure violations, and arm counter-swing observable; authoritative
contact dynamics and final validation remain in Isaac/PhysX.

## Modelled state

- 22 motor positions, velocities, and actions;
- optional free-root height, vertical velocity, forward velocity, torso
  roll/pitch, and angular rates;
- left/right heel and toe contact weights and load;
- the authored baseline walking phase;
- two leg closed-chain projections;
- two USD-sampled elbow linkages; and
- whole-body center-of-mass height, lateral excursion, and vertical velocity.

The knee is never treated as an independent open-chain shortcut.
`FourBarLeg` projects the adjacent hip-pitch and knee actuator coordinates
through the leg closure. Browser `180°` maps to policy/ROS `0 rad` at knee
lock, and the plant clamps both knees to `0`–`π rad`.

The elbow input is likewise the actuator, not the conveniently named passive
joint:

```text
LH/RH_Revolute41 motor
  → five passive revolute coordinates
  → three retained USD closure constraints
  → passive LH/RH_elbow_joint output
```

`ArmElbowLoop` is interpolated from the browser closure solver across the
validated motor range. It exposes the resulting passive elbow angle and
closure residual to training.

## Reward hierarchy

The reward is led by:

1. low torso roll/pitch and low torso angular rate;
2. low center-of-mass height/lateral variation and vertical COM speed;
3. a smooth reference-motion bias toward the hand-authored alternating walk;
4. target forward speed and heel/toe timing;
5. realistic contralateral arm swing; and
6. low energy, action variation, and leg/arm closure residual.

The baseline gait is a bias, not a hard script. PPO can depart from it when
that improves torso and COM stability. The actor mean is zero-initialized, so
the deterministic update-zero policy is exactly that baseline. Every live
preview is ranked on the same seed, and the final checkpoint restores the
best stable preview after all requested updates finish.

All ten top-level coefficients are configurable and serialized into each
policy as `config.rewardWeights`: torso, COM, gait/contact, speed, height, arm
swing, energy, smoothness, closure, and fall. Reward coefficients favor their
behavior; penalty coefficients suppress their error. Zero disables a term.
The checked-in behavior remains the default profile.

For a reproducible fine-tune, add:

```bash
--init-checkpoint artifacts/rl/experiments/<source>/checkpoint.pt
```

The checkpoint must match the 88-observation, 22-action dimensions and exact
joint order. Its deterministic corrected-plant rollout becomes protected
update zero before the requested optimization epochs begin.

## Dashboard training

Start the dashboard:

```bash
python3 web/serve.py 8000
```

Open <http://localhost:8000>, select **RL Lab**, configure updates, rollout
steps, parallel environments, epochs, and the expandable reward profile, then
start training. The same tuning controls are available in the Robot Sim
training drawer. Training accepts up to 10,000 updates; the process-control
endpoints accept mutations only from loopback.

Every PPO update atomically exports a deterministic live policy. With
**AUTO-REPLAY EACH UPDATE** enabled, **WATCH TRAINING LIVE** replays the newest
rollout on the complete browser USD and overlays reward, upright rate, torso
tilt, COM variation, speed, and falls. Final experiments are written beneath
`artifacts/rl/experiments/` and are intentionally ignored by Git.

Each experiment is also a persistent `dropbear-rl-session-v1`. The
`/api/rl/sessions` index survives dashboard restarts and exposes only
experiment-scoped artifacts. From the RL Lab, a stored run can be selected to:

- replay its exported policy on the browser USD;
- copy its exact training and reward parameters into the form; or
- warm-start a new run from its dimension- and joint-order-checked checkpoint.

Starting a new run never overwrites or deletes an older session. Session
configuration records `physicsBackend`; current local PPO runs are explicitly
`teaching-plant-v2`, not PhysX.

## Command line

```bash
python3 -m rl.train_walk \
  --updates 200 \
  --steps 256 \
  --envs 128 \
  --epochs 5 \
  --reward-torso 1.25 \
  --reward-com 0.75 \
  --reward-gait-contact 0.85 \
  --reward-speed 0.60 \
  --penalty-height 7.0 \
  --penalty-arm-swing 0.42 \
  --penalty-energy 0.012 \
  --penalty-smoothness 0.035 \
  --penalty-closure 250 \
  --penalty-fall 5 \
  --device cuda \
  --no-vertical-constraint \
  --arm-swing
```

This example performs exactly 1,000 policy optimization epochs.
The trainer writes a PyTorch checkpoint, browser policy JSON, and metrics
JSON. Use `--live-policy-out` to request an atomic intermediate rollout after
every update.

Run the deterministic same-seed acceptance comparison with:

```bash
python3 -m rl.validate_walk \
  artifacts/rl/experiments/<experiment>/policy.json \
  --reference-policy-out \
    artifacts/rl/experiments/<experiment>/authored-reference.json \
  --out artifacts/rl/experiments/<experiment>/validation.json \
  --expected-policy-epochs 1000
```

The validator checks exact epoch count, 22-motor order, free-root/arm-swing
configuration, forward target-speed tracking, closed-chain residuals, and
non-regression against the authored gait’s combined stability score. Both
policies remain playable in the browser for visual review.

## Tracked reference result

`web/assets/rl/dropbear-walk-reference.json` is the selected update `188` from
a completed 200-update, five-epoch-per-update CUDA experiment: exactly 1,000
additional policy epochs with seed `23`. Its deterministic free-root
evaluation remained upright for 100% of 7.98 seconds with no fall, averaged
`0.256 m/s`, held mean/peak torso tilt to `8.66°`/`11.02°`, and limited COM
height range to `0.044 m`.

Against the same-seed authored zero-residual walk, it improved reward by
`0.355`, upright time by `53.90` percentage points, mean torso tilt by `9.58°`,
peak tilt by `30.41°`, and COM height range by `0.217 m`. The full browser USD
review passed every rendered-motion gate and measured maximum sampled leg and
arm closure residuals of `0.465 mm` and `0.154 mm`.

The paired authored policy, numerical acceptance report, and rendered A/B
report are checked in beside the policy under `web/assets/rl/`.

This remains a research baseline. Before hardware passthrough, validate a
policy in the Isaac/PhysX Dropbear USD, replay the intended trajectory through
the ROS 2 controller SIL, and retain the existing fail-closed admission path.
