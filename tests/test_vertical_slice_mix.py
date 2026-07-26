from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import pytest

from automatedub.config import ToolConfig
from automatedub.vertical_slice import mix


def write_silent_wav(path: Path, seconds: float, frame_rate: int = 16000) -> None:
    frame_count = int(round(seconds * frame_rate))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)


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


def test_load_translation_segments_preserves_timing(tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    segments = mix.load_translation_segments(translation_path)

    assert segments == [
        mix.MixTranslationSegment(id=0, start=0.0, end=1.0, target_text="សួស្តី។"),
        mix.MixTranslationSegment(id=12, start=1.25, end=2.0, target_text="លាហើយ។"),
    ]


def test_build_speech_tracks_skips_missing_tts_files(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0012.wav", seconds=0.75)
    segments = [
        mix.MixTranslationSegment(id=0, start=0.0, end=1.0, target_text="សួស្តី។"),
        mix.MixTranslationSegment(id=12, start=1.25, end=2.0, target_text="លាហើយ។"),
    ]

    tracks = mix.build_speech_tracks(segments, tts_dir, ToolConfig())

    assert tracks == [
        mix.MixSpeechTrack(
            id=12,
            start=1.25,
            end=2.0,
            delay_ms=1450,
            atempo=1.0,
            tts_path=tts_dir / "0012.wav",
        )
    ]


def test_build_speech_tracks_applies_custom_sync_offset(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0000.wav", seconds=0.75)
    segments = [
        mix.MixTranslationSegment(id=0, start=1.25, end=2.0, target_text="សួស្តី។"),
    ]

    tracks = mix.build_speech_tracks(
        segments,
        tts_dir,
        ToolConfig(tts_sync_offset_ms=325),
    )

    assert tracks == [
        mix.MixSpeechTrack(
            id=0,
            start=1.25,
            end=2.0,
            delay_ms=1575,
            atempo=1.0,
            tts_path=tts_dir / "0000.wav",
        )
    ]


def test_build_speech_tracks_clamps_atempo_to_safe_bounds(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0000.wav", seconds=1.0)
    write_silent_wav(tts_dir / "0001.wav", seconds=2.2)
    segments = [
        mix.MixTranslationSegment(id=0, start=0.0, end=10.0, target_text="ឆ្ងាញ់ទេ?"),
        mix.MixTranslationSegment(id=1, start=10.0, end=12.0, target_text="សួស្តី។"),
    ]

    tracks = mix.build_speech_tracks(segments, tts_dir, ToolConfig())

    assert tracks[0].atempo == mix.MIN_TTS_ATEMPO
    assert tracks[1].atempo == 1.1


@pytest.mark.parametrize(
    ("generated_duration", "window_duration", "expected_atempo"),
    [
        (1.1, 1.0, 1.1),
        (0.2, 2.0, mix.MIN_TTS_ATEMPO),
        (2.3, 1.0, mix.MAX_TTS_ATEMPO),
        (1.0, 1.0, 1.0),
        (1.0, 0.0, 1.0),
        (0.0, 1.0, 1.0),
    ],
)
def test_compute_atempo(generated_duration, window_duration, expected_atempo):
    assert mix.compute_atempo(generated_duration, window_duration) == expected_atempo


def test_build_mix_command_delays_generated_speech(tmp_path):
    source_audio = tmp_path / "audio.wav"
    output_audio = tmp_path / "mixed_audio.wav"
    tracks = [
        mix.MixSpeechTrack(
            id=0,
            start=0.0,
            end=1.0,
            delay_ms=0,
            atempo=1.0,
            tts_path=tmp_path / "tts" / "0000.wav",
        ),
        mix.MixSpeechTrack(
            id=12,
            start=1.25,
            end=2.0,
            delay_ms=1250,
            atempo=0.85,
            tts_path=tmp_path / "tts" / "0012.wav",
        ),
    ]

    command = mix.build_mix_command("/usr/bin/ffmpeg", source_audio, tracks, output_audio)

    assert command[:7] == [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_audio),
    ]
    assert "-filter_complex" in command
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "[0:a]volume=0.35[base]" in filter_complex
    assert "atempo=1.0000,adelay=0:all=1[seg1]" in filter_complex
    assert "atempo=0.8500,adelay=1250:all=1[seg2]" in filter_complex
    assert "amix=inputs=3:duration=longest:dropout_transition=0:normalize=0[mixed]" in filter_complex
    assert command[-1] == str(output_audio)


def test_run_mix_writes_plan_and_mixed_audio(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "audio.wav").write_bytes(b"source")
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    tts_dir = output_dir / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0000.wav", seconds=1.0)
    write_silent_wav(tts_dir / "0012.wav", seconds=0.3)

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
            return subprocess.CompletedProcess(command, 0, stdout="2.500000\n")
        Path(command[-1]).write_bytes(b"mixed")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(mix.subprocess, "run", fake_run)

    result = mix.run_mix(output_dir, ToolConfig())

    assert result.mixed_audio_path == output_dir / "mixed_audio.wav"
    assert result.mix_plan_path == output_dir / "mix_plan.json"
    assert result.mixed_segments == 2
    assert result.skipped_segments == 0
    assert result.mixed_audio_path.read_bytes() == b"mixed"
    plan = json.loads(result.mix_plan_path.read_text(encoding="utf-8"))
    assert plan["source_duration_seconds"] == 2.5
    assert plan["tts_sync_offset_ms"] == 200
    assert plan["mixed_segments"] == 2
    assert [segment["status"] for segment in plan["segments"]] == ["included", "included"]
    assert [segment["delay_ms"] for segment in plan["segments"]] == [200, 1450]
    assert [segment["atempo"] for segment in plan["segments"]] == [1.0, mix.MIN_TTS_ATEMPO]


def test_run_mix_requires_at_least_one_tts_file(monkeypatch, tmp_path):
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
        mix,
        "probe_audio_duration",
        lambda ffprobe, audio_path: 2.5,
    )

    with pytest.raises(mix.VS4Error, match="no synthesized speech WAV files"):
        mix.run_mix(output_dir, ToolConfig())

    plan = json.loads((output_dir / "mix_plan.json").read_text(encoding="utf-8"))
    assert plan["mixed_segments"] == 0
    assert plan["skipped_segments"] == 2
