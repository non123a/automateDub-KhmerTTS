"""Verify a staged native Whisper.cpp runtime independently from PATH."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import tempfile
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin"


def write_wav(path: Path) -> None:
    sample_rate = 16_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate):
            value = int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            frames.extend(value.to_bytes(2, "little", signed=True))
        output.writeframes(bytes(frames))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "macos", "linux"), required=True)
    args = parser.parse_args()
    executable_name = "whisper-cli.exe" if args.platform == "windows" else "whisper-cli"
    executable = (
        ROOT
        / "automatedub_studio"
        / "resources"
        / "runtime"
        / "whisper"
        / args.platform
        / executable_name
    )
    if not executable.is_file():
        raise RuntimeError(f"Bundled Whisper.cpp executable is missing: {executable}")
    with tempfile.TemporaryDirectory(prefix="automatedub-whisper-verify-") as directory:
        root = Path(directory)
        audio = root / "speech.wav"
        model = root / "ggml-small.bin"
        output = root / "transcript"
        write_wav(audio)
        print("Downloading required speech recognition model for runtime verification...")
        urllib.request.urlretrieve(MODEL_URL, model)
        environment = {key: value for key, value in os.environ.items() if key.upper() != "PATH"}
        # This validates the executable, model, WAV input, JSON output, and no-PATH execution.
        subprocess.run(
            [
                str(executable),
                "-m",
                str(model),
                "-f",
                str(audio),
                "-l",
                "zh",
                "-oj",
                "-of",
                str(output),
            ],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        transcript = output.with_suffix(".json")
        if not transcript.is_file() or transcript.stat().st_size == 0:
            raise RuntimeError("Bundled Whisper.cpp did not produce a transcript JSON artifact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
