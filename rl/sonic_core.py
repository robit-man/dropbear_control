"""CUDA-first, SONIC-shaped policy core for the Dropbear prototype.

This module deliberately implements the *runtime contract* needed to connect
Dropbear to GR00T WholeBodyControl: 90 robot observations, a 64-dimensional
motion token, and 22 motor residuals.  It is not NVIDIA's SONIC model and does
not claim compatibility with G1 weights.  The local trainer is a fast
teaching-plant smoke path; production policy training remains an Isaac Lab
job using the same versioned input/output contract.

CUDA is mandatory unless callers explicitly pass ``allow_cpu=True``.  This
keeps an accidental CPU training/deployment fallback from looking like a
production-ready run while still allowing deterministic unit tests.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Dict, Mapping, Sequence

import torch
from torch import nn
from torch.distributions import Normal

from .dropbear_ppo import ACTION_NAMES
from .sonic_action import action_contract


SONIC_SCHEMA = "dropbear-sonic-checkpoint-v1"
SESSION_SCHEMA = "dropbear-sonic-training-session-v1"
OBSERVATION_DIM = 90
MOTION_TOKEN_DIM = 64
ACTION_DIM = len(ACTION_NAMES)
RUNTIME_FREQUENCY_HZ = 50.0
CHECKPOINT_OUTPUT_CONTRACT = "normalized motor residual in [-1, 1]"
MOTION_TOKEN_PROMPT_COMPATIBLE = False


def _parse_device_indices(devices: str | Sequence[int] | None) -> tuple[int, ...]:
    if devices is None or devices == "":
        return ()
    if isinstance(devices, str):
        values = tuple(int(value.strip()) for value in devices.split(",") if value.strip())
    else:
        values = tuple(int(value) for value in devices)
    if len(set(values)) != len(values):
        raise ValueError("CUDA device indices must be unique")
    if any(value < 0 for value in values):
        raise ValueError("CUDA device indices must be non-negative")
    return values


@dataclass(frozen=True)
class DevicePlan:
    """Resolved CUDA/CPU execution and mixed-precision configuration."""

    primary: str
    cuda_indices: tuple[int, ...]
    device_names: tuple[str, ...]
    amp_enabled: bool
    amp_dtype: str
    data_parallel: bool
    allow_cpu: bool

    @property
    def torch_device(self) -> torch.device:
        return torch.device(self.primary)

    @classmethod
    def resolve(
        cls,
        device: str = "cuda",
        *,
        devices: str | Sequence[int] | None = None,
        allow_cpu: bool = False,
        amp: bool = True,
        amp_dtype: str = "bfloat16",
    ) -> "DevicePlan":
        requested = str(device).lower()
        selected = _parse_device_indices(devices)
        cuda_available = torch.cuda.is_available() and torch.cuda.device_count() > 0

        if requested in {"cuda", "auto"}:
            if not cuda_available:
                if not allow_cpu:
                    raise RuntimeError(
                        "CUDA is required for SONIC training/deployment; "
                        "use --allow-cpu only for tests"
                    )
                requested = "cpu"
            else:
                if not selected:
                    selected = (0,)
                count = torch.cuda.device_count()
                invalid = [index for index in selected if index >= count]
                if invalid:
                    raise ValueError(
                        f"CUDA device indices {invalid} exceed available count {count}"
                    )
                primary = f"cuda:{selected[0]}"
                names = tuple(torch.cuda.get_device_name(index) for index in selected)
                dtype = amp_dtype.lower()
                if dtype not in {"bfloat16", "float16"}:
                    raise ValueError("amp_dtype must be bfloat16 or float16")
                return cls(
                    primary=primary,
                    cuda_indices=selected,
                    device_names=names,
                    amp_enabled=bool(amp),
                    amp_dtype=dtype,
                    data_parallel=len(selected) > 1,
                    allow_cpu=bool(allow_cpu),
                )

        if requested.startswith("cuda:"):
            if devices not in (None, ""):
                raise ValueError("use either --device cuda:N or --devices, not both")
            try:
                selected_index = int(requested.split(":", 1)[1])
            except ValueError as error:
                raise ValueError(f"invalid CUDA device: {device}") from error
            return cls.resolve(
                "cuda",
                devices=(selected_index,),
                allow_cpu=allow_cpu,
                amp=amp,
                amp_dtype=amp_dtype,
            )

        if requested == "cpu":
            if not allow_cpu:
                raise RuntimeError(
                    "CPU mode is disabled by default; --allow-cpu is test-only"
                )
            return cls(
                primary="cpu",
                cuda_indices=(),
                device_names=("CPU test fallback",),
                amp_enabled=False,
                amp_dtype="float32",
                data_parallel=False,
                allow_cpu=True,
            )

        raise ValueError(f"unsupported device selection: {device}")

    def autocast(self):
        if not self.amp_enabled or self.torch_device.type != "cuda":
            return nullcontext()
        dtype = torch.bfloat16 if self.amp_dtype == "bfloat16" else torch.float16
        return torch.autocast(device_type="cuda", dtype=dtype)

    def as_manifest(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["cuda_required"] = True
        payload["cuda_runtime"] = torch.version.cuda
        payload["torch_version"] = torch.__version__
        return payload


def configure_cuda(plan: DevicePlan, seed: int) -> None:
    """Configure reproducible seeds and fast A100-class math kernels."""

    random.seed(int(seed))
    torch.manual_seed(int(seed))
    if plan.torch_device.type == "cuda":
        torch.cuda.manual_seed_all(int(seed))
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True


class SonicActorCritic(nn.Module):
    """Token-conditioned actor/critic with the Dropbear SONIC wire contract."""

    def __init__(
        self,
        observation_dim: int = OBSERVATION_DIM,
        token_dim: int = MOTION_TOKEN_DIM,
        action_dim: int = ACTION_DIM,
        hidden_dim: int = 256,
    ):
        super().__init__()
        self.observation_dim = int(observation_dim)
        self.token_dim = int(token_dim)
        self.action_dim = int(action_dim)
        self.hidden_dim = int(hidden_dim)
        self.observation_encoder = nn.Sequential(
            nn.LayerNorm(self.observation_dim),
            nn.Linear(self.observation_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
        )
        self.token_encoder = nn.Sequential(
            nn.LayerNorm(self.token_dim),
            nn.Linear(self.token_dim, hidden_dim // 2),
            nn.SiLU(),
            nn.Linear(hidden_dim // 2, hidden_dim // 2),
            nn.SiLU(),
        )
        self.fusion = nn.Sequential(
            nn.Linear(hidden_dim + hidden_dim // 2, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
        )
        self.mu = nn.Linear(hidden_dim, self.action_dim)
        self.value = nn.Linear(hidden_dim, 1)
        self.log_std = nn.Parameter(torch.full((self.action_dim,), -1.0))

        # Zero residual is the authored safe reference gait.
        nn.init.zeros_(self.mu.weight)
        nn.init.zeros_(self.mu.bias)

    def forward(
        self,
        observation: torch.Tensor,
        motion_token: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        if not torch.jit.is_tracing() and not torch.onnx.is_in_onnx_export():
            if observation.shape[-1] != self.observation_dim:
                raise ValueError(
                    f"observation dimension {observation.shape[-1]} != "
                    f"{self.observation_dim}"
                )
            if motion_token.shape[-1] != self.token_dim:
                raise ValueError(
                    f"motion token dimension {motion_token.shape[-1]} != "
                    f"{self.token_dim}"
                )
        obs_features = self.observation_encoder(observation)
        token_features = self.token_encoder(motion_token)
        fused = self.fusion(torch.cat((obs_features, token_features), dim=-1))
        mu = self.mu(fused)
        value = self.value(fused).squeeze(-1)
        return mu, value, self.log_std.expand_as(mu)


def unwrap_model(model: nn.Module) -> SonicActorCritic:
    unwrapped = model.module if isinstance(model, nn.DataParallel) else model
    if not isinstance(unwrapped, SonicActorCritic):
        raise TypeError(f"unexpected SONIC model type: {type(unwrapped)!r}")
    return unwrapped


def build_model(plan: DevicePlan, *, hidden_dim: int = 256) -> nn.Module:
    model: nn.Module = SonicActorCritic(hidden_dim=hidden_dim).to(plan.torch_device)
    if plan.data_parallel:
        model = nn.DataParallel(
            model,
            device_ids=list(plan.cuda_indices),
            output_device=plan.cuda_indices[0],
        )
    return model


class SonicPPO:
    """Compact AMP-aware PPO used to validate the token-conditioned contract."""

    def __init__(
        self,
        plan: DevicePlan,
        *,
        learning_rate: float = 3e-4,
        hidden_dim: int = 256,
    ):
        self.plan = plan
        self.net = build_model(plan, hidden_dim=hidden_dim)
        self.opt = torch.optim.Adam(self.net.parameters(), lr=float(learning_rate))
        self.scaler = torch.amp.GradScaler(
            "cuda",
            enabled=(
                plan.amp_enabled
                and plan.torch_device.type == "cuda"
                and plan.amp_dtype == "float16"
            ),
        )

    def act(
        self,
        observation: torch.Tensor,
        motion_token: torch.Tensor,
        *,
        deterministic: bool = False,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        with self.plan.autocast():
            mu, value, log_std = self.net(observation, motion_token)
        # Probability operations stay fp32 even when the MLP uses bf16/fp16.
        mu = mu.float()
        value = value.float()
        log_std = log_std.float()
        distribution = Normal(mu, log_std.exp())
        raw = mu if deterministic else distribution.sample()
        action = torch.tanh(raw)
        log_probability = distribution.log_prob(raw).sum(-1) - torch.log(
            1 - action.square() + 1e-6
        ).sum(-1)
        return action, log_probability.detach(), value.detach()

    def value(
        self,
        observation: torch.Tensor,
        motion_token: torch.Tensor,
    ) -> torch.Tensor:
        with self.plan.autocast():
            _, value, _ = self.net(observation, motion_token)
        return value.float()

    def update(
        self,
        observations: torch.Tensor,
        motion_tokens: torch.Tensor,
        actions: torch.Tensor,
        old_log_probability: torch.Tensor,
        returns: torch.Tensor,
        advantages: torch.Tensor,
        *,
        epochs: int = 4,
        batch_size: int = 2048,
    ) -> Dict[str, float]:
        advantages = (advantages - advantages.mean()) / (
            advantages.std(unbiased=False) + 1e-6
        )
        size = observations.shape[0]
        totals = {
            "loss": 0.0,
            "policy_loss": 0.0,
            "value_loss": 0.0,
            "entropy": 0.0,
            "approx_kl": 0.0,
        }
        batches = 0
        self.net.train()
        for _ in range(int(epochs)):
            order = torch.randperm(size, device=self.plan.torch_device)
            for start in range(0, size, int(batch_size)):
                index = order[start : start + int(batch_size)]
                with self.plan.autocast():
                    mu, value, log_std = self.net(
                        observations[index],
                        motion_tokens[index],
                    )
                mu = mu.float()
                value = value.float()
                distribution = Normal(mu, log_std.float().exp())
                raw = torch.atanh(actions[index].clamp(-0.999, 0.999))
                log_probability = distribution.log_prob(raw).sum(-1) - torch.log(
                    1 - actions[index].square() + 1e-6
                ).sum(-1)
                ratio = (log_probability - old_log_probability[index]).exp()
                policy_loss = -torch.minimum(
                    ratio * advantages[index],
                    ratio.clamp(0.8, 1.2) * advantages[index],
                ).mean()
                value_loss = (value - returns[index]).square().mean()
                entropy = distribution.entropy().sum(-1).mean()
                loss = policy_loss + 0.5 * value_loss - 0.01 * entropy

                self.opt.zero_grad(set_to_none=True)
                if self.scaler.is_enabled():
                    self.scaler.scale(loss).backward()
                    self.scaler.unscale_(self.opt)
                    nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                    self.scaler.step(self.opt)
                    self.scaler.update()
                else:
                    loss.backward()
                    nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                    self.opt.step()

                with torch.no_grad():
                    approximate_kl = (
                        old_log_probability[index] - log_probability
                    ).mean().abs()
                totals["loss"] += float(loss.detach())
                totals["policy_loss"] += float(policy_loss.detach())
                totals["value_loss"] += float(value_loss.detach())
                totals["entropy"] += float(entropy.detach())
                totals["approx_kl"] += float(approximate_kl.detach())
                batches += 1
        return {key: value / max(1, batches) for key, value in totals.items()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def model_state_cpu(model: nn.Module) -> Dict[str, torch.Tensor]:
    return {
        key: value.detach().cpu().clone()
        for key, value in unwrap_model(model).state_dict().items()
    }


def save_checkpoint(
    path: Path,
    model: nn.Module,
    *,
    config: Mapping[str, Any],
    reference: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SONIC_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model_state_cpu(model),
        "contract": {
            "observation_dim": OBSERVATION_DIM,
            "motion_token_dim": MOTION_TOKEN_DIM,
            "action_dim": ACTION_DIM,
            "joint_order": list(ACTION_NAMES),
            "output": CHECKPOINT_OUTPUT_CONTRACT,
            "frequency_hz": float(reference["frequency_hz"]),
            "action_semantics": action_contract(),
            "motion_token_semantics": {
                "source": str(reference["token_source"]),
                "prompt_router_compatible": MOTION_TOKEN_PROMPT_COMPATIBLE,
            },
        },
        "architecture": {
            "name": "dropbear-token-conditioned-actor-critic",
            "hidden_dim": unwrap_model(model).hidden_dim,
        },
        "config": dict(config),
        "reference": dict(reference),
        "metrics": dict(metrics),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)
    return payload


def validate_checkpoint_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate every inference-relevant checkpoint contract field.

    Artifact admission must compare the complete action transform, reference
    identity, cadence, joint order, and token semantics.  Merely matching a
    schema label is insufficient because a different scale vector or token
    source changes the physical command represented by the same network
    output.
    """

    if payload.get("schema") != SONIC_SCHEMA:
        raise ValueError(
            f"unsupported SONIC checkpoint schema: {payload.get('schema')}"
        )
    contract = payload.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("checkpoint contract is missing")
    reference = payload.get("reference")
    if not isinstance(reference, Mapping):
        raise ValueError("checkpoint reference metadata is missing")

    expected = {
        "observation_dim": OBSERVATION_DIM,
        "motion_token_dim": MOTION_TOKEN_DIM,
        "action_dim": ACTION_DIM,
        "joint_order": list(ACTION_NAMES),
        "output": CHECKPOINT_OUTPUT_CONTRACT,
        "frequency_hz": RUNTIME_FREQUENCY_HZ,
        "action_semantics": action_contract(),
    }
    for key, expected_value in expected.items():
        if contract.get(key) != expected_value:
            raise ValueError(f"checkpoint contract mismatch for {key}")

    if reference.get("frequency_hz") != RUNTIME_FREQUENCY_HZ:
        raise ValueError("checkpoint reference frequency must be exactly 50 Hz")
    if reference.get("joint_order") != list(ACTION_NAMES):
        raise ValueError("checkpoint reference joint order is not canonical")
    reference_digest = reference.get("sha256")
    if (
        not isinstance(reference_digest, str)
        or len(reference_digest) != 64
        or any(character not in "0123456789abcdef" for character in reference_digest)
    ):
        raise ValueError("checkpoint reference sha256 is missing or invalid")
    token_source = reference.get("token_source")
    if not isinstance(token_source, str) or not token_source:
        raise ValueError("checkpoint reference token source is missing")
    expected_token_semantics = {
        "source": token_source,
        "prompt_router_compatible": MOTION_TOKEN_PROMPT_COMPATIBLE,
    }
    if contract.get("motion_token_semantics") != expected_token_semantics:
        raise ValueError(
            "checkpoint motion-token semantics do not match the reference"
        )
    return dict(contract)


