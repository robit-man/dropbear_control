from pathlib import Path
import sys

import pytest
import torch

from rl.dropbear_ppo import (
    ACTION_NAMES,
    LOCAL_POLICY_RESIDUAL_GAIN,
    DropbearWalkEnv,
)
from rl.sonic_action import (
    LOCAL_ACTION_SEMANTICS,
    LOCAL_RESIDUAL_SCALE_RAD,
    reference_payload,
    residual_to_reference,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WBC_PACKAGE = (
    PROJECT_ROOT / "ros2_control" / "dropbear_wbc_controller"
)
if str(WBC_PACKAGE) not in sys.path:
    sys.path.insert(0, str(WBC_PACKAGE))

from dropbear_wbc_controller.contract import (  # noqa: E402
    CANONICAL_JOINT_ORDER,
    JointReferenceFrame,
)


def test_zero_residual_reproduces_time_varying_authored_reference():
    environment = DropbearWalkEnv(num_envs=1, device="cpu")
    environment.t[:] = 0.37
    reference = environment._reference_motor_targets()[0]
    decoded = residual_to_reference([0.0] * 22, reference.tolist())
    assert decoded == pytest.approx(reference.tolist())


def test_residual_postprocessing_matches_teaching_plant_formula():
    environment = DropbearWalkEnv(num_envs=1, device="cpu")
    environment.t[:] = 0.61
    reference = environment._reference_motor_targets()[0]
    residual = torch.linspace(-1.0, 1.0, 22)
    expected = (
        reference
        + residual
        * environment.action_scale
        * LOCAL_POLICY_RESIDUAL_GAIN
    )
    expected[4] = expected[4].clamp(0.0, torch.pi)
    expected[7] = expected[7].clamp(0.0, torch.pi)
    actual = residual_to_reference(
        residual.tolist(),
        reference.tolist(),
    )
    assert actual == pytest.approx(expected.tolist(), abs=1e-7)
    assert len(LOCAL_RESIDUAL_SCALE_RAD) == 22


def test_runtime_reference_payload_is_accepted_by_wbc_contract():
    assert tuple(ACTION_NAMES) == CANONICAL_JOINT_ORDER
    payload = reference_payload(
        [0.0] * 22,
        [0.0] * 22,
        session_id="unit",
        sequence=7,
        source_token_sequence=7,
        generated_steady_time_ns=123,
    )
    assert payload["action_semantics"] == LOCAL_ACTION_SEMANTICS
    # The transport contract ignores explicit extension fields while
    # validating all safety-critical reference fields.
    parsed = JointReferenceFrame.from_dict(payload)
    assert parsed.sequence == 7
    assert parsed.positions == (0.0,) * 22
    assert parsed.source_token_sequence == 7
