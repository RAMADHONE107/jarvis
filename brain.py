#!/usr/bin/env python3
"""Jembatan dari pipeline suara ke agen OpenCode (otak JARVIS)."""

import datetime
import json
import pathlib
import re
import subprocess
import time

HOME = pathlib.Path.home()
STATE = HOME / ".local/share/jarvis"
STATE.mkdir(parents=True, exist_ok=True)
SESSION_FILE = STATE / "opencode_session.txt"

CLI = "opencode-termux"
INSTRUCTION = (
    "[JARVIS] Otak asisten suara Termux. Jawab maksimal 2 kalimat pendek, Bahasa Indonesia, "
    "tanpa markdown, cocok dibacakan. Pakai tool termux hanya kalau butuh aksi nyata.\n"
    "Perintah: "
)


def api(method, path, data=None):
    cmd = [CLI, "api", method, path]
    if data is not None:
        cmd += ["--data", json.dumps(data, ensure_ascii=False)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "opencode api gagal")
    return json.loads(proc.stdout)["data"]


def ensure_session():
    if SESSION_FILE.exists():
        session_id = SESSION_FILE.read_text().strip()
        if session_id:
            return session_id
    session = api("post", "/api/session", {"title": "Jarvis Brain"})
    SESSION_FILE.write_text(session["id"])
    return session["id"]


def _assistant_messages(session_id):
    messages = api("get", f"/api/session/{session_id}/message")
    return [m for m in messages if m.get("type") == "assistant"]


def _text_of(message):
    chunks = []
    for part in message.get("content", []):
        if part.get("type") == "text" and part.get("text", "").strip():
            chunks.append(part["text"].strip())
    return "\n".join(chunks).strip()


def fast_answer(text):
    """Refleks untuk data perangkat yang tidak perlu lewat LLM."""
    low = text.lower()
    if re.search(r"baterai|battery|daya\s+baterai", low):
        try:
            proc = subprocess.run(
                ["termux-battery-status"], capture_output=True, text=True, timeout=4
            )
            data = json.loads(proc.stdout)
            status = "sedang diisi" if data.get("plugged") != "UNPLUGGED" else "tidak diisi"
            return f"Baterai {data.get('percentage')} persen, {status}."
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    if re.search(r"jam\s+berapa|waktu\s+berapa|jam\s+sekarang", low):
        return f"Jam {datetime.datetime.now():%H.%M}."
    if re.search(r"(putar|mainkan|buka|play)\s+(musik|lagu|music)", low):
        try:
            subprocess.run(
                ["am", "start", "--user", "0", "-a", "android.intent.action.MUSIC_PLAYER"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return "Oke, pemutar musik kubuka."

    apps = {
        "youtube": "com.google.android.youtube",
        "youtube music": "com.google.android.apps.youtube.music",
        "kamera": "com.android.camera2",
        "camera": "com.android.camera2",
        "browser": "com.android.chrome",
        "chrome": "com.android.chrome",
    }
    for name, package in apps.items():
        if re.search(r"buka\s+" + re.escape(name), low):
            try:
                subprocess.run(
                    ["am", "start", "--user", "0", "-a", "android.intent.action.MAIN",
                     "-c", "android.intent.category.LAUNCHER", "-p", package],
                    capture_output=True, timeout=5, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            return f"Oke, {name} kubuka."

    if re.search(r"notifikasi|notif|kirim\s+pesan", low):
        content = re.sub(
            r"^(tolong\s+)?(kirim\s+)?(notifikasi|notif|pesan)\s*(tentang|bahwa|isi\s+)?",
            "", low,
        ).strip() or "Halo dari JARVIS."
        try:
            subprocess.run(
                ["termux-notification", "--title", "JARVIS", "--content", content],
                capture_output=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return f"Notifikasi terkirim: {content}"

    if re.search(r"wifi|wi-fi|jaringan", low):
        try:
            proc = subprocess.run(
                ["termux-wifi-connectioninfo"], capture_output=True, text=True, timeout=5
            )
            data = json.loads(proc.stdout)
            ssid = data.get("ssid") or ""
            if not ssid or "unknown" in ssid.lower():
                return "Terhubung ke WiFi, nama jaringan tidak tersedia."
            return f"Terhubung ke WiFi {ssid}."
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    return None


def ask(text, timeout=240):
    """Kirim ucapan user ke otak dan tunggu jawaban finalnya."""
    reflex = fast_answer(text)
    if reflex:
        return reflex
    session_id = ensure_session()
    before_ids = {m["id"] for m in _assistant_messages(session_id)}
    api("post", f"/api/session/{session_id}/prompt", {"text": INSTRUCTION + text})
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        for message in reversed(_assistant_messages(session_id)):
            if message["id"] in before_ids:
                continue
            reply = _text_of(message)
            if reply:
                return reply
    raise TimeoutError("otak tidak merespons tepat waktu")


if __name__ == "__main__":
    import sys

    print(ask(" ".join(sys.argv[1:])))
