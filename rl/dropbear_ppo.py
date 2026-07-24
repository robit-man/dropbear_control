"""Constrained Dropbear walking environment and a compact PPO implementation.

This model is intentionally explicit about the two adjacent motor sources at
each knee. The passive links are solved from a four-bar loop before state is
returned to the policy; no open-chain knee shortcut is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import torch
from torch import nn
from torch.distributions import Normal


@dataclass(frozen=True)
class FourBarGeometry:
    ground: float = 0.105
    input_link: float = 0.075
    coupler: float = 0.145
    output_link: float = 0.115
    motor_offset: float = -0.18


class FourBarLeg:
    """Planar closed-chain knee driven by adjacent hip/knee motor coordinates."""

    def __init__(self, geometry: FourBarGeometry | None = None):
        self.g = geometry or FourBarGeometry()

    def project(self, hip_pitch: torch.Tensor, knee_motor: torch.Tensor) -> Dict[str, torch.Tensor]:
        # The hip-pitch motor is the input crank. The knee motor is the output
        # crank source; the coupler angle is reconstructed from the loop.
        a, b, c, d = self.g.input_link, self.g.coupler, self.g.output_link, self.g.ground
        theta = hip_pitch + self.g.motor_offset
        ax, ay = a * torch.cos(theta), a * torch.sin(theta)
        # Output crank endpoint. The motor coordinate is retained as the
        # measured source; its closure-corrected angle is solved below.
        phi = knee_motor
        bx = d + c * torch.cos(phi)
        by = c * torch.sin(phi)
        dx, dy = bx - ax, by - ay
        dist = torch.sqrt(dx * dx + dy * dy + 1e-9)
        # Circle intersection: point C is distance b from A and distance c
        # from the fixed output endpoint B. Clamp only the numerical domain;
        # residual still reports how far an impossible configuration is.
        cos_alpha = ((b * b + dist * dist - c * c) / (2 * b * dist)).clamp(-1.0, 1.0)
        alpha = torch.atan2(dy, dx)
        coupler = alpha + torch.acos(cos_alpha)
        cx, cy = ax + b * torch.cos(coupler), ay + b * torch.sin(coupler)
        # The closure constraint is the output-link length equation. Do not
        # use the endpoint distance itself as the residual (that is exactly
        # ``c`` for a valid loop); report only the geometric error.
        residual = (torch.sqrt((cx - bx) ** 2 + (cy - by) ** 2) - c).abs()
        knee_angle = torch.atan2(cy - ay, cx - ax) - theta
        return {"coupler_angle": coupler, "knee_angle": knee_angle, "closure_residual": residual}


class DropbearWalkEnv:
    """Vectorized, deterministic teaching plant for a 12-actuator walking policy."""

    def __init__(self, num_envs: int = 64, device: str = "cpu", dt: float = 0.02):
        self.device, self.num_envs, self.dt = torch.device(device), num_envs, dt
        self.leg = FourBarLeg()
        self.t = torch.zeros(num_envs, device=self.device)
        self.q = torch.zeros(num_envs, 12, device=self.device)
        self.dq = torch.zeros_like(self.q)
        self.target_speed = torch.full((num_envs,), 0.35, device=self.device)

    @property
    def observation_dim(self) -> int:
        return 12 * 2 + 4 + 1

    @property
    def action_dim(self) -> int:
        return 12

    def reset(self) -> torch.Tensor:
        self.t.zero_(); self.q.zero_(); self.dq.zero_()
        return self.observe()

    def reset_done(self, done: torch.Tensor) -> torch.Tensor:
        """Reset only terminated vector lanes, preserving other rollouts."""
        mask = done.to(torch.bool)
        self.t[mask] = 0
        self.q[mask] = 0
        self.dq[mask] = 0
        return self.observe()

    def _closure(self) -> Tuple[torch.Tensor, torch.Tensor]:
        left = self.leg.project(self.q[:, 5], self.q[:, 4])
        right = self.leg.project(self.q[:, 6], self.q[:, 7])
        knee = torch.stack((left["knee_angle"], right["knee_angle"]), dim=1)
        residual = torch.stack((left["closure_residual"], right["closure_residual"]), dim=1)
        return knee, residual

    def observe(self) -> torch.Tensor:
        knee, residual = self._closure()
        phase = self.t.mul(2 * math.pi * 1.2)
        return torch.cat((self.q, self.dq, knee, residual, torch.sin(phase)[:, None]), dim=1)

    def step(self, action: torch.Tensor):
        action = action.to(self.device).clamp(-1.0, 1.0)
        desired = action * 1.2
        # q[:, 4] and q[:, 7] are the left/right knee motor coordinates.
        # Zero radians is the 180° mechanical lock; negative knee motion is
        # physically inadmissible and is never presented to the plant.
        desired[:, 4] = (action[:, 4] + 1.0) * (math.pi / 2)
        desired[:, 7] = (action[:, 7] + 1.0) * (math.pi / 2)
        err = desired - self.q
        self.dq = (0.88 * self.dq + 8.0 * err).clamp(-8.0, 8.0)
        next_q = self.q + self.dt * self.dq
        self.q = next_q.clamp(-1.8, 1.8)
        self.q[:, 4] = next_q[:, 4].clamp(0.0, math.pi)
        self.q[:, 7] = next_q[:, 7].clamp(0.0, math.pi)
        self.t += self.dt
        obs = self.observe()
        _, residual = self._closure()
        speed = (self.dq[:, 5] - self.dq[:, 6]).mul(0.03)
        phase = self.t.mul(2 * math.pi * 1.2)
        gait = torch.sin(phase)
        reward = 1.0 - (speed - self.target_speed).square() - 0.02 * self.dq.square().mean(1)
        reward -= 250.0 * residual.square().mean(1)
        reward -= 0.02 * (action[:, 4].sub(gait)).square()
        done = (self.t >= 10.0) | (residual.max(1).values > 0.02)
        return obs, reward, done, {"closure_residual": residual.detach(), "speed": speed.detach()}


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs_dim, 256), nn.Tanh(), nn.Linear(256, 256), nn.Tanh())
        self.mu = nn.Linear(256, action_dim)
        self.value = nn.Linear(256, 1)
        self.log_std = nn.Parameter(torch.full((action_dim,), -0.7))

    def forward(self, obs):
        h = self.body(obs)
        return self.mu(h), self.value(h).squeeze(-1)


class PPO:
    def __init__(self, obs_dim: int, action_dim: int, device: str = "cpu"):
        self.device = torch.device(device)
        self.net = ActorCritic(obs_dim, action_dim).to(self.device)
        self.opt = torch.optim.Adam(self.net.parameters(), lr=3e-4)

    def act(self, obs):
        mu, value = self.net(obs)
        dist = Normal(mu, self.net.log_std.exp())
        raw = dist.sample()
        action = torch.tanh(raw)
        logp = dist.log_prob(raw).sum(-1) - torch.log(1 - action.square() + 1e-6).sum(-1)
        return action, logp.detach(), value.detach()

    def update(self, obs, actions, old_logp, returns, advantages, epochs: int = 4):
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-6)
        for _ in range(epochs):
            mu, value = self.net(obs)
            dist = Normal(mu, self.net.log_std.exp())
            raw = torch.atanh(actions.clamp(-0.999, 0.999))
            logp = dist.log_prob(raw).sum(-1) - torch.log(1 - actions.square() + 1e-6).sum(-1)
            ratio = (logp - old_logp).exp()
            policy = -torch.minimum(ratio * advantages, ratio.clamp(0.8, 1.2) * advantages).mean()
            loss = policy + 0.5 * (value - returns).square().mean() - 0.01 * dist.entropy().mean()
            self.opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(self.net.parameters(), 1.0); self.opt.step()
