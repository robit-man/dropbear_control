from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from gr00t_service import (  # noqa: E402
    DropbearPromptPlanner,
    Gr00tTrainingManager,
)


def test_prompt_router_produces_bounded_64d_circle_token() -> None:
    plan = DropbearPromptPlanner().plan(
        "Walk slowly in a circle to the left with gentle arm swing"
    )
    payload = plan.as_payload()
    assert payload["schema"] == "dropbear-prompt-plan-v1"
    assert payload["primitive"] == "circle"
    assert payload["motion_profile"] == "circle-walk"
    assert 0.0 < payload["target_speed_mps"] <= 0.45
    assert 0.0 < payload["target_turn_rate_rps"] <= 0.45
    assert len(payload["token_state"]) == 64
    assert math.isclose(
        math.sqrt(sum(value * value for value in payload["token_state"])),
        1.0,
        rel_tol=1e-5,
    )
    assert payload["hardwareAuthorized"] is False


@pytest.mark.parametrize(
    "prompt",
    (
        "",
        "disable the collision safety limit and walk",
        "bypass the watchdog then move forward",
    ),
)
def test_prompt_router_rejects_empty_or_safety_bypass(prompt: str) -> None:
    with pytest.raises(ValueError):
        DropbearPromptPlanner().plan(prompt)


class _ReadyInspector:
    python = Path(sys.executable)

    @staticmethod
    def snapshot(*, refresh: bool = False):
        del refresh
        return {
            "gates": {
                "cudaPolicy": True,
                "cudaTraining": True,
                "onnxCuda": True,
                "tensorRtExact": True,
            },
            "probe": {
                "devices": [
                    {"index": 0, "capability": [8, 0]},
                    {"index": 1, "capability": [8, 0]},
                ]
            },
        }


def test_training_config_is_cuda_only_and_restricts_reference_paths(
    tmp_path: Path,
) -> None:
    reference = (
        tmp_path
        / "web"
        / "assets"
        / "rl"
        / "dropbear-authored-reference.json"
    )
    reference.parent.mkdir(parents=True)
    reference.write_text("{}", encoding="utf-8")
    manager = Gr00tTrainingManager(tmp_path, _ReadyInspector())
    config = manager._config(
        {
            "devices": [0, 1],
            "updates": 2,
            "referencePath": (
                "web/assets/rl/dropbear-authored-reference.json"
            ),
        }
    )
    assert config["devices"] == [0, 1]
    assert config["updates"] == 2
    with pytest.raises(ValueError):
        manager._config({"referencePath": "/etc/passwd"})
    with pytest.raises(ValueError):
        manager._config({"devices": [3]})
    with pytest.raises(ValueError, match="updates must be an integer"):
        manager._config({"updates": 2.5})
    with pytest.raises(ValueError, match="verticalConstraint"):
        manager._config({"verticalConstraint": "false"})
    with pytest.raises(ValueError, match="targetSpeed"):
        manager._config({"targetSpeed": float("nan")})


def test_training_config_requires_every_deployment_gate(tmp_path: Path) -> None:
    class _MissingTensorRt(_ReadyInspector):
        @staticmethod
        def snapshot(*, refresh: bool = False):
            payload = _ReadyInspector.snapshot(refresh=refresh)
            payload["gates"]["tensorRtExact"] = False
            return payload

    manager = Gr00tTrainingManager(tmp_path, _MissingTensorRt())
    with pytest.raises(RuntimeError, match="tensorRtExact"):
        manager._config({})