def load_checkpoint(
    path: Path,
    plan: DevicePlan,
) -> tuple[SonicActorCritic, Dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    validate_checkpoint_payload(payload)
    hidden_dim = int(payload.get("architecture", {}).get("hidden_dim", 256))
    model = SonicActorCritic(hidden_dim=hidden_dim)
    model.load_state_dict(payload["model"], strict=True)
    model.to(plan.torch_device)
    model.eval()
    return model, payload


def session_manifest(
    *,
    session_id: str,
    status: str,
    plan: DevicePlan,
    checkpoint: Path,
    reference: Mapping[str, Any],
    config: Mapping[str, Any],
    metrics: Mapping[str, Any],
    extra_artifacts: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256_file(checkpoint),
    }
    artifacts.update(dict(extra_artifacts or {}))
    return {
        "schema": SESSION_SCHEMA,
        "session_id": session_id,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime_mode": (
            "local CUDA compatibility validation; "
            "authoritative Isaac/PhysX run absent; not upstream SONIC"
        ),
        "device": plan.as_manifest(),
        "contract": {
            "observation_dim": OBSERVATION_DIM,
            "motion_token_dim": MOTION_TOKEN_DIM,
            "action_dim": ACTION_DIM,
            "joint_order": list(ACTION_NAMES),
            "output": CHECKPOINT_OUTPUT_CONTRACT,
            "frequency_hz": float(reference["frequency_hz"]),
            "action_semantics": action_contract(),
            "motion_token_semantics": {
                "source": str(reference["token_source"]),
                "prompt_router_compatible": MOTION_TOKEN_PROMPT_COMPATIBLE,
            },
        },
        "reference": dict(reference),
        "config": dict(config),
        "metrics": dict(metrics),
        "artifacts": artifacts,
    }
