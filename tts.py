#!/usr/bin/env python3
"""TTS Android dengan satu worker FIFO supaya engine tidak di-init ulang.

Rujukan: termux/termux-api TextToSpeechAPI.java membaca stdin baris per baris
dan memakai satu instance TextToSpeech untuk semua utterance.
"""

import os
import pathlib
import re
import shlex
import subprocess
import threading
import time

LANG = os.environ.get("JARVIS_TTS_LANG", "id-ID")
RATE = os.environ.get("JARVIS_TTS_RATE", "1.15")
FIFO = pathlib.Path.home() / ".local/share/jarvis/tts.fifo"

_writer = None
_lock = threading.Lock()
_worker = None


def clean_for_speech(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"[`*_#>]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return " ".join(text.split())


def split_sentences(text, limit=170):
    parts = re.split(r"(?<=[.!?])\s+|(?<=\n)", clean_for_speech(text))
    out, current = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if current and len(current) + len(part) + 1 > limit:
            out.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        out.append(current)
    return out


def _tts_command():
    parts = ["termux-tts-speak", "-r", RATE]
    if LANG:
        parts += ["-l", LANG[:2], "-n", LANG[-2:]]
    return " ".join(shlex.quote(part) for part in parts)


def start():
    """Nyalakan satu worker TTS. Aman dipanggil berulang."""
    global _worker
    FIFO.parent.mkdir(parents=True, exist_ok=True)
    if FIFO.exists():
        FIFO.unlink()
    os.mkfifo(FIFO)
    script = f"while true; do cat '{FIFO}'; done | {_tts_command()}"
    _worker = subprocess.Popen(
        ["/data/data/com.termux/files/usr/bin/sh", "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _warmup():
        # Baris kosong memicu init engine saat startup, bukan saat jawaban pertama.
        time.sleep(0.2)
        try:
            with open(FIFO, "w") as fh:
                fh.write("\n")
        except OSError:
            pass

    threading.Thread(target=_warmup, daemon=True).start()


def speak(text):
    """Antrekan kalimat ke worker. Non-blok setelah engine siap."""
    global _writer
    for sentence in split_sentences(text):
        with _lock:
            if _writer is None or _writer.closed:
                _writer = open(FIFO, "w", buffering=1)
            try:
                _writer.write(sentence + "\n")
                _writer.flush()
            except (BrokenPipeError, OSError):
                _writer = None
                start()


if __name__ == "__main__":
    import sys

    start()
    speak(" ".join(sys.argv[1:]))
