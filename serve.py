#!/usr/bin/env python3
"""
serve.py — DDoS test target.

A simple threaded HTTP server that responds to:
    GET /        → HTML page (200)
    GET /ping    → "pong" (200)
    GET /health  → JSON status (200)

Binds to $PORT (required by Heroku).
"""

import http.server
import socketserver
import os
import sys
import json
import time

PORT = int(os.environ.get("PORT", 8080))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            body = b"pong"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "time": time.time(),
                "server": "heroku-target"
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Default page
        html = b"""<!DOCTYPE html>
<html>
<head>
    <title>DDoS Test Target</title>
    <meta charset="utf-8">
</head>
<body style="font-family:system-ui,sans-serif;text-align:center;margin-top:50px;background:#1a1a1a;color:#eee;">
    <h1 style="color:#0f0;">Target is Online</h1>
    <p>This Heroku app is a test target.</p>
    <p>Use this URL to test your bot's HTTP flood.</p>
    <p style="margin-top:30px;">
        <a style="color:#0af;margin:0 10px;" href="/ping">/ping</a>
        <a style="color:#0af;margin:0 10px;" href="/health">/health</a>
    </p>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, fmt, *args):
        # Suppress default logs to avoid Heroku log spam during floods
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    try:
        server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
        print(f"[web] Serving on 0.0.0.0:{PORT}", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"[web] Fatal: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
