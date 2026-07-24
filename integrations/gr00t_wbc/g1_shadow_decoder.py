"""CUDA-only G1 SONIC shadow decoder for preview and retargeting teachers.

The GR00T VLA does not emit G1 joint positions.  It emits one 64-value SONIC
token per 50 Hz control frame.  The pinned G1 dynamic decoder consumes that
token plus ten frames of G1 state history and emits 29 normalized actions in
Isaac Lab order.  This module reproduces that deployed boundary exactly, then
converts the actions into a bounded kinematic G1 state in canonical MuJoCo
joint order.

This is deliberately a shadow/teacher path:

* CUDA is mandatory and CPU execution-provider fallback is disabled.
* the downloaded model digest and ONNX tensor contract are verified;
* malformed, stale, skipped, or out-of-cadence tokens produce no pose;
* decoder/runtime faults latch the instance unavailable; and
* no result is authorized for hardware or represented as Dropbear dynamics.

The returned G1 pose is suitable as input to the semantic Dropbear retargeter.
A real G1 or Dropbear physics rollout remains the authority for contacts,
floating-base state, and closed-loop mechanism dynamics.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import importlib
from pathlib import Path
import threading
from typing import Any, Callable, Sequence

from .retarget import G1_BODY_JOINT_NAMES


SHADOW_DECODER_SCHEMA = "dropbear-g1-sonic-shadow-decoder-v1"
UPSTREAM_COMMIT = "4141c34280abb67c82e115342a8720f4a83d750d"
MODEL_SHA256 = "c7241a123eaa36b5d64bad19540efde93cac1ad443bd4572fd12ca99898118ed"
MODEL_RELATIVE_PATH = Path(
    "references/GR00T-WholeBodyControl/"
    "gear_sonic_deploy/policy/release/model_decoder.onnx"
)

TOKEN_DIMENSION = 64
TOKEN_COMPONENT_ABS_LIMIT = 1.25
CONTROL_RATE_HZ = 50
CONTROL_PERIOD_SECONDS = 1.0 / CONTROL_RATE_HZ
CONTROL_PERIOD_NS = 20_000_000
CADENCE_TOLERANCE_NS = 5_000_000
VLA_ACTION_HORIZON_FRAMES = 40
VLA_ACTION_HORIZON_SECONDS = 0.8
VLA_REFRESH_FRAMES = 20
VLA_REFRESH_RATE_HZ = 2.5
HISTORY_FRAMES = 10
OBSERVATION_DIMENSION = 994
ACTION_DIMENSION = 29
MAX_NORMALIZED_ACTION_ABS = 20.0
MAX_SHADOW_JOINT_SPEED_RAD_S = 35.0

OBSERVATION_SLICES = {
    "token_state": (0, 64),
    "base_angular_velocity_history": (64, 94),
    "body_joint_position_history": (94, 384),
    "body_joint_velocity_history": (384, 674),
    "last_action_history": (674, 964),
    "projected_gravity_history": (964, 994),
}

# For each canonical MuJoCo joint index, the corresponding policy action index.
# This is upstream ``isaaclab_to_mujoco`` despite that ambiguous identifier.
MUJOCO_INDEX_TO_ISAAC_INDEX = (
    0,
    3,
    6,
    9,
    13,
    17,
    1,
    4,
    7,
    10,
    14,
    18,
    2,
    5,
    8,
    11,
    15,
    19,
    21,
    23,
    25,
    27,
    12,
    16,
    20,
    22,
    24,
    26,
    28,
)

# For each Isaac Lab policy index, the corresponding canonical MuJoCo index.
# This is upstream ``mujoco_to_isaaclab``.
ISAAC_INDEX_TO_MUJOCO_INDEX = (
    0,
    6,
    12,
    1,
    7,
    13,
    2,
    8,
    14,
    3,
    9,
    15,
    22,
    4,
    10,
    16,
    23,
    5,
    11,
    17,
    24,
    18,
    25,
    19,
    26,
    20,
    27,
    21,
    28,
)

G1_DEFAULT_ANGLES_RAD = (
    -0.312,
    0.0,
    0.0,
    0.669,
    -0.363,
    0.0,
    -0.312,
    0.0,
    0.0,
    0.669,
    -0.363,
    0.0,
    0.0,
    0.0,
    0.0,
    0.2,
    0.2,
    0.0,
    0.6,
    0.0,
    0.0,
    0.0,
    0.2,
    -0.2,
    0.0,
    0.6,
    0.0,
    0.0,
    0.0,
)

G1_JOINT_LIMITS_RAD = (
    (-2.5307, 2.8798),
    (-0.5236, 2.9671),
    (-2.7576, 2.7576),
    (-0.087267, 2.8798),
    (-0.87267, 0.5236),
    (-0.2618, 0.2618),
    (-2.5307, 2.8798),
    (-2.9671, 0.5236),
    (-2.7576, 2.7576),
    (-0.087267, 2.8798),
    (-0.87267, 0.5236),
    (-0.2618, 0.2618),
    (-2.618, 2.618),
    (-0.52, 0.52),
    (-0.52, 0.52),
    (-3.0892, 2.6704),
    (-1.5882, 2.2515),
    (-2.618, 2.618),
    (-1.0472, 2.0944),
    (-1.97222, 1.97222),
    (-1.61443, 1.61443),
    (-1.61443, 1.61443),
    (-3.0892, 2.6704),
    (-2.2515, 1.5882),
    (-2.618, 2.618),
    (-1.0472, 2.0944),
    (-1.97222, 1.97222),
    (-1.61443, 1.61443),
    (-1.61443, 1.61443),
)


def _official_action_scale(armature: float, effort_limit: float) -> float:
    natural_frequency = 10.0 * 2.0 * 3.1415926535
    stiffness = armature * natural_frequency * natural_frequency
    return 0.25 * effort_limit / stiffness


_SCALE_5020 = _official_action_scale(0.003609725, 25.0)
_SCALE_7520_14 = _official_action_scale(0.010177520, 88.0)
_SCALE_7520_22 = _official_action_scale(0.025101925, 139.0)
_SCALE_4010 = _official_action_scale(0.00425, 5.0)

G1_ACTION_SCALES_RAD = (
    _SCALE_7520_22,
    _SCALE_7520_22,
    _SCALE_7520_14,
    _SCALE_7520_22,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_7520_22,
    _SCALE_7520_22,
    _SCALE_7520_14,
    _SCALE_7520_22,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_7520_14,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_4010,
    _SCALE_4010,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_5020,
    _SCALE_4010,
    _SCALE_4010,
)


class G1ShadowDecoderError(RuntimeError):
    """Base class for fail-closed shadow-decoder errors."""


class G1ShadowDecoderUnavailable(G1ShadowDecoderError):
    """The verified CUDA decoder is unavailable or has latched a fault."""


class G1ShadowContractError(G1ShadowDecoderError):
    """A token, model tensor, or decoded action violates the fixed contract."""


class G1ShadowCadenceError(G1ShadowContractError):
    """The caller skipped, duplicated, reordered, or mistimed a token frame."""


@dataclass(frozen=True)
class _HistorySample:
    base_angular_velocity: Any
    body_joint_position: Any
    body_joint_velocity: Any
    last_action: Any
    projected_gravity: Any


SessionFactory = Callable[[Path], Any]


class G1ShadowDecoder:
    """Decode streamed G1 SONIC tokens into bounded canonical G1 joint poses.

    ``sequence`` is a globally increasing stream sequence, not the VLA
    chunk-local ``frame_index``.  Call :meth:`reset` before starting a new
    playback session.  Supplying ``steady_time_ns`` additionally checks the
    scheduled 20 ms cadence; omitting it still enforces contiguous frames.
    """

    def __init__(
        self,
        project_root: Path | str | None = None,
        *,
        device_id: int = 0,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        if isinstance(device_id, bool) or not isinstance(device_id, int):
            raise ValueError("device_id must be a non-negative integer")
        if device_id < 0:
            raise ValueError("device_id must be a non-negative integer")
        self.device_id = device_id
        self.model_path = self.project_root / MODEL_RELATIVE_PATH
        self._lock = threading.RLock()
        self._np: Any | None = None
        self._session: Any | None = None
        self._provider_names: tuple[str, ...] = ()
        self._cuda_runtime: dict[str, Any] = {}
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._model_verified = False
        self._availability_reason: str | None = None
        self._fault: str | None = None
        self._history: deque[_HistorySample] = deque(maxlen=HISTORY_FRAMES - 1)
        self._q_mujoco: Any | None = None
        self._dq_mujoco: Any | None = None
        self._last_action_isaac: Any | None = None
        self._last_sequence: int | None = None
        self._last_steady_time_ns: int | None = None
        self._cadence_uses_timestamps: bool | None = None
        self._frames_decoded = 0
        self._last_position_clamp_count = 0
        self._last_velocity_clamp_count = 0

        try:
            self._initialize(session_factory)
            self._reset_state()
        except Exception as exc:  # availability is inspectable and decode fails closed
            self._session = None
            self._availability_reason = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        """Whether a verified, CUDA-backed, non-faulted decoder can run."""

        with self._lock:
            return self._session is not None and self._fault is None

    def _initialize(self, session_factory: SessionFactory | None) -> None:
        if not self.model_path.is_file():
            raise G1ShadowDecoderUnavailable(
                f"pinned decoder is absent: {MODEL_RELATIVE_PATH.as_posix()}"
            )
        digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            raise G1ShadowContractError(
                "pinned decoder digest mismatch; refusing unverified weights"
            )
        self._model_verified = True

        self._np = importlib.import_module("numpy")
        if session_factory is None:
            session = self._create_cuda_session()
        else:
            session = session_factory(self.model_path)
        self._validate_session_contract(session)
        self._session = session
        self._warm_up()

    def _create_cuda_session(self) -> Any:
        # The runtime environment intentionally supplies CUDA through its
        # pinned PyTorch build.  Import and initialize it first so cuBLAS and
        # cuDNN are resident before ONNX Runtime loads its CUDA provider.
        torch = importlib.import_module("torch")
        if not bool(torch.cuda.is_available()):
            raise G1ShadowDecoderUnavailable("PyTorch reports CUDA unavailable")
        device_count = int(torch.cuda.device_count())
        if self.device_id >= device_count:
            raise G1ShadowDecoderUnavailable(
                f"CUDA device {self.device_id} is absent; found {device_count}"
            )
        torch.cuda.set_device(self.device_id)
        torch.cuda.init()
        self._cuda_runtime = {
            "torchVersion": str(torch.__version__),
            "torchCudaVersion": str(torch.version.cuda),
            "deviceName": str(torch.cuda.get_device_name(self.device_id)),
            "deviceCount": device_count,
        }

        ort = importlib.import_module("onnxruntime")
        available = tuple(ort.get_available_providers())
        if "CUDAExecutionProvider" not in available:
            raise G1ShadowDecoderUnavailable(
                "onnxruntime CUDAExecutionProvider is not installed"
            )
        options = ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        providers = [
            (
                "CUDAExecutionProvider",
                {
                    "device_id": self.device_id,
                    "do_copy_in_default_stream": 1,
                },
            )
        ]
        return ort.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=providers,
        )

    @staticmethod
    def _tensor_shape(meta: Any) -> tuple[int, ...]:
        shape = tuple(meta.shape)
        if not all(isinstance(value, int) for value in shape):
            raise G1ShadowContractError("decoder tensors must have static shapes")
        return shape

    def _validate_session_contract(self, session: Any) -> None:
        providers = tuple(session.get_providers())
        if not providers or providers[0] != "CUDAExecutionProvider":
            raise G1ShadowDecoderUnavailable(
                "CUDAExecutionProvider is not the active primary provider"
            )
        inputs = tuple(session.get_inputs())
        outputs = tuple(session.get_outputs())
        if len(inputs) != 1 or len(outputs) != 1:
            raise G1ShadowContractError(
                "decoder must expose exactly one input and one output"
            )
        input_meta = inputs[0]
        output_meta = outputs[0]
        if (
            input_meta.name != "obs_dict"
            or self._tensor_shape(input_meta) != (1, OBSERVATION_DIMENSION)
            or input_meta.type != "tensor(float)"
        ):
            raise G1ShadowContractError("decoder input must be obs_dict float32[1,994]")
        if (
            output_meta.name != "action"
            or self._tensor_shape(output_meta) != (1, ACTION_DIMENSION)
            or output_meta.type != "tensor(float)"
        ):
            raise G1ShadowContractError("decoder output must be action float32[1,29]")
        self._provider_names = providers
        self._input_name = input_meta.name
        self._output_name = output_meta.name

    def _warm_up(self) -> None:
        assert self._np is not None
        assert self._session is not None or self._output_name is not None
        observation = self._np.zeros(
            (1, OBSERVATION_DIMENSION),
            dtype=self._np.float32,
        )
        output = self._run_session(observation)
        self._validate_action_output(output)

    def _run_session(self, observation: Any) -> Any:
        if self._session is None:
            # During initialization the candidate is not committed yet.
            raise G1ShadowDecoderUnavailable("CUDA session is not initialized")
        assert self._input_name is not None
        assert self._output_name is not None
        return self._session.run(
            [self._output_name],
            {self._input_name: observation},
        )[0]

    def _reset_state(self) -> None:
        assert self._np is not None
        self._history.clear()
        self._q_mujoco = self._np.asarray(
            G1_DEFAULT_ANGLES_RAD,
            dtype=self._np.float32,
        )
        self._dq_mujoco = self._np.zeros(
            ACTION_DIMENSION,
            dtype=self._np.float32,
        )
        self._last_action_isaac = self._np.zeros(
            ACTION_DIMENSION,
            dtype=self._np.float32,
        )
        self._last_sequence = None
        self._last_steady_time_ns = None
        self._cadence_uses_timestamps = None
        self._frames_decoded = 0
        self._last_position_clamp_count = 0
        self._last_velocity_clamp_count = 0

    def reset(self) -> None:
        """Reset stream cadence and the kinematic shadow to the standing pose."""

        with self._lock:
            if not self.available:
                raise G1ShadowDecoderUnavailable(
                    self._availability_reason or self._fault or "decoder unavailable"
                )
            self._reset_state()

    def _validate_token(self, token: Sequence[float]) -> Any:
        assert self._np is not None
        values = self._np.asarray(token)
        if values.shape != (TOKEN_DIMENSION,):
            raise G1ShadowContractError(
                f"motion token must have shape ({TOKEN_DIMENSION},)"
            )
        if values.dtype == self._np.bool_:
            raise G1ShadowContractError("motion token cannot contain booleans")
        try:
            values = values.astype(self._np.float32, copy=False)
        except (TypeError, ValueError) as exc:
            raise G1ShadowContractError(
                "motion token must contain numeric values"
            ) from exc
        if not bool(self._np.isfinite(values).all()):
            raise G1ShadowContractError("motion token must contain finite values")
        if bool((self._np.abs(values) > TOKEN_COMPONENT_ABS_LIMIT).any()):
            raise G1ShadowContractError(
                "motion token exceeds the pinned +/-1.25 component envelope"
            )
        return values

    def _validate_cadence(
        self,
        sequence: int,
        steady_time_ns: int | None,
    ) -> None:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise G1ShadowCadenceError(
                "sequence must be a non-negative global frame integer"
            )
        expected = None if self._last_sequence is None else self._last_sequence + 1
        if expected is not None and sequence != expected:
            raise G1ShadowCadenceError(
                f"expected contiguous token sequence {expected}, got {sequence}"
            )

        timed = steady_time_ns is not None
        if self._cadence_uses_timestamps is not None and (
            timed != self._cadence_uses_timestamps
        ):
            raise G1ShadowCadenceError(
                "steady_time_ns must be supplied consistently for a stream"
            )
        if steady_time_ns is None:
            return
        if (
            isinstance(steady_time_ns, bool)
            or not isinstance(steady_time_ns, int)
            or steady_time_ns < 0
        ):
            raise G1ShadowCadenceError("steady_time_ns must be a non-negative integer")
        if self._last_steady_time_ns is not None:
            delta = steady_time_ns - self._last_steady_time_ns
            if abs(delta - CONTROL_PERIOD_NS) > CADENCE_TOLERANCE_NS:
                raise G1ShadowCadenceError(
                    "token cadence must remain 50 Hz "
                    f"({CONTROL_PERIOD_NS} ns +/- {CADENCE_TOLERANCE_NS} ns)"
                )

    def _current_sample(self) -> _HistorySample:
        assert self._np is not None
        assert self._q_mujoco is not None
        assert self._dq_mujoco is not None
        assert self._last_action_isaac is not None
        default = self._np.asarray(G1_DEFAULT_ANGLES_RAD, dtype=self._np.float32)
        residual_mujoco = self._q_mujoco - default
        residual_isaac = residual_mujoco[self._np.asarray(ISAAC_INDEX_TO_MUJOCO_INDEX)]
        velocity_isaac = self._dq_mujoco[self._np.asarray(ISAAC_INDEX_TO_MUJOCO_INDEX)]
        return _HistorySample(
            base_angular_velocity=self._np.zeros(3, dtype=self._np.float32),
            body_joint_position=residual_isaac.astype(
                self._np.float32,
                copy=True,
            ),
            body_joint_velocity=velocity_isaac.astype(
                self._np.float32,
                copy=True,
            ),
            last_action=self._last_action_isaac.astype(
                self._np.float32,
                copy=True,
            ),
            projected_gravity=self._np.asarray(
                (0.0, 0.0, -1.0),
                dtype=self._np.float32,
            ),
        )

    def _build_observation(
        self,
        token: Any,
        current_sample: _HistorySample,
    ) -> Any:
        assert self._np is not None
        samples = [*self._history, current_sample]
        zero = _HistorySample(
            base_angular_velocity=self._np.zeros(3, dtype=self._np.float32),
            body_joint_position=self._np.zeros(
                ACTION_DIMENSION,
                dtype=self._np.float32,
            ),
            body_joint_velocity=self._np.zeros(
                ACTION_DIMENSION,
                dtype=self._np.float32,
            ),
            last_action=self._np.zeros(
                ACTION_DIMENSION,
                dtype=self._np.float32,
            ),
            projected_gravity=self._np.zeros(3, dtype=self._np.float32),
        )
        samples = [zero] * (HISTORY_FRAMES - len(samples)) + samples
        if len(samples) != HISTORY_FRAMES:
            raise G1ShadowContractError("internal history length is invalid")
        observation = self._np.concatenate(
            (
                token,
                *(sample.base_angular_velocity for sample in samples),
                *(sample.body_joint_position for sample in samples),
                *(sample.body_joint_velocity for sample in samples),
                *(sample.last_action for sample in samples),
                *(sample.projected_gravity for sample in samples),
            )
        ).astype(self._np.float32, copy=False)
        if observation.shape != (OBSERVATION_DIMENSION,):
            raise G1ShadowContractError(
                "internal observation assembly did not produce 994 values"
            )
        return observation.reshape(1, OBSERVATION_DIMENSION)

    def _validate_action_output(self, output: Any) -> Any:
        assert self._np is not None
        values = self._np.asarray(output)
        if values.shape != (1, ACTION_DIMENSION):
            raise G1ShadowContractError("decoder action must have shape (1,29)")
        if values.dtype != self._np.float32:
            raise G1ShadowContractError("decoder action must be float32")
        action = values[0]
        if not bool(self._np.isfinite(action).all()):
            raise G1ShadowContractError("decoder emitted a non-finite action")
        if bool((self._np.abs(action) > MAX_NORMALIZED_ACTION_ABS).any()):
            raise G1ShadowContractError(
                "decoder action exceeds the pinned +/-20 training envelope"
            )
        return action.astype(self._np.float32, copy=True)

    def _advance_shadow(self, action_isaac: Any) -> Any:
        assert self._np is not None
        assert self._q_mujoco is not None
        action_mujoco = action_isaac[self._np.asarray(MUJOCO_INDEX_TO_ISAAC_INDEX)]
        default = self._np.asarray(G1_DEFAULT_ANGLES_RAD, dtype=self._np.float32)
        scale = self._np.asarray(G1_ACTION_SCALES_RAD, dtype=self._np.float32)
        lower = self._np.asarray(
            [bounds[0] for bounds in G1_JOINT_LIMITS_RAD],
            dtype=self._np.float32,
        )
        upper = self._np.asarray(
            [bounds[1] for bounds in G1_JOINT_LIMITS_RAD],
            dtype=self._np.float32,
        )
        unbounded_target = default + action_mujoco * scale
        target = self._np.clip(unbounded_target, lower, upper)
        self._last_position_clamp_count = int(
            self._np.count_nonzero(target != unbounded_target)
        )

        requested_velocity = (target - self._q_mujoco) / CONTROL_PERIOD_SECONDS
        velocity = self._np.clip(
            requested_velocity,
            -MAX_SHADOW_JOINT_SPEED_RAD_S,
            MAX_SHADOW_JOINT_SPEED_RAD_S,
        )
        self._last_velocity_clamp_count = int(
            self._np.count_nonzero(velocity != requested_velocity)
        )
        next_q = self._np.clip(
            self._q_mujoco + velocity * CONTROL_PERIOD_SECONDS,
            lower,
            upper,
        ).astype(self._np.float32)
        self._dq_mujoco = velocity.astype(self._np.float32)
        self._q_mujoco = next_q
        self._last_action_isaac = action_isaac
        return next_q

    def _latch_fault(self, exc: Exception) -> None:
        self._fault = f"{type(exc).__name__}: {exc}"
        self._availability_reason = self._fault
        self._session = None

    def decode_token(
        self,
        token: Sequence[float],
        *,
        sequence: int,
        steady_time_ns: int | None = None,
    ) -> tuple[float, ...]:
        """Decode one streamed 50 Hz token into canonical absolute G1 q[29].

        The tuple order is :data:`G1_BODY_JOINT_NAMES`.  Input/cadence errors
        reject only that frame.  Inference or output-contract errors latch the
        decoder unavailable so no later frame can silently continue.
        """

        with self._lock:
            if not self.available:
                raise G1ShadowDecoderUnavailable(
                    self._availability_reason or self._fault or "decoder unavailable"
                )
            token_values = self._validate_token(token)
            self._validate_cadence(sequence, steady_time_ns)
            current_sample = self._current_sample()
            observation = self._build_observation(token_values, current_sample)

            try:
                output = self._run_session(observation)
                action = self._validate_action_output(output)
            except Exception as exc:
                self._latch_fault(exc)
                if isinstance(exc, G1ShadowDecoderError):
                    raise
                raise G1ShadowDecoderUnavailable(
                    f"CUDA decoder inference failed: {exc}"
                ) from exc

            next_q = self._advance_shadow(action)
            self._history.append(current_sample)
            self._last_sequence = sequence
            self._cadence_uses_timestamps = steady_time_ns is not None
            self._last_steady_time_ns = steady_time_ns
            self._frames_decoded += 1
            return tuple(float(value) for value in next_q)

    def status_payload(self) -> dict[str, Any]:
        """Return the complete inspectable, non-hardware decoder contract."""

        with self._lock:
            q = (
                []
                if self._q_mujoco is None
                else [float(value) for value in self._q_mujoco]
            )
            return {
                "schema": SHADOW_DECODER_SCHEMA,
                "available": self.available,
                "mode": "preview-teacher-only",
                "hardwareAuthorized": False,
                "dropbearDynamicsAuthority": False,
                "availabilityReason": self._availability_reason,
                "faultLatched": self._fault is not None,
                "upstream": {
                    "repository": (
                        "https://github.com/NVlabs/GR00T-WholeBodyControl.git"
                    ),
                    "commit": UPSTREAM_COMMIT,
                },
                "model": {
                    "path": MODEL_RELATIVE_PATH.as_posix(),
                    "sha256": MODEL_SHA256,
                    "verified": self._model_verified,
                    "input": {
                        "name": "obs_dict",
                        "dtype": "float32",
                        "shape": [1, OBSERVATION_DIMENSION],
                    },
                    "output": {
                        "name": "action",
                        "dtype": "float32",
                        "shape": [1, ACTION_DIMENSION],
                        "order": "IsaacLab",
                    },
                },
                "runtime": {
                    "cudaRequired": True,
                    "cpuFallbackAllowed": False,
                    "deviceId": self.device_id,
                    "providers": list(self._provider_names),
                    **self._cuda_runtime,
                },
                "tokenStream": {
                    "dimension": TOKEN_DIMENSION,
                    "componentAbsLimit": TOKEN_COMPONENT_ABS_LIMIT,
                    "controlRateHz": CONTROL_RATE_HZ,
                    "periodNs": CONTROL_PERIOD_NS,
                    "timestampToleranceNs": CADENCE_TOLERANCE_NS,
                    "sequenceSemantics": "global-contiguous-frame-sequence",
                    "vlaActionHorizonFrames": VLA_ACTION_HORIZON_FRAMES,
                    "vlaActionHorizonSeconds": VLA_ACTION_HORIZON_SECONDS,
                    "nominalRefreshFrames": VLA_REFRESH_FRAMES,
                    "nominalRefreshRateHz": VLA_REFRESH_RATE_HZ,
                },
                "observation": {
                    "dimension": OBSERVATION_DIMENSION,
                    "historyFrames": HISTORY_FRAMES,
                    "historyOrder": "oldest-to-newest-zero-padded",
                    "slices": {
                        key: list(value) for key, value in OBSERVATION_SLICES.items()
                    },
                    "bodyPositionSemantics": (
                        "default-relative-radians-IsaacLab-order"
                    ),
                    "bodyVelocitySemantics": "radians-per-second-IsaacLab-order",
                    "lastActionSemantics": "raw-normalized-IsaacLab-order",
                    "gravitySemantics": "projected-gravity-body-frame",
                },
                "shadowState": {
                    "jointOrder": list(G1_BODY_JOINT_NAMES),
                    "order": "MuJoCo/body-actuated",
                    "absolutePositionRad": q,
                    "positionLimitsRad": [
                        list(bounds) for bounds in G1_JOINT_LIMITS_RAD
                    ],
                    "maximumJointSpeedRadS": MAX_SHADOW_JOINT_SPEED_RAD_S,
                    "physicsAuthoritative": False,
                    "lastPositionClampCount": self._last_position_clamp_count,
                    "lastVelocityClampCount": self._last_velocity_clamp_count,
                },
                "streamState": {
                    "framesDecoded": self._frames_decoded,
                    "lastSequence": self._last_sequence,
                    "timestampsValidated": self._cadence_uses_timestamps is True,
                },
            }


def shadow_decoder_contract() -> dict[str, Any]:
    """Return the static contract without constructing an ONNX session."""

    return {
        "schema": SHADOW_DECODER_SCHEMA,
        "previewTeacherOnly": True,
        "hardwareAuthorized": False,
        "modelSha256": MODEL_SHA256,
        "inputShape": [1, OBSERVATION_DIMENSION],
        "outputShape": [1, ACTION_DIMENSION],
        "tokenDimension": TOKEN_DIMENSION,
        "controlRateHz": CONTROL_RATE_HZ,
        "historyFrames": HISTORY_FRAMES,
        "jointOrder": list(G1_BODY_JOINT_NAMES),
        "mujocoIndexToIsaacIndex": list(MUJOCO_INDEX_TO_ISAAC_INDEX),
        "isaacIndexToMujocoIndex": list(ISAAC_INDEX_TO_MUJOCO_INDEX),
        "defaultAnglesRad": list(G1_DEFAULT_ANGLES_RAD),
        "actionScalesRad": list(G1_ACTION_SCALES_RAD),
        "positionLimitsRad": [list(bounds) for bounds in G1_JOINT_LIMITS_RAD],
    }
