"""Dropbear walking teaching plant and compact PPO implementation.

The action/state ordering follows the browser USD motor map: twelve leg motors
followed by ten arm motors. The knee is never treated as an independent
open-chain shortcut; the adjacent hip/knee sources are projected through the
four-bar loop before rewards and observations are produced.

This remains a differentiable teaching plant, not a replacement for the
Dropbear USD running in Isaac/PhysX. Its free-root mode exists to make falling,
upright reward shaping, contact timing, and arm counter-swing observable during
local policy experiments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import torch
from torch import nn
from torch.distributions import Normal


LEG_JOINT_NAMES = (
    "left_outer_calf",
    "left_inner_calf",
    "right_inner_calf",
    "right_outer_calf",
    "left_knee",
    "left_hip_pitch",
    "right_hip_pitch",
    "right_knee",
    "left_hip_yaw",
    "left_hip_roll",
    "right_hip_roll",
    "right_hip_yaw",
)

ARM_JOINT_NAMES = (
    "left_shoulder_pitch",
    "left_shoulder_yaw",
    "left_shoulder_roll",
    "left_elbow_pitch",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_yaw",
    "right_shoulder_roll",
    "right_elbow_pitch",
    "right_wrist_roll",
)

ACTION_NAMES = LEG_JOINT_NAMES + ARM_JOINT_NAMES


@dataclass(frozen=True)
class FourBarGeometry:
    ground: float = 0.105
    input_link: float = 0.075
    coupler: float = 0.145
    output_link: float = 0.115
    motor_offset: float = -0.18


@dataclass(frozen=True)
class RewardWeights:
    """User-tunable coefficients for every top-level walking objective."""

    torso_stability: float = 1.25
    com_stability: float = 0.75
    gait_contact: float = 0.85
    speed_tracking: float = 0.60
    height_penalty: float = 7.0
    arm_swing_penalty: float = 0.42
    energy_penalty: float = 0.012
    smoothness_penalty: float = 0.035
    closure_penalty: float = 250.0
    fall_penalty: float = 5.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "torso": self.torso_stability,
            "com": self.com_stability,
            "gaitContact": self.gait_contact,
            "speed": self.speed_tracking,
            "height": self.height_penalty,
            "armSwing": self.arm_swing_penalty,
            "energy": self.energy_penalty,
            "smoothness": self.smoothness_penalty,
            "closure": self.closure_penalty,
            "fall": self.fall_penalty,
        }


@dataclass(frozen=True)
class WalkPlantConfig:
    vertical_constraint: bool = True
    arm_swing: bool = True
    target_speed: float = 0.35
    episode_seconds: float = 8.0
    # Sum of all 93 authored rigid-body masses in the verified source USD.
    mass_kg: float = 56.22897759778425
    nominal_height_m: float = 0.80
    nominal_com_height_m: float = 0.72
    contact_band_m: float = 0.012
    reward_weights: RewardWeights = RewardWeights()


class FourBarLeg:
    """Planar closed-chain knee driven by adjacent hip/knee motor coordinates."""

    def __init__(self, geometry: FourBarGeometry | None = None):
        self.g = geometry or FourBarGeometry()

    def project(self, hip_pitch: torch.Tensor, knee_motor: torch.Tensor) -> Dict[str, torch.Tensor]:
        a, b, c, d = self.g.input_link, self.g.coupler, self.g.output_link, self.g.ground
        theta = hip_pitch + self.g.motor_offset
        ax, ay = a * torch.cos(theta), a * torch.sin(theta)
        phi = knee_motor
        bx = d + c * torch.cos(phi)
        by = c * torch.sin(phi)
        dx, dy = bx - ax, by - ay
        dist = torch.sqrt(dx * dx + dy * dy + 1e-9)
        cos_alpha = ((b * b + dist * dist - c * c) / (2 * b * dist)).clamp(-1.0, 1.0)
        alpha = torch.atan2(dy, dx)
        coupler = alpha + torch.acos(cos_alpha)
        cx, cy = ax + b * torch.cos(coupler), ay + b * torch.sin(coupler)
        residual = (torch.sqrt((cx - bx) ** 2 + (cy - by) ** 2) - c).abs()
        knee_angle = torch.atan2(cy - ay, cx - ax) - theta
        return {
            "coupler_angle": coupler,
            "knee_angle": knee_angle,
            "closure_residual": residual,
        }


class ArmElbowLoop:
    """USD-sampled surrogate for the five-passive-joint elbow linkage.

    ``LH_Revolute41`` / ``RH_Revolute41`` are the motor coordinates. The
    visually named ``*_elbow_joint`` is passive and follows the three retained
    loop closures, so it must not be commanded directly.
    """

    def __init__(self, device: torch.device):
        self.device = device
        self.motor_samples = torch.tensor(
            [-1.0471976, -0.7853982, -0.5235988, -0.2617994, 0.0,
             0.2617994, 0.5235988, 0.7853982, 1.0471976, 1.3089969],
            device=device,
        )
        # Average of the left/right passive *_elbow_joint states produced by
        # the retained-closure browser solver at the sample motor positions.
        self.elbow_samples = torch.tensor(
            [-0.1813566, -0.1439713, -0.1020135, -0.0546698, 0.0,
             0.0651861, 0.1455621, 0.2471768, 0.3747834, 0.5180507],
            device=device,
        )

    def project(self, motor_angle: torch.Tensor) -> Dict[str, torch.Tensor]:
        clamped = motor_angle.clamp(
            float(self.motor_samples[0]),
            float(self.motor_samples[-1]),
        )
        upper = torch.searchsorted(self.motor_samples, clamped).clamp(
            1,
            self.motor_samples.numel() - 1,
        )
        lower = upper - 1
        x0 = self.motor_samples[lower]
        x1 = self.motor_samples[upper]
        y0 = self.elbow_samples[lower]
        y1 = self.elbow_samples[upper]
        blend = (clamped - x0) / (x1 - x0).clamp_min(1e-7)
        elbow_angle = y0 + blend * (y1 - y0)
        out_of_range = (
            torch.relu(self.motor_samples[0] - motor_angle)
            + torch.relu(motor_angle - self.motor_samples[-1])
        )
        closure_residual = out_of_range * 0.04
        return {
            "elbow_angle": elbow_angle,
            "closure_residual": closure_residual,
        }


class DropbearWalkEnv:
    """Vectorized 22-motor walking plant with optional free-root balance."""

    def __init__(
        self,
        num_envs: int = 64,
        device: str = "cpu",
        dt: float = 0.02,
        *,
        vertical_constraint: bool = True,
        arm_swing: bool = True,
        target_speed: float = 0.35,
        episode_seconds: float = 8.0,
        reward_weights: RewardWeights | None = None,
        seed: int = 7,
    ):
        self.device = torch.device(device)
        self.num_envs = int(num_envs)
        self.dt = float(dt)
        self.config = WalkPlantConfig(
            vertical_constraint=bool(vertical_constraint),
            arm_swing=bool(arm_swing),
            target_speed=float(target_speed),
            episode_seconds=float(episode_seconds),
            reward_weights=reward_weights or RewardWeights(),
        )
        torch.manual_seed(int(seed))
        if self.device.type == "cuda":
            torch.cuda.manual_seed_all(int(seed))

        self.leg = FourBarLeg()
        self.arm_elbow = ArmElbowLoop(self.device)
        self.t = torch.zeros(self.num_envs, device=self.device)
        self.q = torch.zeros(self.num_envs, len(ACTION_NAMES), device=self.device)
        self.dq = torch.zeros_like(self.q)
        self.prev_action = torch.zeros_like(self.q)
        self.target_speed = torch.full(
            (self.num_envs,),
            self.config.target_speed,
            device=self.device,
        )
        self.base_height = torch.zeros(self.num_envs, device=self.device)
        self.base_vz = torch.zeros_like(self.base_height)
        self.base_x = torch.zeros_like(self.base_height)
        self.base_vx = torch.zeros_like(self.base_height)
        self.base_roll = torch.zeros_like(self.base_height)
        self.base_pitch = torch.zeros_like(self.base_height)
        self.base_roll_rate = torch.zeros_like(self.base_height)
        self.base_pitch_rate = torch.zeros_like(self.base_height)
        self.contact_weights = torch.zeros(self.num_envs, 4, device=self.device)
        self.contact_loads_kg = torch.zeros_like(self.contact_weights)
        self.foot_heights = torch.zeros_like(self.contact_weights)
        self.com_height = torch.zeros_like(self.base_height)
        self.com_lateral = torch.zeros_like(self.base_height)
        self.com_vertical_speed = torch.zeros_like(self.base_height)
        self.previous_com_height = torch.zeros_like(self.base_height)
        self.episode_return = torch.zeros_like(self.base_height)
        self.episode_steps = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)

        center = torch.zeros(len(ACTION_NAMES), device=self.device)
        scale = torch.tensor(
            [
                # The adjacent inner/outer X8s operate on the retained
                # three-point calf/ankle loop. Keep learned residual authority
                # small enough to stay on that physically closed manifold.
                0.10, 0.10, 0.10, 0.10,  # calf X8 sources
                0.55, 0.62, 0.62, 0.55,  # knee and hip pitch
                0.30, 0.35, 0.35, 0.30,  # hip yaw / roll
                0.82, 0.32, 0.42, 0.36, 0.38,  # left arm
                0.82, 0.32, 0.42, 0.36, 0.38,  # right arm
            ],
            device=self.device,
        )
        center[4] = 0.55
        center[7] = 0.55
        center[15] = 0.44
        center[20] = 0.44
        self.action_center = center
        self.action_scale = scale
        self.reset()

    @property
    def observation_dim(self) -> int:
        # q + dq + leg and arm closed-chain state + base state + contacts +
        # phase sin/cos + previous action.
        return len(ACTION_NAMES) * 3 + 8 + 8 + 4 + 2

    @property
    def action_dim(self) -> int:
        return len(ACTION_NAMES)

    def _reset_mask(self, mask: torch.Tensor) -> None:
        count = int(mask.sum().item())
        if count == 0:
            return
        lanes = torch.arange(self.num_envs, device=self.device, dtype=torch.float32)
        spread = lanes / max(1, self.num_envs - 1) - 0.5
        self.t[mask] = (lanes[mask] % 8) * (1.0 / 8.0) / 1.2
        self.q[mask] = 0
        self.q[mask, 4] = 0.36
        self.q[mask, 7] = 0.36
        self.q[mask, 15] = 0.42
        self.q[mask, 20] = 0.42
        self.dq[mask] = 0
        self.prev_action[mask] = 0
        self.base_height[mask] = self.config.nominal_height_m
        self.base_vz[mask] = 0
        self.base_x[mask] = 0
        self.base_vx[mask] = 0
        self.base_roll[mask] = spread[mask] * 0.035
        self.base_pitch[mask] = -spread[mask] * 0.025
        self.base_roll_rate[mask] = 0
        self.base_pitch_rate[mask] = 0
        self.contact_weights[mask] = 0
        self.contact_loads_kg[mask] = 0
        self.foot_heights[mask] = 0
        self.com_height[mask] = self.config.nominal_com_height_m
        self.previous_com_height[mask] = self.config.nominal_com_height_m
        self.com_lateral[mask] = 0
        self.com_vertical_speed[mask] = 0
        self.episode_return[mask] = 0
        self.episode_steps[mask] = 0

    def reset(self) -> torch.Tensor:
        mask = torch.ones(self.num_envs, dtype=torch.bool, device=self.device)
        self._reset_mask(mask)
        self._update_contact_state()
        return self.observe()

    def reset_done(self, done: torch.Tensor) -> torch.Tensor:
        self._reset_mask(done.to(torch.bool))
        self._update_contact_state()
        return self.observe()

    def _closure(self) -> Tuple[torch.Tensor, torch.Tensor]:
        left = self.leg.project(self.q[:, 5], self.q[:, 4])
        right = self.leg.project(self.q[:, 6], self.q[:, 7])
        knee = torch.stack((left["knee_angle"], right["knee_angle"]), dim=1)
        residual = torch.stack(
            (left["closure_residual"], right["closure_residual"]),
            dim=1,
        )
        return knee, residual

    def _arm_closure(self) -> Tuple[torch.Tensor, torch.Tensor]:
        left = self.arm_elbow.project(self.q[:, 15])
        right = self.arm_elbow.project(self.q[:, 20])
        elbow = torch.stack((left["elbow_angle"], right["elbow_angle"]), dim=1)
        residual = torch.stack(
            (left["closure_residual"], right["closure_residual"]),
            dim=1,
        )
        return elbow, residual

    def _phase(self) -> torch.Tensor:
        return self.t.mul(2 * math.pi * 1.2)

    def _foot_geometry(self) -> Tuple[torch.Tensor, torch.Tensor]:
        thigh = 0.43
        shank = 0.43
        half_foot = 0.10
        hip = torch.stack((self.q[:, 5], self.q[:, 6]), dim=1)
        knee = torch.stack((self.q[:, 4], self.q[:, 7]), dim=1)
        calf = torch.stack(
            (
                (self.q[:, 0] + self.q[:, 1]) * 0.5,
                (self.q[:, 2] + self.q[:, 3]) * 0.5,
            ),
            dim=1,
        )
        leg_z = thigh * torch.cos(hip) + shank * torch.cos(hip - knee)
        foot_center_z = self.base_height[:, None] - leg_z
        foot_pitch = hip - 0.45 * knee + 0.30 * calf
        heel_z = foot_center_z - half_foot * torch.sin(foot_pitch)
        toe_z = foot_center_z + half_foot * torch.sin(foot_pitch)
        heights = torch.stack(
            (heel_z[:, 0], toe_z[:, 0], heel_z[:, 1], toe_z[:, 1]),
            dim=1,
        )

        foot_center_x = (
            self.base_x[:, None]
            + thigh * torch.sin(hip)
            + shank * torch.sin(hip - knee)
        )
        heel_x = foot_center_x - half_foot * torch.cos(foot_pitch)
        toe_x = foot_center_x + half_foot * torch.cos(foot_pitch)
        positions_x = torch.stack(
            (heel_x[:, 0], toe_x[:, 0], heel_x[:, 1], toe_x[:, 1]),
            dim=1,
        )
        return heights, positions_x

    def _update_contact_state(self) -> torch.Tensor:
        heights, positions_x = self._foot_geometry()
        band = self.config.contact_band_m
        weights = torch.sigmoid((band - heights) / 0.006)
        total = weights.sum(1, keepdim=True)
        loads = torch.where(
            total > 0.05,
            weights / total.clamp_min(1e-6) * self.config.mass_kg,
            torch.zeros_like(weights),
        )
        self.foot_heights = heights
        self.contact_weights = weights
        self.contact_loads_kg = loads
        return positions_x

    def observe(self) -> torch.Tensor:
        knee, residual = self._closure()
        elbow, arm_residual = self._arm_closure()
        phase = self._phase()
        base = torch.stack(
            (
                self.base_height - self.config.nominal_height_m,
                self.base_vz,
                self.base_roll,
                self.base_pitch,
                self.base_roll_rate,
                self.base_pitch_rate,
                self.base_vx,
                self.target_speed,
            ),
            dim=1,
        )
        contacts = self.contact_loads_kg / self.config.mass_kg
        return torch.cat(
            (
                self.q,
                self.dq,
                knee,
                residual,
                elbow,
                arm_residual,
                base,
                contacts,
                torch.sin(phase)[:, None],
                torch.cos(phase)[:, None],
                self.prev_action,
            ),
            dim=1,
        )

    def _integrate_root(self, positions_x: torch.Tensor) -> None:
        left_support = self.contact_weights[:, :2].mean(1)
        right_support = self.contact_weights[:, 2:].mean(1)
        total_support = self.contact_weights.sum(1)

        stance_denom = (left_support + right_support).clamp_min(0.1)
        stance_drive = -(
            self.dq[:, 5] * left_support + self.dq[:, 6] * right_support
        ) / stance_denom
        hip_reference, knee_reference, _ = self._teaching_targets()
        reference_alignment = torch.exp(
            -3.0 * (self.q[:, [5, 6]] - hip_reference).square().mean(1)
            -2.0 * (self.q[:, [4, 7]] - knee_reference).square().mean(1)
        )
        forward_acc = (
            0.35 * stance_drive
            + 0.90 * self.target_speed * reference_alignment
            - 0.90 * self.base_vx
            - 0.25 * self.base_pitch
        )
        self.base_vx = (self.base_vx + self.dt * forward_acc).clamp(-1.5, 1.8)
        self.base_x += self.dt * self.base_vx

        if self.config.vertical_constraint:
            self.base_height.fill_(self.config.nominal_height_m)
            self.base_vz.zero_()
        else:
            support_ratio = (total_support / 2.0).clamp(0.0, 1.30)
            extension_drive = -0.06 * (
                self.dq[:, 4] * left_support + self.dq[:, 7] * right_support
            ) / stance_denom
            vertical_acc = (
                9.80665 * (support_ratio - 1.0)
                + extension_drive
                - 2.7 * self.base_vz
            )
            self.base_vz = (self.base_vz + self.dt * vertical_acc).clamp(-3.0, 2.0)
            self.base_height += self.dt * self.base_vz

        load_balance = (right_support - left_support) / stance_denom
        hip_roll_moment = self.q[:, 9] - self.q[:, 10]
        arm_roll_moment = self.q[:, 14] - self.q[:, 19]
        roll_acc = (
            3.2 * load_balance
            + 1.6 * hip_roll_moment
            + 0.55 * arm_roll_moment
            - 1.65 * self.base_roll_rate
            - 1.80 * self.base_roll
        )

        weighted_x = (positions_x * self.contact_weights).sum(1)
        support_x = weighted_x / total_support.clamp_min(0.1)
        support_arm = support_x - self.base_x
        shoulder_mean = 0.5 * (self.q[:, 12] + self.q[:, 17])
        hip_mean = 0.5 * (self.q[:, 5] + self.q[:, 6])
        pitch_acc = (
            4.2 * support_arm
            - 0.95 * hip_mean
            - 0.35 * shoulder_mean
            - 1.85 * self.base_pitch_rate
            - 1.75 * self.base_pitch
        )

        self.base_roll_rate = (
            self.base_roll_rate + self.dt * roll_acc
        ).clamp(-3.5, 3.5)
        self.base_pitch_rate = (
            self.base_pitch_rate + self.dt * pitch_acc
        ).clamp(-3.5, 3.5)
        self.base_roll += self.dt * self.base_roll_rate
        self.base_pitch += self.dt * self.base_pitch_rate

    def _teaching_targets(self) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        phase = self._phase()
        gait = torch.sin(phase)
        left_swing = torch.relu(gait)
        right_swing = torch.relu(-gait)
        hip_target = torch.stack((0.45 * gait, -0.45 * gait), dim=1)
        knee_target = torch.stack(
            (0.12 + 0.62 * left_swing, 0.12 + 0.62 * right_swing),
            dim=1,
        )
        contact_target = torch.stack(
            (torch.sigmoid(-5.0 * gait), torch.sigmoid(5.0 * gait)),
            dim=1,
        )
        return hip_target, knee_target, contact_target

    def _reference_motor_targets(self) -> torch.Tensor:
        """Return the authored walking trajectory used as a policy prior."""
        hip_target, knee_target, _ = self._teaching_targets()
        phase = self._phase()
        gait = torch.sin(phase)
        left_swing = torch.relu(gait)
        right_swing = torch.relu(-gait)
        reference = self.action_center[None, :].repeat(self.num_envs, 1)
        reference[:, [5, 6]] = hip_target
        reference[:, [4, 7]] = knee_target
        reference[:, 0] = 0.06 + 0.16 * left_swing
        reference[:, 1] = 0.06 + 0.14 * left_swing
        reference[:, 2] = 0.06 + 0.14 * right_swing
        reference[:, 3] = 0.06 + 0.16 * right_swing
        reference[:, 9] = -0.07 * gait
        reference[:, 10] = 0.07 * gait
        reference[:, 12] = -0.52 * gait
        reference[:, 17] = 0.52 * gait
        reference[:, 15] = 0.44
        reference[:, 20] = 0.44
        return reference

    def _update_center_of_mass(self) -> None:
        """Approximate whole-body COM from the free root and limb configuration."""
        knee_mean = self.q[:, [4, 7]].mean(1)
        hip_mean = self.q[:, [5, 6]].mean(1)
        shoulder_mean = self.q[:, [12, 17]].mean(1)
        arm_roll_difference = self.q[:, 14] - self.q[:, 19]
        hip_roll_difference = self.q[:, 9] - self.q[:, 10]
        next_height = (
            self.base_height
            - 0.08
            - 0.024 * (knee_mean - 0.36).square()
            - 0.008 * shoulder_mean.square()
        )
        self.com_vertical_speed = (
            next_height - self.previous_com_height
        ) / max(self.dt, 1e-6)
        self.previous_com_height = next_height.detach().clone()
        self.com_height = next_height
        self.com_lateral = (
            0.11 * torch.sin(self.base_roll)
            + 0.018 * hip_roll_difference
            + 0.008 * arm_roll_difference
            + 0.012 * torch.sin(self.base_pitch) * hip_mean
        )

    def step(self, action: torch.Tensor):
        action = action.to(self.device).clamp(-1.0, 1.0)
        # PPO controls a residual around the proven browser walking sequence.
        # This makes the existing gait a useful prior while leaving enough
        # authority to alter every motor for balance and COM stabilization.
        reference = self._reference_motor_targets()
        desired = reference + action * self.action_scale * 0.62
        if not self.config.arm_swing:
            desired[:, 12:22] = 0
            desired[:, 15] = 0.42
            desired[:, 20] = 0.42

        err = desired - self.q
        self.dq = (0.86 * self.dq + 7.5 * err).clamp(-8.0, 8.0)
        next_q = self.q + self.dt * self.dq
        self.q = next_q.clamp(-1.8, 1.8)
        self.q[:, 4] = next_q[:, 4].clamp(0.0, math.pi)
        self.q[:, 7] = next_q[:, 7].clamp(0.0, math.pi)
        self.q[:, 15] = next_q[:, 15].clamp(0.0, 1.35)
        self.q[:, 20] = next_q[:, 20].clamp(0.0, 1.35)

        positions_x = self._update_contact_state()
        self._integrate_root(positions_x)
        self.t += self.dt
        self.episode_steps += 1
        self._update_contact_state()
        self._update_center_of_mass()

        _, residual = self._closure()
        physical_elbow, arm_residual = self._arm_closure()
        hip_target, knee_target, contact_target = self._teaching_targets()
        actual_contact = torch.stack(
            (
                self.contact_weights[:, :2].amax(1),
                self.contact_weights[:, 2:].amax(1),
            ),
            dim=1,
        )
        gait_error = (
            (self.q[:, [5, 6]] - hip_target).square().mean(1)
            + 0.8 * (self.q[:, [4, 7]] - knee_target).square().mean(1)
            + 0.25 * (actual_contact - contact_target).square().mean(1)
        )
        calf_reference = self._reference_motor_targets()[:, :4]
        calf_manifold_error = (
            self.q[:, :4] - calf_reference
        ).square().mean(1)
        gait_error = gait_error + 1.4 * calf_manifold_error

        phase = self._phase()
        arm_target = torch.stack(
            (
                -0.52 * torch.sin(phase),
                0.52 * torch.sin(phase),
            ),
            dim=1,
        )
        shoulder_error = (self.q[:, [12, 17]] - arm_target).square().mean(1)
        elbow_error = (physical_elbow - 0.11).square().mean(1)
        arm_quiet_error = self.q[:, [13, 14, 16, 18, 19, 21]].square().mean(1)
        arm_error = shoulder_error + 0.35 * elbow_error + 0.15 * arm_quiet_error
        if not self.config.arm_swing:
            arm_error = torch.zeros_like(arm_error)

        # Core attitude is the primary learned objective. The root must remain
        # upright without relying on the optional vertical guide.
        torso_stability_error = (
            3.6 * self.base_roll.square()
            + 3.0 * self.base_pitch.square()
            + 0.18 * self.base_roll_rate.square()
            + 0.18 * self.base_pitch_rate.square()
        )
        # Keep whole-body COM quiet while allowing the periodic motion needed
        # for a step. Lateral drift and vertical COM velocity are both costly.
        com_stability_error = (
            26.0
            * (self.com_height - self.config.nominal_com_height_m).square()
            + 18.0 * self.com_lateral.square()
            + 0.35 * self.com_vertical_speed.square()
        )
        height_error = (self.base_height - self.config.nominal_height_m).square()
        speed_error = (self.base_vx - self.target_speed).square()
        energy = self.dq.square().mean(1)
        smoothness = (action - self.prev_action).square().mean(1)

        # The authored alternating walk is a reference-motion bias. PPO may
        # depart from it to stabilize the torso and COM, but receives a smooth
        # advantage for preserving its contact and swing timing.
        torso_stability_reward = torch.exp(-torso_stability_error)
        com_stability_reward = torch.exp(-com_stability_error)
        baseline_walk_bias = torch.exp(-1.4 * gait_error)
        velocity_reward = torch.exp(-2.2 * speed_error)
        weights = self.config.reward_weights
        reward = (
            weights.torso_stability * torso_stability_reward
            + weights.com_stability * com_stability_reward
            + weights.gait_contact * baseline_walk_bias
            + weights.speed_tracking * velocity_reward
            - weights.height_penalty * height_error
            - weights.arm_swing_penalty * arm_error
            - weights.energy_penalty * energy
            - weights.smoothness_penalty * smoothness
            - weights.closure_penalty * residual.square().mean(1)
            - weights.closure_penalty * arm_residual.square().mean(1)
        )
        fallen = (
            (self.base_height < 0.58)
            | (self.base_roll.abs() > 0.72)
            | (self.base_pitch.abs() > 0.72)
        )
        timeout = self.t >= self.config.episode_seconds
        done = (
            fallen
            | timeout
            | (residual.max(1).values > 0.02)
            | (arm_residual.max(1).values > 0.02)
        )
        reward = reward - weights.fall_penalty * fallen.float()
        upright = (
            (self.base_height > 0.68)
            & (self.base_roll.abs() < 0.28)
            & (self.base_pitch.abs() < 0.32)
        )
        self.episode_return += reward
        self.prev_action = action.detach().clone()

        obs = self.observe()
        info = {
            "closure_residual": residual.detach(),
            "arm_closure_residual": arm_residual.detach(),
            "physical_elbow_angle": physical_elbow.detach(),
            "speed": self.base_vx.detach(),
            "base_height": self.base_height.detach(),
            "base_roll": self.base_roll.detach(),
            "base_pitch": self.base_pitch.detach(),
            "torso_stability_error": torso_stability_error.detach(),
            "com_height": self.com_height.detach(),
            "com_lateral": self.com_lateral.detach(),
            "com_vertical_speed": self.com_vertical_speed.detach(),
            "com_stability_error": com_stability_error.detach(),
            "baseline_walk_bias": baseline_walk_bias.detach(),
            "contacts": self.contact_weights.detach(),
            "contact_loads_kg": self.contact_loads_kg.detach(),
            "upright": upright.detach(),
            "fallen": fallen.detach(),
            "arm_swing_error": arm_error.detach(),
            "gait_error": gait_error.detach(),
            "calf_manifold_error": calf_manifold_error.detach(),
            "vertical_constraint": self.config.vertical_constraint,
            "reward_weights": weights.as_dict(),
        }
        return obs, reward, done, info


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(obs_dim, 256),
            nn.Tanh(),
            nn.Linear(256, 256),
            nn.Tanh(),
        )
        self.mu = nn.Linear(256, action_dim)
        self.value = nn.Linear(256, 1)
        # Residual control must begin at the authored working gait. A random
        # policy mean would corrupt that reference before PPO has learned
        # anything, so update zero deterministically produces zero residuals.
        nn.init.zeros_(self.mu.weight)
        nn.init.zeros_(self.mu.bias)
        self.log_std = nn.Parameter(torch.full((action_dim,), -1.0))

    def forward(self, obs):
        h = self.body(obs)
        return self.mu(h), self.value(h).squeeze(-1)


class PPO:
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        device: str = "cpu",
        *,
        learning_rate: float = 3e-4,
    ):
        self.device = torch.device(device)
        self.net = ActorCritic(obs_dim, action_dim).to(self.device)
        self.opt = torch.optim.Adam(self.net.parameters(), lr=learning_rate)

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        mu, value = self.net(obs)
        dist = Normal(mu, self.net.log_std.exp())
        raw = mu if deterministic else dist.sample()
        action = torch.tanh(raw)
        logp = dist.log_prob(raw).sum(-1) - torch.log(
            1 - action.square() + 1e-6
        ).sum(-1)
        return action, logp.detach(), value.detach()

    def update(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        old_logp: torch.Tensor,
        returns: torch.Tensor,
        advantages: torch.Tensor,
        *,
        epochs: int = 4,
        batch_size: int = 2048,
    ) -> Dict[str, float]:
        advantages = (advantages - advantages.mean()) / (
            advantages.std(unbiased=False) + 1e-6
        )
        size = obs.shape[0]
        metrics = {"loss": 0.0, "policy": 0.0, "value": 0.0, "entropy": 0.0, "kl": 0.0}
        batches = 0
        for _ in range(int(epochs)):
            order = torch.randperm(size, device=self.device)
            for start in range(0, size, int(batch_size)):
                index = order[start : start + int(batch_size)]
                mu, value = self.net(obs[index])
                dist = Normal(mu, self.net.log_std.exp())
                raw = torch.atanh(actions[index].clamp(-0.999, 0.999))
                logp = dist.log_prob(raw).sum(-1) - torch.log(
                    1 - actions[index].square() + 1e-6
                ).sum(-1)
                ratio = (logp - old_logp[index]).exp()
                clipped = ratio.clamp(0.8, 1.2)
                policy_loss = -torch.minimum(
                    ratio * advantages[index],
                    clipped * advantages[index],
                ).mean()
                value_loss = (value - returns[index]).square().mean()
                entropy = dist.entropy().sum(-1).mean()
                loss = policy_loss + 0.5 * value_loss - 0.01 * entropy
                self.opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                self.opt.step()

                with torch.no_grad():
                    kl = (old_logp[index] - logp).mean().abs()
                metrics["loss"] += float(loss.detach())
                metrics["policy"] += float(policy_loss.detach())
                metrics["value"] += float(value_loss.detach())
                metrics["entropy"] += float(entropy.detach())
                metrics["kl"] += float(kl.detach())
                batches += 1
        return {key: value / max(1, batches) for key, value in metrics.items()}
