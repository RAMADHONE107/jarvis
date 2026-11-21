#!/usr/bin/env python3
"""Continuous 16 kHz mono microphone via PulseAudio (OpenSL ES source)."""

import subprocess


class Mic:
    def __init__(self, source="@DEFAULT_SOURCE@", rate=16000, channels=1):
        self.rate = rate
        self.bytes_per_second = rate * channels * 2
        self.proc = subprocess.Popen(
            [
                "parec",
                "--raw",
                f"--device={source}",
                "--format=s16le",
                f"--rate={rate}",
                f"--channels={channels}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=self.bytes_per_second * 4,
        )

    def read(self, seconds):
        need = int(seconds * self.bytes_per_second)
        chunks = []
        got = 0
        while got < need:
            chunk = self.proc.stdout.read(need - got)
            if not chunk:
                break
            chunks.append(chunk)
            got += len(chunk)
        return b"".join(chunks)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
