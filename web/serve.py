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
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
ALIASES = {
    "/node_modules/": os.path.join(HERE, "node_modules"),
    "/cad-candidate/": os.path.join(
        PROJECT_ROOT, "generated", "myactuator", "cad", "candidate_exports"
    ),
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def translate_path(self, path):
        request_path = unquote(urlsplit(path).path)
        for prefix, root in ALIASES.items():
            if request_path.startswith(prefix):
                relative = request_path[len(prefix):].lstrip("/")
                resolved_root = os.path.realpath(root)
                target = os.path.realpath(os.path.join(resolved_root, relative))
                if os.path.commonpath((resolved_root, target)) != resolved_root:
                    return resolved_root
                return target
        return super().translate_path(path)

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
