import torch
import pytest

from rl.dropbear_ppo import (
    ACTION_NAMES,
    ARM_JOINT_NAMES,
    ArmElbowLoop,
    DropbearWalkEnv,
    FourBarLeg,
    PPO,
    RewardWeights,
)
from rl.train_walk import policy_selection_score
from rl.validate_walk import authored_reference_rollout


def test_four_bar_returns_finite_closure_and_knee_angle():
    leg = FourBarLeg()
    result = leg.project(torch.tensor([0.1, -0.2]), torch.tensor([0.15, -0.1]))
    assert torch.isfinite(result["knee_angle"]).all()
    assert torch.isfinite(result["closure_residual"]).all()
    assert (result["closure_residual"] >= 0).all()


def test_environment_observation_and_step_shapes():
    env = DropbearWalkEnv(num_envs=4)
    obs = env.reset()
    assert env.action_dim == 22
    assert env.observation_dim == 90
    assert len(ACTION_NAMES) == 22
    assert len(ARM_JOINT_NAMES) == 10
    assert obs.shape == (4, env.observation_dim)
    nxt, reward, done, info = env.step(torch.zeros(4, env.action_dim))
    assert nxt.shape == obs.shape
    assert reward.shape == (4,)
    assert done.shape == (4,)
    assert info["closure_residual"].shape == (4, 2)
    assert info["arm_closure_residual"].shape == (4, 2)
    assert info["physical_elbow_angle"].shape == (4, 2)
    assert info["torso_stability_error"].shape == (4,)
    assert info["com_stability_error"].shape == (4,)
    assert info["baseline_walk_bias"].shape == (4,)
    assert info["calf_manifold_error"].shape == (4,)
    assert info["com_height"].shape == (4,)
    assert info["gait_symmetry_reward"].shape == (4,)
    assert info["leg_swing_reward"].shape == (4,)
    assert info["lateral_tilt_error"].shape == (4,)
    assert info["dorsal_tilt_error"].shape == (4,)
    assert info["knee_contraction_error"].shape == (4,)
    assert info["reward_weights"]["armSwing"] == 0.35


def test_environment_applies_explicit_reference_as_residual_baseline():
    env = DropbearWalkEnv(num_envs=2)
    env.reset()
    reference = env._reference_motor_targets().clone()
    reference[:, 5] = 0.77
    reference[:, 6] = -0.68
    _, _, _, info = env.step(
        torch.zeros(2, env.action_dim),
        reference_override=reference,
    )
    assert torch.equal(info["reference_target"], reference)
    assert torch.equal(info["desired_target"], reference)
    assert torch.all(env.q[:, 5] > 0)
    assert torch.all(env.q[:, 6] < 0)


def test_environment_rejects_malformed_or_nonfinite_reference_override():
    env = DropbearWalkEnv(num_envs=2)
    env.reset()
    action = torch.zeros(2, env.action_dim)
    with pytest.raises(ValueError, match="reference_override must have shape"):
        env.step(action, reference_override=torch.zeros(env.action_dim))
    invalid = torch.zeros(2, env.action_dim)
    invalid[0, 0] = torch.nan
    with pytest.raises(ValueError, match="finite"):
        env.step(action, reference_override=invalid)


def test_arm_swing_penalty_weight_changes_the_actual_reward():
    default_env = DropbearWalkEnv(num_envs=2, seed=19)
    no_arm_penalty_env = DropbearWalkEnv(
        num_envs=2,
        seed=19,
        reward_weights=RewardWeights(arm_swing_penalty=0.0),
    )
    default_env.reset()
    no_arm_penalty_env.reset()
    action = torch.zeros(2, default_env.action_dim)
    _, default_reward, _, default_info = default_env.step(action)
    _, no_arm_reward, _, _ = no_arm_penalty_env.step(action)
    expected_difference = (
        default_info["reward_weights"]["armSwing"]
        * default_info["arm_swing_error"]
    )
    assert torch.all(expected_difference > 0)
    assert torch.allclose(
        no_arm_reward - default_reward,
        expected_difference,
        atol=1e-6,
    )


def test_initial_deterministic_policy_is_authored_gait_residual_zero():
    env = DropbearWalkEnv(num_envs=2)
    obs = env.reset()
    agent = PPO(env.observation_dim, env.action_dim)
    action, _, _ = agent.act(obs, deterministic=True)
    assert torch.equal(action, torch.zeros_like(action))


def test_knee_motor_coordinates_never_cross_lock():
    env = DropbearWalkEnv(num_envs=2)
    env.reset()
    negative = torch.zeros(2, env.action_dim)
    negative[:, 4] = -1
    negative[:, 7] = -1
    for _ in range(40):
        env.step(negative)
    assert (env.q[:, 4] >= 0).all()
    assert (env.q[:, 7] >= 0).all()


