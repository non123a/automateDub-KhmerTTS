from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice import transcription


def test_validate_audio_input_requires_wav(tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    with pytest.raises(transcription.VS1Error, match="audio file must be a WAV"):
        transcription.validate_audio_input(audio_path)


def test_validate_model_path_requires_file(tmp_path):
    with pytest.raises(transcription.VS1Error, match="model file does not exist"):
        transcription.validate_model_path(tmp_path / "missing.bin")


def test_build_whisper_cpp_command(tmp_path):
    command = transcription.build_whisper_cpp_command(
        "whisper-cli",
        tmp_path / "model.bin",
        tmp_path / "audio.wav",
        tmp_path / "transcript",
    )

    assert command == [
        "whisper-cli",
        "-m",
        str(tmp_path / "model.bin"),
        "-f",
        str(tmp_path / "audio.wav"),
        "-l",
        "zh",
        "-oj",
        "-of",
        str(tmp_path / "transcript"),
        "-np",
    ]


def test_normalize_whisper_cpp_payload_uses_offsets():
    payload = {
        "transcription": [
            {"offsets": {"from": 0, "to": 1250}, "text": "你好"},
            {"offsets": {"from": 1250, "to": 2500}, "text": "世界"},
        ]
    }

    transcript = transcription.normalize_whisper_cpp_payload(
        raw_payload=payload,
        source_audio="audio.wav",
        model_path=Path("ggml-small.bin"),
    )

    assert transcript.language == "zh"
    assert transcript.engine == {"provider": "local", "model": "whisper.cpp:ggml-small.bin"}
    assert transcript.text == "你好 世界"
    assert transcript.segments[0].start == 0.0
    assert transcript.segments[0].end == 1.25


def test_normalize_whisper_cpp_payload_uses_timestamps():
    payload = {
        "transcription": [
            {"timestamps": {"from": "00:00:01,000", "to": "00:00:02,500"}, "text": "你好"}
        ]
    }

    transcript = transcription.normalize_whisper_cpp_payload(
        raw_payload=payload,
        source_audio="audio.wav",
        model_path=Path("model.bin"),
    )

    assert transcript.segments[0].start == 1.0
    assert transcript.segments[0].end == 2.5


def test_write_transcript_writes_expected_schema(tmp_path):
    transcript = transcription.Transcript(
        version=1,
        language="zh",
        source_audio="audio.wav",
        engine={"provider": "local", "model": "whisper.cpp:ggml-small.bin"},
        text="你好",
        segments=[transcription.TranscriptSegment(id=0, start=0.0, end=1.0, text="你好")],
    )

    output = tmp_path / "transcript.json"
    transcription.write_transcript(output, transcript)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "language": "zh",
        "source_audio": "audio.wav",
        "engine": {"provider": "local", "model": "whisper.cpp:ggml-small.bin"},
        "text": "你好",
        "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "你好"}],
    }


def test_whisper_cpp_transcriber_invokes_cli_and_writes_transcript(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    model_path = tmp_path / "ggml-small.bin"
    model_path.write_bytes(b"model")

    monkeypatch.setattr(
        transcription,
        "resolve_executable",
        lambda executable: "/usr/bin/whisper-cli",
    )

    def fake_run(command, check, capture_output, text):
        output_base = Path(command[command.index("-of") + 1])
        output_base.with_suffix(".json").write_text(
            json.dumps({"transcription": [{"offsets": {"from": 0, "to": 1000}, "text": "你好"}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(transcription.subprocess, "run", fake_run)

    output_path = tmp_path / "transcript.json"
    transcriber = transcription.WhisperCppTranscriber(ToolConfig(whisper_model_path=model_path))
    result = transcriber.transcribe(audio_path, output_path)

    assert result.text == "你好"
    assert output_path.exists()


def test_run_whisper_cpp_reports_failure():
    command = ["whisper-cli"]

    def raise_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="bad model")

    original_run = transcription.subprocess.run
    transcription.subprocess.run = raise_error
    try:
        with pytest.raises(transcription.VS1Error, match="transcription failed: bad model"):
            transcription.run_whisper_cpp(command)
    finally:
        transcription.subprocess.run = original_run


def test_run_whisper_cpp_retries_signal_failure_with_no_gpu(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        if "-ng" not in command:
            raise subprocess.CalledProcessError(-11, command, stderr="")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(transcription.subprocess, "run", fake_run)

    transcription.run_whisper_cpp(["whisper-cli", "-m", "model.bin"])

    assert calls == [
        ["whisper-cli", "-m", "model.bin"],
        ["whisper-cli", "-m", "model.bin", "-ng"],
    ]
