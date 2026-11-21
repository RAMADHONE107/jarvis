#!/usr/bin/env python3
"""Speech-to-text lokal memakai whisper.cpp dari GitHub."""

import pathlib
import struct
import subprocess
import tempfile
import wave

ROOT = pathlib.Path(__file__).resolve().parent
WHISPER = ROOT / "whisper.cpp/build/bin/whisper-cli"
MODELS = ROOT / "models"
WAKE_MODEL = MODELS / "ggml-tiny.bin"
VOICE_MODEL = MODELS / "ggml-base.bin"


def to_wav(pcm, path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)


def rms(pcm):
    if not pcm:
        return 0
    count = len(pcm) // 2
    if count == 0:
        return 0
    total = sum(v * v for v in struct.unpack(f"<{count}h", pcm[: count * 2]))
    return (total / count) ** 0.5


def transcribe(pcm, model=None, lang="id", threads=4, timeout=120):
    model = model or VOICE_MODEL
    if not WHISPER.exists():
        raise RuntimeError("whisper.cpp belum ter-build")
    if not model.exists():
        raise RuntimeError(f"model {model.name} belum diunduh")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        wav = tmp / "in.wav"
        to_wav(pcm, wav)
        cmd = [
            str(WHISPER),
            "-m", str(model),
            "-f", str(wav),
            "-l", lang,
            "-t", str(threads),
            "-otxt",
            "-of", str(tmp / "out"),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        out = tmp / "out.txt"
        if out.exists():
            return " ".join(out.read_text(errors="ignore").split()).strip()
        return ""
