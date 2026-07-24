import math
from pathlib import Path

import pytest

from integrations.gr00t_wbc import ACTION_NAMES, UpstreamSonicActionAdapter


ROOT = Path(__file__).resolve().parents[2]


def test_upstream_action_adapter_implements_embodiment_formula():
    adapter = UpstreamSonicActionAdapter()
    zero = adapter.decode([0.0] * len(ACTION_NAMES))
    assert zero == pytest.approx(adapter.centers)
    positive = adapter.decode([1.0] * len(ACTION_NAMES))
    assert positive[4] == pytest.approx(1.10)
    assert positive[7] == pytest.approx(1.10)
    assert all(math.isfinite(value) for value in positive)


def test_upstream_action_adapter_clamps_actions_and_knee_limits():
    adapter = UpstreamSonicActionAdapter()
    positive = adapter.decode([100.0] * len(ACTION_NAMES))
    negative = adapter.decode([-100.0] * len(ACTION_NAMES))
    assert positive == adapter.decode([1.0] * len(ACTION_NAMES))
    assert negative == adapter.decode([-1.0] * len(ACTION_NAMES))
    assert 0.0 <= positive[4] <= math.pi
    assert 0.0 <= negative[4] <= math.pi
    assert 0.0 <= positive[7] <= math.pi
    assert 0.0 <= negative[7] <= math.pi


def test_seed_training_config_matches_deployment_action_clamp():
    seed = (
        ROOT / "integrations/gr00t_wbc/config/sonic_dropbear.yaml"
    ).read_text(encoding="utf-8")
    assert "\n    action_clip_value: 1.0\n" in seed
