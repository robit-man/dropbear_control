import torch

from rl.dropbear_ppo import DropbearWalkEnv, FourBarLeg


def test_four_bar_returns_finite_closure_and_knee_angle():
    leg = FourBarLeg()
    result = leg.project(torch.tensor([0.1, -0.2]), torch.tensor([0.15, -0.1]))
    assert torch.isfinite(result["knee_angle"]).all()
    assert torch.isfinite(result["closure_residual"]).all()
    assert (result["closure_residual"] >= 0).all()


def test_environment_observation_and_step_shapes():
    env = DropbearWalkEnv(num_envs=4)
    obs = env.reset()
    assert obs.shape == (4, env.observation_dim)
    nxt, reward, done, info = env.step(torch.zeros(4, env.action_dim))
    assert nxt.shape == obs.shape
    assert reward.shape == (4,)
    assert done.shape == (4,)
    assert info["closure_residual"].shape == (4, 2)


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
