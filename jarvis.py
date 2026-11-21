#!/usr/bin/env python3
"""J.A.R.V.I.S. cepat untuk Termux: Android STT -> OpenCode -> TTS."""

import pathlib
import queue
import re
import subprocess
import threading
import time

import brain
import hud
import tts

# SpeechRecognizer mengubah "Hey Jarvis" jadi beberapa variasi; tangkap semuanya.
WAKE = re.compile(
    r"\b(hey|hei|hi|hai)?\s*(jarvis|jarwis|jarbis|javis|harvis|yarpiece|yarvis|jervis)\b",
    re.I,
)
EXIT = re.compile(r"\b(keluar|berhenti|mati|stop)\b", re.I)
SHORT_WAKE = re.compile(r"^(hey|hei|hi|hai|yo|jarvis|jarwis)\b", re.I)
BEEP = pathlib.Path(__file__).resolve().parent / "beep.wav"
REPLY_SCRIPT = pathlib.Path(__file__).resolve().parent / "bin/jarvis-reply"
CONVO_SECONDS = 45
START_SECONDS = 12
_convo_until = 0.0
_degraded = False
_short_wakes = 0
_last_short = 0.0

_events = queue.Queue()
_proc = None
_running = True
_speaking = threading.Event()


def note(message):
    print(f"[jarvis] {message}", flush=True)
    hud.log(message)


def chime():
    """Tanda dengar tanpa memblokir jendela perintah."""
    threading.Thread(target=_chime_blocking, daemon=True).start()


def _chime_blocking():
    try:
        subprocess.run(
            ["termux-media-player", "play", str(BEEP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    vibrate()


def vibrate(ms=70):
    try:
        subprocess.run(["termux-vibrate", "-d", str(ms)], timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def notify(content):
    """Notifikasi permanen; tombol Tanya memakai Direct Reply saat mikrofon sibuk."""
    cmd = [
        "termux-notification",
        "--id", "jarvis",
        "--ongoing",
        "-t", "JARVIS siap",
        "-c", " ".join(str(content).split())[:140],
        "--button1", "Tanya",
        "--button1-action", f'{REPLY_SCRIPT} "$REPLY"',
        "--button2", "HUD",
        "--button2-action", "am start -a android.intent.action.VIEW -d http://127.0.0.1:8769",
        "--priority", "high",
    ]
    try:
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def recognizer_loop():
    """Jalankan SpeechRecognizer Android terus, kirim hasil akhir ke _events."""
    global _proc
    while _running:
        lines = []
        try:
            _proc = subprocess.Popen(
                ["termux-speech-to-text", "-p"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            for line in _proc.stdout:
                line = line.strip()
                if line and not _speaking.is_set():
                    lines.append(line)
                    hud.set_state(mode="listening", user=line)
            _proc.wait()
        except (OSError, subprocess.SubprocessError) as exc:
            note(f"recognizer: {exc}")
        finally:
            _proc = None
        if lines and not _speaking.is_set():
            _events.put(("voice", lines[-1]))
        time.sleep(0.15)


def stop_recognizer():
    proc = _proc
    if proc is not None and proc.poll() is None:
        proc.terminate()


def listen(timeout=60):
    """Tunggu satu masukan: dari HUD atau dari suara."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = hud.next_input(0.2)
        if item == "__WAKE__":
            return "wake", ""
        if item:
            return "hud", item
        try:
            kind, text = _events.get(timeout=0.2)
            if kind == "voice":
                return kind, text
        except queue.Empty:
            continue
    return "", ""


def respond(text):
    global _convo_until, _degraded, _short_wakes
    note(f"perintah: {text}")
    hud.set_state(mode="thinking", user=text, reply="")
    started = time.time()
    try:
        answer = brain.ask(text)
    except Exception as exc:
        answer = f"Maaf, otak saya bermasalah. {exc}"
    note(f"jawaban ({time.time() - started:.1f}s): {answer}")
    _degraded = False
    _short_wakes = 0
    notify(answer)
    hud.set_state(mode="speaking", reply=answer)
    _speaking.set()
    try:
        tts.speak(answer)
    finally:
        while not _events.empty():
            try:
                _events.get_nowait()
            except queue.Empty:
                break
        time.sleep(0.3)
        _speaking.clear()
    hud.set_state(mode="idle")
    _convo_until = time.time() + CONVO_SECONDS


def _start_hud():
    try:
        hud.serve()
    except OSError:
        note("HUD sudah berjalan di port 8769")


def main():
    global _convo_until, _degraded, _short_wakes, _last_short
    threading.Thread(target=_start_hud, daemon=True).start()
    tts.start()
    threading.Thread(target=recognizer_loop, daemon=True).start()
    notify("Ketuk Tanya untuk kirim perintah, juga saat telepon.")
    note("JARVIS online. Katakan 'Hey Jarvis'.")
    vibrate(60)

    while True:
        source, text = listen()
        if not source:
            continue
        clean = text.strip()
        if not clean and source != "wake":
            continue

        if source in ("hud", "wake"):
            if source == "wake":
                hud.set_state(mode="listening", user="")
                chime()
                _convo_until = time.time() + START_SECONDS
                note(f"siap perintah {START_SECONDS} detik")
                continue
            if EXIT.search(clean):
                note("keluar lewat HUD")
                break
            respond(clean)
            continue

        # Dari suara: wake word eksplisit.
        match = WAKE.search(clean)
        if match:
            command = clean[match.end():].strip(" ,.-:!")
            if command:
                stop_recognizer()
                respond(command)
            else:
                hud.set_state(mode="listening", user="")
                chime()
                _convo_until = time.time() + START_SECONDS
                note(f"siap perintah {START_SECONDS} detik")
            continue

        # Masih dalam jendela obrolan: semua ucapan jadi perintah.
        if time.time() < _convo_until:
            if SHORT_WAKE.fullmatch(clean) or len(clean) < 3:
                chime()
                continue
            if EXIT.search(clean):
                note("keluar")
                break
            stop_recognizer()
            respond(clean)
            continue

        # Wake terpotong jadi "hey" saja. Kalau berulang, mikrofon sedang dipakai telepon.
        if SHORT_WAKE.match(clean) or len(clean) < 3:
            now = time.time()
            if not _degraded and _short_wakes and now - _last_short < 25:
                _degraded = True
                note("audio sibuk: pakai notifikasi Tanya saat telepon")
                hud.set_state(mode="call", reply="Mikrofon sibuk. Ketuk notifikasi JARVIS > Tanya.")
                notify("Mikrofon sibuk. Ketuk Tanya untuk kirim perintah.")
            _short_wakes += 1
            _last_short = now
            hud.set_state(mode="listening", user="")
            if not _degraded:
                chime()
            _convo_until = now + START_SECONDS
            if not _degraded:
                note(f"wake pendek, siap perintah {START_SECONDS} detik")
            continue

        note(f"abaikan (tanpa wake): {clean}")
        hud.set_state(mode="idle", user="")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