def test_elbow_motor_drives_passive_closed_loop_coordinate():
    loop = ArmElbowLoop(torch.device("cpu"))
    motor = torch.deg2rad(torch.tensor([-45.0, 0.0, 45.0]))
    state = loop.project(motor)
    assert state["elbow_angle"][0] < -0.1
    assert abs(float(state["elbow_angle"][1])) < 1e-6
    assert state["elbow_angle"][2] > 0.2
    assert float(state["closure_residual"].max()) == 0.0


def test_free_root_integrates_and_reports_falls():
    env = DropbearWalkEnv(num_envs=2, vertical_constraint=False)
    env.reset()
    initial_height = env.base_height.clone()
    for _ in range(10):
        _, _, _, info = env.step(torch.zeros(2, env.action_dim))
    assert not torch.equal(env.base_height, initial_height)
    assert info["vertical_constraint"] is False

    env.base_height[:] = 0.57
    _, _, done, info = env.step(torch.zeros(2, env.action_dim))
    assert done.all()
    assert info["fallen"].all()


def test_asynchronous_symmetry_uses_half_cycle_history():
    env = DropbearWalkEnv(num_envs=1)
    env.reset()
    ready = False
    for _ in range(env.symmetry_lag_steps + 2):
        _, _, _, info = env.step(torch.zeros(1, env.action_dim))
        ready = ready or bool(info["gait_symmetry_ready"][0])
    assert ready
    assert 0.0 <= float(info["gait_symmetry_reward"][0]) <= 1.0


def test_circle_profile_integrates_yaw_and_curved_root_path():
    env = DropbearWalkEnv(
        num_envs=1,
        target_speed=0.22,
        target_turn_rate=0.28,
        motion_profile="circle-walk",
    )
    env.reset()
    for _ in range(50):
        env.step(torch.zeros(1, env.action_dim))
    assert float(env.base_yaw[0]) > 0
    assert float(env.base_y[0]) > 0
    assert float(env.target_turn_rate[0]) == pytest.approx(0.28)


def test_source_derived_mujoco_backend_runs_gravity_and_force_contacts():
    pytest.importorskip("mujoco")
    env = DropbearWalkEnv(
        num_envs=1,
        physics_backend="mujoco-usd-proxy-v1",
        vertical_constraint=False,
    )
    env.reset()
    assert env.physics.model.nbody - 1 == 90
    assert env.physics.model.njnt == 84
    assert env.physics.model.neq == 27
    assert env.physics.model.nu == 22
    assert env.physics.mass_kg == pytest.approx(56.174599, abs=1e-5)
    observed_contact = False
    for _ in range(10):
        _, reward, done, info = env.step(torch.zeros(1, env.action_dim))
        observed_contact = observed_contact or bool(
            (info["contact_loads_kg"] > 0).any()
        )
    assert torch.isfinite(reward).all()
    assert observed_contact
    assert info["physics_backend"] == "mujoco-usd-proxy-v1"
    assert info["vertical_constraint"] is False


def test_source_derived_mujoco_backend_honors_vertical_guide():
    pytest.importorskip("mujoco")
    env = DropbearWalkEnv(
        num_envs=1,
        physics_backend="mujoco-usd-proxy-v1",
        vertical_constraint=True,
    )
    env.reset()
    for _ in range(10):
        env.step(torch.zeros(1, env.action_dim))
    assert float(env.base_height[0]) == pytest.approx(
        env.config.nominal_height_m,
        abs=1e-6,
    )
    assert float(env.base_vz[0]) == pytest.approx(0.0, abs=1e-6)


def test_policy_selection_prefers_stable_reference_speed():
    stable = {
        "meanReward": 2.7,
        "uprightPercent": 84.0,
        "meanSpeed": 0.34,
        "comHeightRangeM": 0.04,
        "comLateralPeakM": 0.01,
        "torsoTiltMeanDegrees": 8.0,
        "durationSeconds": 8.0,
    }
    unstable = {
        **stable,
        "meanReward": 3.0,
        "uprightPercent": 35.0,
        "meanSpeed": 0.62,
        "comHeightRangeM": 0.22,
        "torsoTiltMeanDegrees": 25.0,
        "durationSeconds": 4.0,
    }
    assert policy_selection_score(
        stable,
        target_speed=0.35,
        episode_seconds=8.0,
    ) > policy_selection_score(
        unstable,
        target_speed=0.35,
        episode_seconds=8.0,
    )


def test_authored_reference_exports_full_motor_and_root_frames():
    reference = authored_reference_rollout(
        {
            "groundTruth": {},
            "config": {
                "updates": 200,
                "ppoEpochs": 5,
                "seed": 23,
                "targetSpeed": 0.35,
                "episodeSeconds": 1.0,
                "verticalConstraint": False,
                "armSwing": True,
            },
        }
    )
    assert reference["jointOrder"] == list(ACTION_NAMES)
    assert reference["frames"]
    assert len(reference["frames"][0]["q"]) == 22
    assert set(reference["frames"][0]["base"]) == {
        "height",
        "x",
        "vx",
        "roll",
        "pitch",
        "y",
        "yaw",
        "yawRate",
    }
    assert reference["evaluation"]["closureMaxM"] < 1e-5
