#!/usr/bin/env python3
"""Static file server for the MyActuator web dashboard.

Serves the ``web/`` directory so the dashboard can be opened over
``http://localhost:8000`` (WebSerial requires a secure context; localhost
counts as secure in Chrome/Edge).

Usage:
    python3 web/serve.py [port]   # default port 8000
"""
import sys
import os
import json
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from rl_service import RLTrainingManager
from physics_service import PhysicsRuntimeRegistry

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
RL_MANAGER = RLTrainingManager(Path(PROJECT_ROOT))
PHYSICS_REGISTRY = PhysicsRuntimeRegistry(Path(PROJECT_ROOT))
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
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 32_768:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        payload = json.loads(raw or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _is_loopback(self):
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def do_GET(self):
        request_path = urlsplit(self.path).path
        if request_path == "/api/rl/status":
            self._send_json(200, RL_MANAGER.snapshot())
            return
        if request_path == "/api/rl/sessions":
            self._send_json(200, RL_MANAGER.list_sessions())
            return
        if request_path == "/api/physics/status":
            self._send_json(200, PHYSICS_REGISTRY.snapshot())
            return
        super().do_GET()

    def do_POST(self):
        request_path = urlsplit(self.path).path
        if request_path not in {"/api/rl/train", "/api/rl/stop"}:
            self._send_json(404, {"error": "not found"})
            return
        if not self._is_loopback():
            self._send_json(403, {"error": "RL process control is loopback-only"})
            return
        try:
            if request_path == "/api/rl/train":
                state = RL_MANAGER.start(self._read_json())
                self._send_json(202, state)
            else:
                state = RL_MANAGER.stop()
                self._send_json(200, state)
        except (ValueError, RuntimeError) as error:
            self._send_json(409 if isinstance(error, RuntimeError) else 400, {
                "error": str(error),
            })

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.chdir(HERE)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Dropbear digital twin: http://localhost:{port}", flush=True)
    print("Serving local Three.js modules and tracked STEP-derived CAD.", flush=True)
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
