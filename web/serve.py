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

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    os.chdir(HERE)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"MyActuator dashboard: http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
