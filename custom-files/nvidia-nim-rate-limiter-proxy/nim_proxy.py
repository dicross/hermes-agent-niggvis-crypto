#!/usr/bin/env python3
"""
NVIDIA NIM Rate Limiter Proxy — HTTPS edition
Listens on port 443 with a self-signed cert, intercepts requests
from the VS Code extension, throttles to RPM_LIMIT, then forwards
to the real integrate.api.nvidia.com.

Requires: nim_setup.sh to have been run first.
Usage:    sudo python3 nim_proxy.py
"""

import http.server
import http.client
import ssl
import socketserver
import threading
import time
import sys
import os
from collections import deque

# ── Configuration ─────────────────────────────────────────────
LOCAL_PORT  = 443
NVIDIA_HOST = "integrate.api.nvidia.com"
RPM_LIMIT   = 40
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
CERT_FILE   = os.path.join(CERT_DIR, "nim_cert.pem")
KEY_FILE    = os.path.join(CERT_DIR, "nim_key.pem")
# ──────────────────────────────────────────────────────────────

request_times = deque()
lock          = threading.Lock()
status_lock   = threading.Lock()
stats         = {"total": 0, "held": 0, "passed": 0}


# ── Sliding-window rate limiter ───────────────────────────────

def _evict(now):
    """Remove timestamps older than 60 s from the window."""
    while request_times and now - request_times[0] > 60:
        request_times.popleft()

def current_rpm():
    now = time.time()
    with lock:
        _evict(now)
        return len(request_times)

def wait_for_slot():
    """
    Block the calling thread until a request slot is available.
    No request is ever dropped — it is queued and sent as soon as
    the oldest entry leaves the 60-second sliding window.
    """
    while True:
        now = time.time()
        with lock:
            _evict(now)
            if len(request_times) < RPM_LIMIT:
                request_times.append(now)
                stats["passed"] += 1
                return  # slot acquired

        with lock:
            wait_sec = max(0.0, 60.0 - (time.time() - request_times[0])) + 0.05
            stats["held"] += 1

        render_status(waiting=True, wait_sec=wait_sec)
        time.sleep(min(wait_sec, 0.5))


# ── Terminal UI ───────────────────────────────────────────────

def render_status(waiting=False, wait_sec=0.0):
    rpm    = current_rpm()
    pct    = rpm / RPM_LIMIT
    W      = 36
    filled = int(pct * W)
    bar    = "X" * filled + "." * (W - filled)

    RED, YEL, GRN, RST = "\033[91m", "\033[93m", "\033[92m", "\033[0m"
    color  = RED if pct >= 0.90 else YEL if pct >= 0.65 else GRN
    sep    = "-" * 54

    out = "\033[H"
    out += f"+{sep}+\n"
    out += f"|  NVIDIA NIM Rate Limiter Proxy  (HTTPS :443){' '*9}|\n"
    out += f"|  Intercepting: https://integrate.api.nvidia.com{' '*5}|\n"
    out += f"+{sep}+\n"
    out += f"|  RPM: {color}{rpm:2d}/{RPM_LIMIT}{RST}  [{bar}]  {int(pct*100):3d}%  |\n"
    out += f"|  Total: {stats['total']:<5}  Forwarded: {stats['passed']:<5}  Queued: {stats['held']:<5}|\n"
    out += f"+{sep}+\n"

    if waiting:
        msg = f"  LIMIT REACHED -- resuming in {wait_sec:.1f}s ..."
        out += f"|{YEL}{msg:<54}{RST}|\n"
    else:
        msg = f"  Active -- accepting requests"
        out += f"|{GRN}{msg:<54}{RST}|\n"

    out += f"+{sep}+\n"

    with status_lock:
        sys.stdout.write(out)
        sys.stdout.flush()


# ── Reverse proxy handler ─────────────────────────────────────

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
}

class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def handle_request(self):
        stats["total"] += 1
        wait_for_slot()
        render_status()

        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in HOP_BY_HOP}
        fwd_headers["Host"] = NVIDIA_HOST

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else None

        # Forward to the real NVIDIA NIM over HTTPS
        upstream_ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(NVIDIA_HOST, context=upstream_ctx, timeout=120)

        try:
            conn.request(self.command, self.path, body=body, headers=fwd_headers)
            resp = conn.getresponse()

            self.send_response(resp.status)
            is_sse = False
            for name, value in resp.getheaders():
                if name.lower() in {"transfer-encoding", "connection"}:
                    continue
                self.send_header(name, value)
                if name.lower() == "content-type" and "event-stream" in value:
                    is_sse = True
            self.end_headers()

            if is_sse:
                while chunk := resp.read(256):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            else:
                self.wfile.write(resp.read())

        except Exception as exc:
            try:
                self.send_error(502, f"Proxy error: {exc}")
            except Exception:
                pass
        finally:
            conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = handle_request


class ThreadedProxy(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads      = True
    allow_reuse_address = True


if __name__ == "__main__":
    for f in (CERT_FILE, KEY_FILE):
        if not os.path.exists(f):
            print(f"ERROR: {f} not found. Run nim_setup.sh first.")
            sys.exit(1)

    render_status()

    server = ThreadedProxy(("0.0.0.0", LOCAL_PORT), ProxyHandler)

    # Wrap server socket with SSL (present self-signed cert to VS Code)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(CERT_FILE, KEY_FILE)
    server.socket = server_ctx.wrap_socket(server.socket, server_side=True)

    print(f"HTTPS proxy running on port {LOCAL_PORT}")
    print("Stop: Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy stopped.")
        server.shutdown()
