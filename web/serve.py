#!/usr/bin/env python3
"""Static file server for the MyActuator web dashboard.

Serves the ``web/`` directory so the dashboard can be opened over
``http://localhost:8000`` (WebSerial requires a secure context; localhost
counts as secure in Chrome/Edge).

Usage:
    python3 web/serve.py [port]   # default port 8000
"""
import hmac
import ipaddress
import json
import math
import os
import secrets
import signal
import sys
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from rl_service import RLTrainingManager
from physics_service import PhysicsRuntimeRegistry
from gr00t_service import (
    DropbearPromptPlanner,
    Gr00tRuntimeInspector,
    Gr00tTrainingManager,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
RL_MANAGER = RLTrainingManager(Path(PROJECT_ROOT))
PHYSICS_REGISTRY = PhysicsRuntimeRegistry(Path(PROJECT_ROOT))
GR00T_INSPECTOR = Gr00tRuntimeInspector(Path(PROJECT_ROOT))
GR00T_TRAINING = Gr00tTrainingManager(
    Path(PROJECT_ROOT), GR00T_INSPECTOR
)
GR00T_PROMPT_PLANNER = DropbearPromptPlanner()
CONTROL_TOKEN = secrets.token_urlsafe(32)
MAX_JSON_BODY_BYTES = 32_768
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ALIASES = {
    "/node_modules/": os.path.join(HERE, "node_modules"),
    "/cad-candidate/": os.path.join(
        PROJECT_ROOT, "generated", "myactuator", "cad", "candidate_exports"
    ),
    "/artifacts/": os.path.join(PROJECT_ROOT, "artifacts"),
}
SOURCE_FILES = {
    "/cad-source/dropbear-x8-pro.step": os.path.join(
        PROJECT_ROOT,
        "assets", "vendor", "myactuator", "RMD-X", "X8-25", "vendor",
        "X8-25 Product information 240814", "2D 3D",
        "X8-25 (RMD-X8 PRO 1：9 V2).step",
    ),
    "/cad-source/dropbear-x10-s2.step": os.path.join(
        PROJECT_ROOT,
        "assets", "vendor", "myactuator", "RMD-X", "X10-100", "vendor", "X10-100",
        "(RMD-X10-S2 V3)Product information 240220", "2D 3D",
        "RMD-X10-S2 V3.step",
    ),
}


class UnsupportedMediaType(ValueError):
    """Raised when a control request is not encoded as JSON."""


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _require_finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON numbers are not allowed")
    if isinstance(value, dict):
        for item in value.values():
            _require_finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _require_finite_json(item)


def _is_loopback_address(address):
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        return parsed.is_loopback
    except ValueError:
        return False


def _host_parts(value):
    if not value or any(character in value for character in "\r\n,/@"):
        return None
    try:
        parsed = urlsplit(f"//{value.strip()}")
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port if parsed.port is not None else 80
    except ValueError:
        return None
    return hostname, port


def _is_loopback_bind_host(host):
    if host.lower().rstrip(".") == "localhost":
        return True
    return _is_loopback_address(host)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def end_headers(self):
        # This is a live engineering dev server; stale ES modules can leave the
        # visible controls out of sync with the current HTML during iteration.
        if urlsplit(self.path).path.endswith((".html", ".js", ".css")) or self.path == "/":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        request_path = unquote(urlsplit(path).path)
        if request_path in SOURCE_FILES:
            return os.path.realpath(SOURCE_FILES[request_path])
        for prefix, root in ALIASES.items():
            if request_path.startswith(prefix):
                relative = request_path[len(prefix):].lstrip("/")
                resolved_root = os.path.realpath(root)
                target = os.path.realpath(os.path.join(resolved_root, relative))
                if os.path.commonpath((resolved_root, target)) != resolved_root:
                    return resolved_root
                return target
        return super().translate_path(path)

    def _send_json(self, status, payload):
        try:
            body = json.dumps(
                payload,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            status = 500
            body = b'{"error":"response is not finite JSON"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise UnsupportedMediaType(
                "Content-Type must be application/json"
            )
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("transfer-encoded request bodies are not supported")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length, 10)
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length <= 0:
            raise ValueError("request body must contain a JSON object")
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(
                raw.decode("utf-8"),
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("request body must be valid UTF-8 JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        _require_finite_json(payload)
        return payload

    def _is_loopback(self):
        return _is_loopback_address(self.client_address[0])

    def _local_request_host(self):
        host = _host_parts(self.headers.get("Host"))
        return (
            host
            if host is not None
            and host[0] in LOCAL_HOSTS
            and host[1] == self.server.server_port
            else None
        )

    def _same_origin(self, request_host):
        for header in ("Origin", "Referer"):
            value = self.headers.get(header)
            if not value:
                continue
            try:
                parsed = urlsplit(value)
                if parsed.username is not None or parsed.password is not None:
                    return False
                origin_host = (parsed.hostname or "").lower().rstrip(".")
                origin_port = (
                    parsed.port
                    if parsed.port is not None
                    else (80 if parsed.scheme == "http" else 443)
                )
            except ValueError:
                return False
            if (
                parsed.scheme != "http"
                or (origin_host, origin_port) != request_host
            ):
                return False
        return True

    def _authorize_control(self):
        if not self._is_loopback():
            return "training and prompt control are loopback-only"
        request_host = self._local_request_host()
        if request_host is None:
            return "control requires a loopback Host header"
        if not self._same_origin(request_host):
            return "control requires a same-origin request"
        supplied = self.headers.get("X-Dropbear-Control-Token", "")
        if not hmac.compare_digest(supplied, CONTROL_TOKEN):
            return "invalid control token"
        return None

    def do_GET(self):
        request_path = urlsplit(self.path).path
        if request_path == "/api/control-token":
            if not self._is_loopback() or self._local_request_host() is None:
                self._send_json(403, {
                    "error": "control token is available only on loopback",
                })
            else:
                self._send_json(200, {"token": CONTROL_TOKEN})
            return
        if request_path == "/api/rl/status":
            self._send_json(200, RL_MANAGER.snapshot())
            return
        if request_path == "/api/rl/sessions":
            self._send_json(200, RL_MANAGER.list_sessions())
            return
        if request_path == "/api/physics/status":
            self._send_json(200, PHYSICS_REGISTRY.snapshot())
            return
        if request_path == "/api/gr00t/status":
            self._send_json(200, {
                **GR00T_INSPECTOR.snapshot(),
                "training": GR00T_TRAINING.snapshot(),
            })
            return
        if request_path == "/api/gr00t/sessions":
            self._send_json(200, GR00T_TRAINING.list_sessions())
            return
        super().do_GET()

    def do_POST(self):
        request_path = urlsplit(self.path).path
        authorization_error = self._authorize_control()
        if authorization_error:
            self._send_json(403, {"error": authorization_error})
            return
        try:
            payload = self._read_json()
            supported = {
                "/api/rl/train",
                "/api/rl/stop",
                "/api/gr00t/prompt",
                "/api/gr00t/train",
                "/api/gr00t/stop",
            }
            if request_path not in supported:
                self._send_json(404, {"error": "not found"})
                return
            if request_path == "/api/rl/train":
                state = RL_MANAGER.start(payload)
                self._send_json(202, state)
            elif request_path == "/api/rl/stop":
                state = RL_MANAGER.stop()
                self._send_json(200, state)
            elif request_path == "/api/gr00t/prompt":
                plan = GR00T_PROMPT_PLANNER.plan(
                    payload.get("prompt")
                )
                self._send_json(200, plan.as_payload())
            elif request_path == "/api/gr00t/train":
                state = GR00T_TRAINING.start(payload)
                self._send_json(202, state)
            else:
                self._send_json(200, GR00T_TRAINING.stop())
        except UnsupportedMediaType as error:
            self._send_json(415, {"error": str(error)})
        except (ValueError, RuntimeError) as error:
            self._send_json(409 if isinstance(error, RuntimeError) else 400, {
                "error": str(error),
            })

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


def _shutdown_managers():
    for label, callback in (
        ("GR00T training", GR00T_TRAINING.shutdown),
        ("RL training", RL_MANAGER.stop),
    ):
        try:
            callback()
        except Exception as error:  # Best-effort teardown must close the server.
            sys.stderr.write(f"[serve] {label} shutdown failed: {error}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    host = os.environ.get("DROPBEAR_DASHBOARD_HOST", "127.0.0.1").strip()
    if not host:
        raise SystemExit("DROPBEAR_DASHBOARD_HOST cannot be empty")
    if (
        not _is_loopback_bind_host(host)
        and os.environ.get("DROPBEAR_ALLOW_REMOTE") != "1"
    ):
        raise SystemExit(
            "non-loopback dashboard binding requires DROPBEAR_ALLOW_REMOTE=1"
        )
    os.chdir(HERE)
    httpd = ThreadingHTTPServer((host, port), Handler)
    shutdown_started = threading.Event()

    def request_shutdown(signum, _frame):
        if shutdown_started.is_set():
            return
        shutdown_started.set()
        print(f"\nreceived signal {signum}; stopping.", flush=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    display_host = "localhost" if _is_loopback_bind_host(host) else host
    print(f"Dropbear digital twin: http://{display_host}:{port}", flush=True)
    print("Serving local Three.js modules and tracked STEP-derived CAD.", flush=True)
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    finally:
        try:
            _shutdown_managers()
        finally:
            httpd.server_close()
        print("stopped.", flush=True)


if __name__ == "__main__":
    main()
