"""Run a short PPO teaching job for the constrained Dropbear plant."""

import argparse
from pathlib import Path
import torch

from .dropbear_ppo import DropbearWalkEnv, PPO


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--updates", type=int, default=20)
    p.add_argument("--steps", type=int, default=256)
    p.add_argument("--envs", type=int, default=64)
    p.add_argument("--device", default="cpu")
    p.add_argument("--out", default="artifacts/rl/dropbear_ppo.pt")
    args = p.parse_args()
    env = DropbearWalkEnv(args.envs, args.device)
    agent = PPO(env.observation_dim, env.action_dim, args.device)
    obs = env.reset()
    for update in range(args.updates):
        rows = []
        for _ in range(args.steps):
            action, logp, value = agent.act(obs)
            nxt, reward, done, info = env.step(action)
            rows.append((obs, action, logp, value, reward))
            env.reset_done(done)
            obs = nxt.clone()
            obs[done] = env.observe()[done]
        states, actions, logps, values, rewards = zip(*rows)
        states, actions = torch.cat(states), torch.cat(actions)
        logps, values, rewards = torch.cat(logps), torch.cat(values), torch.stack(rewards)
        discounted = torch.zeros_like(rewards)
        running = torch.zeros(args.envs, device=env.device)
        for index in range(args.steps - 1, -1, -1):
            running = rewards[index] + 0.99 * running
            discounted[index] = running
        returns = discounted.reshape(-1)
        advantages = returns - values
        agent.update(states, actions, logps, returns, advantages)
        if update % 5 == 0 or update == args.updates - 1:
            print(f"update={update + 1}/{args.updates} reward={rewards.mean().item():.3f} closure={info['closure_residual'].max().item():.6f}m")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": agent.net.state_dict(), "obs_dim": env.observation_dim, "action_dim": env.action_dim}, args.out)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
