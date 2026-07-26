from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from automatedub.vertical_slice import mix, tts_combine


def minimal_translation_payload() -> dict[str, object]:
    return {
        "version": 1,
        "source_transcript": "transcript.json",
        "prompt_artifact": "translation_prompt.json",
        "engine": {"provider": "openai-compatible", "model": "test-model"},
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 1.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "你好",
                "target_text": "សួស្តី។",
                "notes": None,
            },
            {
                "id": 12,
                "start": 1.25,
                "end": 2.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "拜拜",
                "target_text": "លាហើយ។",
                "notes": None,
            },
        ],
    }


def test_build_combine_speech_tracks_skips_missing_tts_files(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    (tts_dir / "0012.wav").write_bytes(b"fake-wav-bytes")
    segments = [
        mix.MixTranslationSegment(id=0, start=0.0, end=1.0, target_text="សួស្តី។"),
        mix.MixTranslationSegment(id=12, start=1.25, end=2.0, target_text="លាហើយ។"),
    ]

    tracks = tts_combine.build_combine_speech_tracks(segments, tts_dir)

    assert tracks == [
        tts_combine.CombineSpeechTrack(
            id=12,
            start=1.25,
            delay_ms=1250,
            tts_path=tts_dir / "0012.wav",
        )
    ]


def test_build_combine_speech_tracks_places_segments_at_source_start_with_no_offset(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    (tts_dir / "0000.wav").write_bytes(b"fake-wav-bytes")
    (tts_dir / "0012.wav").write_bytes(b"fake-wav-bytes")
    segments = [
        mix.MixTranslationSegment(id=0, start=0.0, end=1.0, target_text="សួស្តី។"),
        mix.MixTranslationSegment(id=12, start=1.25, end=2.0, target_text="លាហើយ។"),
    ]

    tracks = tts_combine.build_combine_speech_tracks(segments, tts_dir)

    assert [track.delay_ms for track in tracks] == [0, 1250]
    assert [track.start for track in tracks] == [0.0, 1.25]


def test_build_combine_command_generates_silent_base_and_delayed_segments(tmp_path):
    output_path = tmp_path / "tts_combined.wav"
    tracks = [
        tts_combine.CombineSpeechTrack(
            id=0,
            start=0.0,
            delay_ms=0,
            tts_path=tmp_path / "tts" / "0000.wav",
        ),
        tts_combine.CombineSpeechTrack(
            id=12,
            start=1.25,
            delay_ms=1250,
            tts_path=tmp_path / "tts" / "0012.wav",
        ),
    ]

    command = tts_combine.build_combine_command(
        ffmpeg="/usr/bin/ffmpeg",
        source_duration=14.0,
        speech_tracks=tracks,
        tts_combined_path=output_path,
    )

    assert command[:5] == ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    assert "-f" in command
    assert command[command.index("-f") + 1] == "lavfi"
    assert "anullsrc=channel_layout=mono:sample_rate=16000" in command
    assert command.count("-t") == 2
    assert "14.000" in command
    assert str(tracks[0].tts_path) in command
    assert str(tracks[1].tts_path) in command
    assert "-filter_complex" in command
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "adelay=0:all=1[seg1]" in filter_complex
    assert "adelay=1250:all=1[seg2]" in filter_complex
    assert "atempo" not in filter_complex
    assert "volume" not in filter_complex
    assert "amix=inputs=3:duration=first:dropout_transition=0:normalize=0[combined]" in filter_complex
    assert command[-1] == str(output_path)


def test_build_combine_command_with_no_speech_tracks(tmp_path):
    output_path = tmp_path / "tts_combined.wav"

    command = tts_combine.build_combine_command(
        ffmpeg="/usr/bin/ffmpeg",
        source_duration=5.0,
        speech_tracks=[],
        tts_combined_path=output_path,
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "amix=inputs=1:duration=first:dropout_transition=0:normalize=0[combined]" in filter_complex


def test_run_tts_combine_writes_plan_and_combined_audio(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audio.wav").write_bytes(b"source")
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    tts_dir = output_dir / "tts"
    tts_dir.mkdir()
    (tts_dir / "0000.wav").write_bytes(b"fake-wav-bytes")
    (tts_dir / "0012.wav").write_bytes(b"fake-wav-bytes")

    monkeypatch.setattr(
        mix,
        "resolve_executable",
        lambda executable: f"/usr/bin/{executable}",
    )

    def fake_run(command, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is True
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="14.000000\n")
        Path(command[-1]).write_bytes(b"combined")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mix.subprocess, "run", fake_run)

    result = tts_combine.run_tts_combine(output_dir)

    assert result.tts_combined_path == output_dir / "tts_combined.wav"
    assert result.tts_combined_plan_path == output_dir / "tts_combined_plan.json"
    assert result.included_segments == 2
    assert result.skipped_segments == 0
    assert result.tts_combined_path.read_bytes() == b"combined"

    plan = json.loads(result.tts_combined_plan_path.read_text(encoding="utf-8"))
    assert plan["duration_seconds"] == 14.0
    assert plan["included_segments"] == 2
    assert plan["skipped_segments"] == 0
    assert "generated_at" in plan
    assert "ffmpeg_command" in plan
    assert [segment["status"] for segment in plan["segments"]] == ["included", "included"]
    assert [segment["delay_ms"] for segment in plan["segments"]] == [0, 1250]


def test_run_tts_combine_marks_missing_tts_as_skipped(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audio.wav").write_bytes(b"source")
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    tts_dir = output_dir / "tts"
    tts_dir.mkdir()
    (tts_dir / "0012.wav").write_bytes(b"fake-wav-bytes")

    monkeypatch.setattr(
        mix,
        "resolve_executable",
        lambda executable: f"/usr/bin/{executable}",
    )

    def fake_run(command, check, capture_output, text):
        if command[0] == "/usr/bin/ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="14.000000\n")
        Path(command[-1]).write_bytes(b"combined")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mix.subprocess, "run", fake_run)

    result = tts_combine.run_tts_combine(output_dir)

    assert result.included_segments == 1
    assert result.skipped_segments == 1
    plan = json.loads(result.tts_combined_plan_path.read_text(encoding="utf-8"))
    assert [segment["status"] for segment in plan["segments"]] == ["missing_tts", "included"]


def test_run_tts_combine_requires_at_least_one_tts_file(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audio.wav").write_bytes(b"source")
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mix,
        "resolve_executable",
        lambda executable: f"/usr/bin/{executable}",
    )
    monkeypatch.setattr(
        tts_combine,
        "probe_audio_duration",
        lambda ffprobe, audio_path: 14.0,
    )

    with pytest.raises(tts_combine.TtsCombineError, match="no synthesized speech WAV files"):
        tts_combine.run_tts_combine(output_dir)

    plan = json.loads((output_dir / "tts_combined_plan.json").read_text(encoding="utf-8"))
    assert plan["included_segments"] == 0
    assert plan["skipped_segments"] == 2
