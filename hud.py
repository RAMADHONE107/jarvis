#!/usr/bin/env python3
"""HUD web JARVIS: server SSE + endpoint perintah, tanpa dependency tambahan."""

import json
import pathlib
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
STATE_FILE = pathlib.Path.home() / ".local/share/jarvis/hud-state.json"

_state = {
    "mode": "idle",
    "user": "",
    "reply": "",
    "log": [],
    "level": 0.0,
    "wake": "Hey Jarvis",
    "brain": "opencode/big-pickle",
}
_lock = threading.Lock()
_inbox = queue.Queue()


def set_state(**updates):
    with _lock:
        _state.update(updates)
        snapshot = dict(_state)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(snapshot, ensure_ascii=False))
    except OSError:
        pass
    return snapshot


def snapshot():
    with _lock:
        return dict(_state)


def log(message):
    with _lock:
        _state["log"] = (_state["log"] + [str(message)])[-12:]


def next_input(timeout=1.0):
    try:
        return _inbox.get(timeout=timeout)
    except queue.Empty:
        return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "hud.html").read_text(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(snapshot(), ensure_ascii=False))
        elif self.path == "/api/info":
            self._send(200, json.dumps(_device_info(), ensure_ascii=False))
        elif self.path == "/events":
            self._events()
        else:
            self._send(404, json.dumps({"error": "tidak ditemukan"}))

    def do_POST(self):
        if self.path not in ("/api/text", "/api/wake"):
            self._send(404, json.dumps({"error": "tidak ditemukan"}))
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        if self.path == "/api/wake":
            _inbox.put("__WAKE__")
        else:
            try:
                text = json.loads(body).get("text", "").strip()
            except ValueError:
                text = body.strip()
            if text:
                _inbox.put(text)
        self._send(200, json.dumps({"ok": True}))

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        try:
            while True:
                current = snapshot()
                payload = json.dumps(current, ensure_ascii=False)
                if payload != last:
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    last = payload
                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *_args):
        pass


def _device_info():
    info = {}
    try:
        out = subprocess.run(
            ["termux-battery-status"], capture_output=True, text=True, timeout=3
        )
        if out.returncode == 0:
            info["battery"] = json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return info


def serve(port=8769):
    set_state(mode="idle")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    log(f"HUD aktif di http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import sys

    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8769)
