from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice import audio


def test_validate_input_mp4_requires_existing_file(tmp_path):
    with pytest.raises(audio.VS0Error, match="input file does not exist"):
        audio.validate_input_mp4(tmp_path / "missing.mp4")


def test_validate_input_mp4_requires_file(tmp_path):
    with pytest.raises(audio.VS0Error, match="input path is not a file"):
        audio.validate_input_mp4(tmp_path)


def test_validate_input_mp4_requires_mp4_suffix(tmp_path):
    input_path = tmp_path / "movie.mov"
    input_path.write_bytes(b"not real media")

    with pytest.raises(audio.VS0Error, match="input file must be an MP4"):
        audio.validate_input_mp4(input_path)


def test_build_extract_audio_command_uses_expected_wav_settings(tmp_path):
    input_path = tmp_path / "movie.mp4"
    output_path = tmp_path / "output" / "audio.wav"

    command = audio.build_extract_audio_command("/usr/bin/ffmpeg", input_path, output_path)

    assert command == [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]


def test_extract_audio_creates_output_directory_and_returns_audio_path(monkeypatch, tmp_path):
    input_path = tmp_path / "movie.mp4"
    input_path.write_bytes(b"fake mp4")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(audio, "resolve_executable", lambda name: "/usr/bin/ffmpeg")

    def fake_run(command, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is True
        Path(command[-1]).write_bytes(b"fake wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    result = audio.extract_audio(input_path, output_dir, ToolConfig())

    assert result == output_dir / "audio.wav"
    assert result.read_bytes() == b"fake wav"


def test_extract_audio_reports_ffmpeg_failure(monkeypatch, tmp_path):
    input_path = tmp_path / "movie.mp4"
    input_path.write_bytes(b"fake mp4")

    monkeypatch.setattr(audio, "resolve_executable", lambda name: "/usr/bin/ffmpeg")

    def fake_run(command, check, capture_output, text):
        raise subprocess.CalledProcessError(1, command, stderr="invalid media")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    with pytest.raises(audio.VS0Error, match="audio extraction failed: invalid media"):
        audio.extract_audio(input_path, tmp_path / "output", ToolConfig())

