"""Deterministic motion-reference input for the local CUDA compatibility model.

Files use the dashboard policy frame shape (``q``, ``dq``, ``base`` and
``contactLoadsKg``) and may additionally contain a 64-value ``motionToken``.
When no upstream FSQ token is present, a deterministic 64-D compatibility
token is generated from the reference state.  That generated token validates
conditioning, transport and deployment plumbing; it is not represented as an
NVIDIA-trained SONIC universal token.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Sequence

import torch

from .dropbear_ppo import ACTION_NAMES, DropbearWalkEnv
from .sonic_core import (
    ACTION_DIM,
    MOTION_TOKEN_DIM,
    RUNTIME_FREQUENCY_HZ,
)


BASE_KEYS = ("height", "x", "vx", "roll", "pitch", "y", "yaw", "yawRate")
REFERENCE_SCHEMA = "dropbear-sonic-motion-reference-v1"
REFERENCE_SAMPLE_PERIOD_SECONDS = 1.0 / RUNTIME_FREQUENCY_HZ
REFERENCE_POSITION_LOWER_RAD = tuple(
    0.0 if index in (4, 7) else (
        -1.0471976 if index in (15, 20) else -math.pi
    )
    for index in range(ACTION_DIM)
)
REFERENCE_POSITION_UPPER_RAD = tuple(
    1.3089969 if index in (15, 20) else math.pi
    for index in range(ACTION_DIM)
)


class SonicReferenceDataset:
    """Validated, deterministic 50 Hz motor reference and motion tokens."""

    def __init__(
        self,
        q: torch.Tensor,
        dq: torch.Tensor,
        base: torch.Tensor,
        contacts: torch.Tensor,
        tokens: torch.Tensor | None = None,
        *,
        name: str = "reference",
        frequency_hz: float = 50.0,
        source: str = "memory",
    ):
        self.q = torch.as_tensor(q, dtype=torch.float32, device="cpu").contiguous()
        self.dq = torch.as_tensor(dq, dtype=torch.float32, device="cpu").contiguous()
        self.base = torch.as_tensor(base, dtype=torch.float32, device="cpu").contiguous()
        self.contacts = torch.as_tensor(
            contacts,
            dtype=torch.float32,
            device="cpu",
        ).contiguous()
        if self.q.ndim != 2 or self.q.shape[1] != ACTION_DIM:
            raise ValueError(f"reference q must have shape [frames, {ACTION_DIM}]")
        if self.dq.shape != self.q.shape:
            raise ValueError("reference dq must match q")
        if self.base.shape != (self.q.shape[0], len(BASE_KEYS)):
            raise ValueError(f"reference base must have shape [frames, {len(BASE_KEYS)}]")
        if self.contacts.shape != (self.q.shape[0], 4):
            raise ValueError("reference contacts must have shape [frames, 4]")
        if self.q.shape[0] < 2:
            raise ValueError("reference requires at least two frames")
        if not all(
            torch.isfinite(value).all()
            for value in (self.q, self.dq, self.base, self.contacts)
        ):
            raise ValueError("reference contains non-finite values")
        lower = torch.tensor(REFERENCE_POSITION_LOWER_RAD, dtype=torch.float32)
        upper = torch.tensor(REFERENCE_POSITION_UPPER_RAD, dtype=torch.float32)
        invalid_positions = (self.q < lower) | (self.q > upper)
        if invalid_positions.any():
            frame_index, joint_index = invalid_positions.nonzero()[0].tolist()
            joint_name = ACTION_NAMES[joint_index]
            raise ValueError(
                f"reference frame {frame_index} joint {joint_name} is outside "
                "the local integration envelope "
                f"[{lower[joint_index].item()}, {upper[joint_index].item()}] rad"
            )
        if (self.contacts < 0.0).any():
            raise ValueError("reference contact loads cannot be negative")
        self.frequency_hz = float(frequency_hz)
        if (
            not math.isfinite(self.frequency_hz)
            or self.frequency_hz != RUNTIME_FREQUENCY_HZ
        ):
            raise ValueError("SONIC references must be exactly 50 Hz")
        self.name = str(name)
        self.source = str(source)
        if tokens is None:
            self.tokens = self._compatibility_tokens()
            self.token_source = "deterministic-state-tokenizer-v1"
        else:
            self.tokens = torch.as_tensor(
                tokens,
                dtype=torch.float32,
                device="cpu",
            ).contiguous()
            if self.tokens.shape != (self.q.shape[0], MOTION_TOKEN_DIM):
                raise ValueError(
                    f"motion tokens must have shape [frames, {MOTION_TOKEN_DIM}]"
                )
            if not torch.isfinite(self.tokens).all():
                raise ValueError("motion tokens contain non-finite values")
            self.token_source = "file"
        self.sha256 = self._digest()

    def __len__(self) -> int:
        return int(self.q.shape[0])

    def _compatibility_tokens(self) -> torch.Tensor:
        # 22 q + 22 dq + 8 root + 4 contacts = 56 reference features.
        contacts = self.contacts / 56.22897759778425
        features = torch.cat(
            (
                self.q,
                0.10 * self.dq,
                self.base,
                contacts,
            ),
            dim=1,
        )
        tokens = torch.zeros(len(self), MOTION_TOKEN_DIM, dtype=torch.float32)
        tokens[:, : features.shape[1]] = torch.tanh(features)
        phase = torch.arange(len(self), dtype=torch.float32) / len(self)
        for harmonic in range(1, 5):
            offset = features.shape[1] + (harmonic - 1) * 2
            tokens[:, offset] = torch.sin(2 * torch.pi * harmonic * phase)
            tokens[:, offset + 1] = torch.cos(2 * torch.pi * harmonic * phase)
        return tokens

    def _digest(self) -> str:
        digest = hashlib.sha256()
        for tensor in (self.q, self.dq, self.base, self.contacts, self.tokens):
            digest.update(tensor.numpy().tobytes())
        digest.update(self.name.encode("utf-8"))
        digest.update(str(self.frequency_hz).encode("ascii"))
        return digest.hexdigest()

    def sample(
        self,
        indices: torch.Tensor | Sequence[int],
        device: torch.device | str,
    ) -> Dict[str, torch.Tensor]:
        index = torch.as_tensor(indices, dtype=torch.long, device="cpu") % len(self)
        return {
            "q": self.q[index].to(device, non_blocking=True),
            "dq": self.dq[index].to(device, non_blocking=True),
            "base": self.base[index].to(device, non_blocking=True),
            "contacts": self.contacts[index].to(device, non_blocking=True),
            "token": self.tokens[index].to(device, non_blocking=True),
        }

    def metadata(self) -> Dict[str, Any]:
        return {
            "schema": REFERENCE_SCHEMA,
            "name": self.name,
            "source": self.source,
            "frames": len(self),
            "frequency_hz": self.frequency_hz,
            "sample_period_seconds": REFERENCE_SAMPLE_PERIOD_SECONDS,
            "duration_seconds": len(self) / self.frequency_hz,
            "token_source": self.token_source,
            "sha256": self.sha256,
            "joint_order": list(ACTION_NAMES),
        }

    @classmethod
    def builtin(
        cls,
        *,
        frame_count: int = 400,
        frequency_hz: float = 50.0,
        target_speed: float = 0.26,
        target_turn_rate: float = 0.0,
        motion_profile: str = "gentle-forward",
    ) -> "SonicReferenceDataset":
        """Sample the repository's authored closed-loop baseline deterministically."""

        frame_count = int(frame_count)
        if frame_count < 2:
            raise ValueError("frame_count must be at least two")
        if (
            not math.isfinite(float(frequency_hz))
            or float(frequency_hz) != RUNTIME_FREQUENCY_HZ
        ):
            raise ValueError("SONIC references must be exactly 50 Hz")
        dt = 1.0 / float(frequency_hz)
        env = DropbearWalkEnv(
            num_envs=1,
            device="cpu",
            dt=dt,
            target_speed=target_speed,
            target_turn_rate=target_turn_rate,
            motion_profile=motion_profile,
            vertical_constraint=True,
            seed=0,
        )
        positions = []
        bases = []
        contacts = []
        with torch.no_grad():
            for index in range(frame_count):
                env.t[:] = index * dt
                target = env._reference_motor_targets().detach().cpu()[0]
                env.q[:] = target
                env._update_contact_state()
                positions.append(target)
                bases.append(
                    torch.tensor(
                        [
                            env.config.nominal_height_m,
                            index * dt * target_speed,
                            target_speed,
                            0.0,
                            0.0,
                            0.0,
                            index * dt * target_turn_rate,
                            target_turn_rate,
                        ],
                        dtype=torch.float32,
                    )
                )
                contacts.append(env.contact_loads_kg.detach().cpu()[0].clone())
        q = torch.stack(positions)
        dq = torch.empty_like(q)
        dq[1:] = (q[1:] - q[:-1]) / dt
        dq[0] = dq[-1]
        return cls(
            q,
            dq,
            torch.stack(bases),
            torch.stack(contacts),
            name=f"authored-{motion_profile}",
            frequency_hz=frequency_hz,
            source="DropbearWalkEnv._reference_motor_targets",
        )

    @classmethod
    def from_json(cls, path: Path) -> "SonicReferenceDataset":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read reference JSON: {error}") from error
        if not isinstance(payload, dict):
            raise ValueError("reference JSON must contain an object")
        if payload.get("schema") != REFERENCE_SCHEMA:
            raise ValueError(f"reference schema must be {REFERENCE_SCHEMA}")
        joint_order = payload.get("jointOrder")
        if joint_order != list(ACTION_NAMES):
            raise ValueError("reference joint order does not match Dropbear motor order")
        frequency = payload.get("sampleRateHz")
        if (
            isinstance(frequency, bool)
            or not isinstance(frequency, (int, float))
            or not math.isfinite(float(frequency))
            or float(frequency) != RUNTIME_FREQUENCY_HZ
        ):
            raise ValueError("SONIC references must be exactly 50 Hz")
        frames = payload.get("frames")
        if not isinstance(frames, list) or len(frames) < 2:
            raise ValueError("reference JSON must contain at least two frames")
        if payload.get("frameCount") != len(frames):
            raise ValueError(
                "reference frameCount does not match the number of frames"
            )

        q_rows: list[list[float]] = []
        dq_rows: list[list[float]] = []
        positions: list[list[float]] = []
        orientations: list[list[float]] = []
        contact_rows: list[list[float]] = []
        token_rows: list[list[float]] = []
        token_presence: list[bool] = []
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                raise ValueError(f"reference frame {index} must be an object")
            try:
                actual_time = float(frame["timeSec"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"reference frame {index} has no finite timeSec"
                ) from error
            expected_time = index * REFERENCE_SAMPLE_PERIOD_SECONDS
            if (
                not math.isfinite(actual_time)
                or abs(actual_time - expected_time) > 1e-7
            ):
                raise ValueError(
                    f"reference frame {index} is not on the exact 50 Hz timeline"
                )
            q_rows.append(
                cls._finite_row(
                    frame.get("jointPositionRad"),
                    ACTION_DIM,
                    f"reference frame {index} jointPositionRad",
                )
            )
            dq_rows.append(
                cls._finite_row(
                    frame.get("jointVelocityRadSec"),
                    ACTION_DIM,
                    f"reference frame {index} jointVelocityRadSec",
                )
            )
            position = cls._finite_row(
                frame.get("rootPositionM"),
                3,
                f"reference frame {index} rootPositionM",
            )
            if position[2] <= 0.0:
                raise ValueError(
                    f"reference frame {index} root height must be positive"
                )
            orientation = cls._finite_row(
                frame.get("rootOrientationWxyz"),
                4,
                f"reference frame {index} rootOrientationWxyz",
            )
            quaternion_norm = math.sqrt(sum(value * value for value in orientation))
            if abs(quaternion_norm - 1.0) > 1e-6:
                raise ValueError(
                    f"reference frame {index} root quaternion is not normalized"
                )
            positions.append(position)
            orientations.append(orientation)
            contact_rows.append(
                cls._finite_row(
                    frame.get("contactLoadsKg"),
                    4,
                    f"reference frame {index} contactLoadsKg",
                )
            )
            token_presence.append("motionToken" in frame)
            if "motionToken" in frame:
                token_rows.append(
                    cls._finite_row(
                        frame["motionToken"],
                        MOTION_TOKEN_DIM,
                        f"reference frame {index} motionToken",
                    )
                )
        if any(token_presence) and not all(token_presence):
            raise ValueError(
                "reference motionToken must be present on every frame or none"
            )

        dt = REFERENCE_SAMPLE_PERIOD_SECONDS
        eulers = [cls._quaternion_to_rpy(value) for value in orientations]
        base_rows = []
        for index, position in enumerate(positions):
            previous = max(0, index - 1)
            vx = (
                (position[0] - positions[previous][0]) / dt
                if index
                else 0.0
            )
            yaw_rate = (
                math.remainder(
                    eulers[index][2] - eulers[previous][2],
                    2.0 * math.pi,
                )
                / dt
                if index
                else 0.0
            )
            roll, pitch, yaw = eulers[index]
            base_rows.append(
                [
                    position[2],
                    position[0],
                    vx,
                    roll,
                    pitch,
                    position[1],
                    yaw,
                    yaw_rate,
                ]
            )
        source_metadata = payload.get("source")
        source_name = (
            source_metadata.get("name")
            if isinstance(source_metadata, dict)
            else None
        )
        return cls(
            torch.tensor(q_rows, dtype=torch.float32),
            torch.tensor(dq_rows, dtype=torch.float32),
            torch.tensor(base_rows, dtype=torch.float32),
            torch.tensor(contact_rows, dtype=torch.float32),
            (
                torch.tensor(token_rows, dtype=torch.float32)
                if all(token_presence)
                else None
            ),
            name=str(source_name or payload.get("name") or path.stem),
            frequency_hz=RUNTIME_FREQUENCY_HZ,
            source=str(path),
        )

    @staticmethod
    def _finite_row(
        value: Any,
        size: int,
        label: str,
    ) -> list[float]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"{label} must contain {size} finite values")
        try:
            result = [float(item) for item in value]
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{label} must contain {size} finite values"
            ) from error
        if len(result) != size or not all(math.isfinite(item) for item in result):
            raise ValueError(f"{label} must contain {size} finite values")
        return result

    @staticmethod
    def _quaternion_to_rpy(
        value: Sequence[float],
    ) -> tuple[float, float, float]:
        if len(value) != 4:
            raise ValueError("rootOrientationWxyz must contain four values")
        w, x, y, z = (float(item) for item in value)
        norm = math.sqrt(w * w + x * x + y * y + z * z)
        if norm < 1e-9:
            raise ValueError("root orientation quaternion has zero norm")
        w, x, y, z = (item / norm for item in (w, x, y, z))
        roll = math.atan2(
            2.0 * (w * x + y * z),
            1.0 - 2.0 * (x * x + y * y),
        )
        pitch_term = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(pitch_term)
        yaw = math.atan2(
            2.0 * (w * z + x * y),
            1.0 - 2.0 * (y * y + z * z),
        )
        return roll, pitch, yaw


def load_reference(
    path: Path | None,
    *,
    frame_count: int = 400,
    target_speed: float = 0.26,
    target_turn_rate: float = 0.0,
    motion_profile: str = "gentle-forward",
) -> SonicReferenceDataset:
    if path is None:
        return SonicReferenceDataset.builtin(
            frame_count=frame_count,
            target_speed=target_speed,
            target_turn_rate=target_turn_rate,
            motion_profile=motion_profile,
        )
    return SonicReferenceDataset.from_json(path)
