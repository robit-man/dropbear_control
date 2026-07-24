"""Strict, lightweight Isaac-GR00T PolicyClient transport for G1 SONIC.

This module implements only the ZeroMQ/msgpack boundary needed to request a
UNITREE_G1_SONIC action chunk from an independently operated Isaac-GR00T
server.  It does not load a VLA checkpoint, start a server, or imply that a
compatible server is reachable.

The wire format follows NVIDIA's Apache-2.0 ``PolicyClient``:

* ZeroMQ REQ/REP over ``tcp://host:port``;
* msgpack with msgpack-numpy ndarray envelopes;
* ``{"endpoint": "get_action", "data": {...}}`` requests; and
* ``[action_dict, info_dict]`` responses.

Imports for msgpack, msgpack-numpy, numpy, and pyzmq are deliberately lazy so
the rest of the Dropbear integration remains usable without transport extras.
Object-dtype arrays and forged pickle-bearing msgpack-numpy envelopes are
rejected before msgpack-numpy can process them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import functools
import importlib
import ipaddress
import math
import threading
from typing import Any


POLICY_CLIENT_SCHEMA = "dropbear-unitree-g1-sonic-policy-client-v1"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 5550
DEFAULT_TIMEOUT_MS = 15_000
MAX_WIRE_MESSAGE_BYTES = 64 * 1024 * 1024

ACTION_HORIZON_FRAMES = 40
MOTION_TOKEN_DIMENSION = 64
HAND_JOINT_DIMENSION = 7
MOTION_TOKEN_COMPONENT_ABS_LIMIT = 1.25

MOTION_TOKEN_KEY = "motion_token"
LEFT_HAND_KEY = "left_hand_joints"
RIGHT_HAND_KEY = "right_hand_joints"
REQUIRED_ACTION_KEYS = (
    MOTION_TOKEN_KEY,
    LEFT_HAND_KEY,
    RIGHT_HAND_KEY,
)
ACTION_SHAPES = {
    MOTION_TOKEN_KEY: (1, ACTION_HORIZON_FRAMES, MOTION_TOKEN_DIMENSION),
    LEFT_HAND_KEY: (1, ACTION_HORIZON_FRAMES, HAND_JOINT_DIMENSION),
    RIGHT_HAND_KEY: (1, ACTION_HORIZON_FRAMES, HAND_JOINT_DIMENSION),
}
_IGNORED_SERVER_ACTION_KEYS = frozenset(("task_progress", "action.task_progress"))


class G1SonicPolicyClientError(RuntimeError):
    """Base class for the fail-closed transport boundary."""


class G1SonicTransportUnavailable(G1SonicPolicyClientError):
    """Optional transport dependencies or the remote endpoint are unavailable."""


class G1SonicTransportTimeout(G1SonicTransportUnavailable):
    """A PolicyClient request exceeded its configured send/receive timeout."""


class G1SonicProtocolError(G1SonicPolicyClientError):
    """A request or response violates the fixed G1 SONIC wire contract."""


class G1SonicServerError(G1SonicPolicyClientError):
    """The independently operated Isaac-GR00T server returned an error."""


@dataclass(frozen=True, slots=True)
class _TransportDependencies:
    msgpack: Any
    msgpack_numpy: Any
    numpy: Any
    zmq: Any


@functools.lru_cache(maxsize=1)
def _load_transport_dependencies() -> _TransportDependencies:
    modules: dict[str, Any] = {}
    missing: list[str] = []
    for import_name, distribution_name in (
        ("msgpack", "msgpack"),
        ("msgpack_numpy", "msgpack-numpy"),
        ("numpy", "numpy"),
        ("zmq", "pyzmq"),
    ):
        try:
            modules[import_name] = importlib.import_module(import_name)
        except ImportError:
            missing.append(distribution_name)
    if missing:
        raise G1SonicTransportUnavailable(
            "G1 SONIC PolicyClient transport extras are unavailable; install "
            f"{', '.join(sorted(missing))} from requirements-gr00t-runtime-lock.txt"
        )
    return _TransportDependencies(
        msgpack=modules["msgpack"],
        msgpack_numpy=modules["msgpack_numpy"],
        numpy=modules["numpy"],
        zmq=modules["zmq"],
    )


def _reject_custom_wire_type(obj: Any) -> Any:
    raise TypeError(
        f"unsupported PolicyClient wire value {type(obj).__module__}."
        f"{type(obj).__qualname__}"
    )


class SafePolicyWireSerializer:
    """Official-compatible msgpack-numpy serialization without pickle."""

    @staticmethod
    def to_bytes(data: Any) -> bytes:
        deps = _load_transport_dependencies()
        default = functools.partial(
            SafePolicyWireSerializer._safe_encode,
            deps=deps,
        )
        try:
            return deps.msgpack.packb(data, default=default)
        except G1SonicPolicyClientError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise G1SonicProtocolError(
                f"PolicyClient request serialization failed: {error}"
            ) from error

    @staticmethod
    def from_bytes(data: bytes) -> Any:
        deps = _load_transport_dependencies()
        if not isinstance(data, bytes):
            raise G1SonicProtocolError("PolicyClient response must be bytes")
        if len(data) > MAX_WIRE_MESSAGE_BYTES:
            raise G1SonicProtocolError(
                "PolicyClient response exceeds the 64 MiB transport limit"
            )
        object_hook = functools.partial(
            SafePolicyWireSerializer._safe_decode,
            deps=deps,
        )
        try:
            return deps.msgpack.unpackb(
                data,
                object_hook=object_hook,
                raw=False,
                max_str_len=MAX_WIRE_MESSAGE_BYTES,
                max_bin_len=MAX_WIRE_MESSAGE_BYTES,
                max_array_len=MAX_WIRE_MESSAGE_BYTES,
                max_map_len=1_000_000,
                max_ext_len=MAX_WIRE_MESSAGE_BYTES,
            )
        except G1SonicPolicyClientError:
            raise
        except Exception as error:
            raise G1SonicProtocolError(
                f"PolicyClient response deserialization failed: {error}"
            ) from error

    @staticmethod
    def _safe_encode(obj: Any, *, deps: _TransportDependencies) -> Any:
        if isinstance(obj, deps.numpy.ndarray) and obj.dtype.hasobject:
            raise G1SonicProtocolError(
                "refusing to encode an object-bearing ndarray; "
                "msgpack-numpy would invoke pickle"
            )
        return deps.msgpack_numpy.encode(obj, chain=_reject_custom_wire_type)

    @staticmethod
    def _safe_decode(obj: Any, *, deps: _TransportDependencies) -> Any:
        if not isinstance(obj, dict):
            return obj

        # A legacy Isaac-GR00T envelope carries npy bytes.  ``allow_pickle`` is
        # fixed false, so an object array cannot cross this boundary.
        ndarray_marker = obj.get("__ndarray_class__", obj.get(b"__ndarray_class__"))
        if ndarray_marker:
            payload = obj.get("as_npy", obj.get(b"as_npy"))
            if payload is None:
                raise G1SonicProtocolError(
                    "malformed ndarray payload: marker present but as_npy missing"
                )
            import io

            try:
                value = deps.numpy.load(
                    io.BytesIO(payload),
                    allow_pickle=False,
                )
            except Exception as error:
                raise G1SonicProtocolError(
                    "refusing malformed or pickle-bearing npy payload"
                ) from error
            if isinstance(value, deps.numpy.ndarray) and value.dtype.hasobject:
                raise G1SonicProtocolError("refusing decoded object-bearing ndarray")
            return value

        nd_value = obj.get(b"nd", obj.get("nd"))
        if nd_value is not None:
            if type(nd_value) is not bool:
                raise G1SonicProtocolError(
                    "msgpack-numpy ndarray marker must be a boolean"
                )
            kind_value = obj.get(b"kind", obj.get("kind", b""))
            if kind_value in (b"O", "O"):
                raise G1SonicProtocolError(
                    "refusing object-dtype ndarray payload; pickle is disabled"
                )
            type_value = obj.get(b"type", obj.get("type"))
            if nd_value is True and type_value is not None:
                try:
                    dtype = deps.numpy.dtype(type_value)
                except (TypeError, ValueError):
                    # Structured dtype descriptors are handled by
                    # msgpack-numpy below.  Inspect the decoded value too.
                    dtype = None
                if dtype is not None and dtype.hasobject:
                    raise G1SonicProtocolError("refusing object-bearing ndarray dtype")

        try:
            value = deps.msgpack_numpy.decode(
                obj,
                chain=lambda item: item,
            )
        except Exception as error:
            raise G1SonicProtocolError(
                f"invalid msgpack-numpy payload: {error}"
            ) from error
        if isinstance(value, deps.numpy.ndarray) and value.dtype.hasobject:
            raise G1SonicProtocolError("refusing decoded object-bearing ndarray")
        return value


def _normalise_action_key(key: Any) -> str:
    if not isinstance(key, str):
        raise G1SonicProtocolError("G1 SONIC action keys must be strings")
    return key.removeprefix("action.")


def validate_unitree_g1_sonic_response(
    response: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate and normalize one official UNITREE_G1_SONIC response.

    The returned action dictionary contains only canonical, unprefixed keys.
    Arrays are finite, C-contiguous, read-only float32 copies with exact
    ``[batch=1, horizon=40, dimension]`` shapes.
    """

    deps = _load_transport_dependencies()
    np = deps.numpy

    if not isinstance(response, (list, tuple)) or len(response) != 2:
        raise G1SonicProtocolError(
            "get_action response must be [action_dict, info_dict]"
        )
    raw_action, raw_info = response
    if not isinstance(raw_action, Mapping):
        raise G1SonicProtocolError("get_action action payload must be a mapping")
    if not isinstance(raw_info, Mapping):
        raise G1SonicProtocolError("get_action info payload must be a mapping")

    normalized: dict[str, Any] = {}
    unexpected: list[str] = []
    for wire_key, value in raw_action.items():
        if wire_key in _IGNORED_SERVER_ACTION_KEYS:
            continue
        key = _normalise_action_key(wire_key)
        if key not in ACTION_SHAPES:
            unexpected.append(str(wire_key))
            continue
        if key in normalized:
            raise G1SonicProtocolError(
                f"duplicate G1 SONIC action key after prefix normalization: {key}"
            )
        if not isinstance(value, np.ndarray):
            raise G1SonicProtocolError(f"G1 SONIC action {key} must be a numpy ndarray")
        expected_shape = ACTION_SHAPES[key]
        if value.shape != expected_shape:
            raise G1SonicProtocolError(
                f"G1 SONIC action {key} has shape {value.shape}, "
                f"expected {expected_shape}"
            )
        if value.dtype != np.dtype(np.float32):
            raise G1SonicProtocolError(
                f"G1 SONIC action {key} has dtype {value.dtype}, expected float32"
            )
        if not np.isfinite(value).all():
            raise G1SonicProtocolError(
                f"G1 SONIC action {key} contains non-finite values"
            )
        output = np.ascontiguousarray(value).copy()
        output.setflags(write=False)
        normalized[key] = output

    if unexpected:
        raise G1SonicProtocolError(
            f"unexpected G1 SONIC action keys: {sorted(unexpected)}"
        )
    missing = sorted(set(REQUIRED_ACTION_KEYS) - set(normalized))
    if missing:
        raise G1SonicProtocolError(f"missing G1 SONIC action keys: {missing}")

    token_max = float(np.max(np.abs(normalized[MOTION_TOKEN_KEY])))
    if not math.isfinite(token_max) or token_max > MOTION_TOKEN_COMPONENT_ABS_LIMIT:
        raise G1SonicProtocolError(
            "G1 SONIC motion_token exceeds the fixed absolute component "
            f"limit {MOTION_TOKEN_COMPONENT_ABS_LIMIT}"
        )

    return normalized, dict(raw_info)


def _normalized_host(host: str) -> str:
    if not isinstance(host, str):
        raise TypeError("host must be a string")
    normalized = host.strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    normalized = normalized.rstrip(".")
    if not normalized or any(character.isspace() for character in normalized):
        raise ValueError("host must be a non-empty hostname or IP address")
    if "/" in normalized or normalized == "*":
        raise ValueError("wildcard and path-like hosts are not valid client targets")
    return normalized


def _is_loopback_host(host: str) -> bool:
    normalized = _normalized_host(host).lower()
    if normalized in ("localhost", "localhost.localdomain"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(mapped is not None and mapped.is_loopback)


def _wire_host(host: str) -> str:
    normalized = _normalized_host(host)
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        if ":" in normalized:
            raise ValueError("invalid host")
        return normalized
    return f"[{normalized}]" if address.version == 6 else normalized


def policy_client_contract() -> dict[str, Any]:
    """Return static integration metadata without probing any server."""

    return {
        "schema": POLICY_CLIENT_SCHEMA,
        "upstreamProtocol": "Isaac-GR00T PolicyClient ZMQ REQ/REP + msgpack_numpy",
        "embodiment": "UNITREE_G1_SONIC",
        "serverReachability": "unknown-until-ping",
        "serverIncluded": False,
        "modelCheckpointIncluded": False,
        "defaultEndpoint": f"tcp://{DEFAULT_HOST}:{DEFAULT_PORT}",
        "remoteAllowedByDefault": False,
        "tlsProvidedByProtocol": False,
        "actionKeys": list(REQUIRED_ACTION_KEYS),
        "actionShapes": {key: list(shape) for key, shape in ACTION_SHAPES.items()},
        "motionTokenComponentAbsLimit": MOTION_TOKEN_COMPONENT_ABS_LIMIT,
    }


class G1SonicPolicyClient:
    """Minimal fail-closed client for an external G1 SONIC policy server."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        api_token: str | None = None,
        allow_remote: bool = False,
    ) -> None:
        normalized_host = _normalized_host(host)
        if not isinstance(allow_remote, bool):
            raise TypeError("allow_remote must be a boolean")
        if not _is_loopback_host(normalized_host) and not allow_remote:
            raise ValueError(
                "non-loopback PolicyClient targets are disabled; set "
                "allow_remote=True only with an explicitly protected transport"
            )
        if isinstance(port, bool) or not isinstance(port, int):
            raise TypeError("port must be an integer")
        if port < 1 or port > 65_535:
            raise ValueError("port must be in the range 1..65535")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
            raise TypeError("timeout_ms must be an integer")
        if timeout_ms < 1 or timeout_ms > 600_000:
            raise ValueError("timeout_ms must be in the range 1..600000")
        if api_token is not None and (not isinstance(api_token, str) or not api_token):
            raise ValueError("api_token must be a non-empty string when provided")

        self.host = normalized_host
        self.port = port
        self.timeout_ms = timeout_ms
        self.api_token = api_token
        self.allow_remote = allow_remote
        self._deps = _load_transport_dependencies()
        self._context = self._deps.zmq.Context()
        self._socket: Any | None = None
        self._closed = False
        self._request_lock = threading.Lock()
        self._init_socket()

    @property
    def endpoint(self) -> str:
        return f"tcp://{_wire_host(self.host)}:{self.port}"

    def _init_socket(self) -> None:
        if self._closed:
            raise G1SonicTransportUnavailable("PolicyClient is closed")
        old_socket = self._socket
        if old_socket is not None:
            old_socket.close(linger=0)
        socket = self._context.socket(self._deps.zmq.REQ)
        socket.setsockopt(self._deps.zmq.RCVTIMEO, self.timeout_ms)
        socket.setsockopt(self._deps.zmq.SNDTIMEO, self.timeout_ms)
        socket.setsockopt(
            self._deps.zmq.MAXMSGSIZE,
            MAX_WIRE_MESSAGE_BYTES,
        )
        socket.setsockopt(self._deps.zmq.LINGER, 0)
        socket.connect(self.endpoint)
        self._socket = socket

    def call_endpoint(
        self,
        endpoint: str,
        data: Mapping[str, Any] | None = None,
        *,
        requires_input: bool = True,
    ) -> Any:
        if endpoint not in ("ping", "get_action", "reset"):
            raise G1SonicProtocolError(
                f"unsupported PolicyClient endpoint: {endpoint!r}"
            )
        if self._closed or self._socket is None:
            raise G1SonicTransportUnavailable("PolicyClient is closed")
        if requires_input and data is not None and not isinstance(data, Mapping):
            raise TypeError("endpoint data must be a mapping or None")

        request: dict[str, Any] = {"endpoint": endpoint}
        if requires_input:
            request["data"] = None if data is None else dict(data)
        if self.api_token is not None:
            request["api_token"] = self.api_token
        payload = SafePolicyWireSerializer.to_bytes(request)
        if len(payload) > MAX_WIRE_MESSAGE_BYTES:
            raise G1SonicProtocolError(
                "PolicyClient request exceeds the 64 MiB transport limit"
            )

        with self._request_lock:
            try:
                self._socket.send(payload)
                message = self._socket.recv()
            except self._deps.zmq.error.Again as error:
                self._init_socket()
                raise G1SonicTransportTimeout(
                    f"PolicyClient request to {self.endpoint} timed out after "
                    f"{self.timeout_ms} ms"
                ) from error
            except self._deps.zmq.error.ZMQError as error:
                self._init_socket()
                raise G1SonicTransportUnavailable(
                    f"PolicyClient transport failure at {self.endpoint}: {error}"
                ) from error

        if message == b"ERROR":
            raise G1SonicServerError("Policy server returned the legacy ERROR sentinel")
        response = SafePolicyWireSerializer.from_bytes(message)
        if isinstance(response, Mapping):
            error = response.get("error", response.get(b"error"))
            if error is not None:
                raise G1SonicServerError(f"Policy server error: {error}")
        return response

    def ping(self) -> bool:
        """Probe reachability; constructor alone never claims a live server."""

        try:
            response = self.call_endpoint("ping", requires_input=False)
        except G1SonicTransportUnavailable:
            return False
        return isinstance(response, Mapping) and response.get("status") == "ok"

    def get_action(
        self,
        observation: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(observation, Mapping):
            raise TypeError("observation must be a mapping")
        if options is not None and not isinstance(options, Mapping):
            raise TypeError("options must be a mapping or None")
        response = self.call_endpoint(
            "get_action",
            {
                "observation": dict(observation),
                "options": None if options is None else dict(options),
            },
        )
        return validate_unitree_g1_sonic_response(response)

    def reset(
        self,
        options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if options is not None and not isinstance(options, Mapping):
            raise TypeError("options must be a mapping or None")
        response = self.call_endpoint(
            "reset",
            {"options": None if options is None else dict(options)},
        )
        if not isinstance(response, Mapping):
            raise G1SonicProtocolError("reset response must be a mapping")
        return dict(response)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        socket = self._socket
        self._socket = None
        if socket is not None:
            socket.close(linger=0)
        self._context.term()

    def __enter__(self) -> G1SonicPolicyClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
