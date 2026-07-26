from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from automatedub.vertical_slice import duration_report


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
                "end": 2.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "你好",
                "target_text": "សួស្តី។",
                "notes": None,
            },
            {
                "id": 1,
                "start": 2.0,
                "end": 12.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "好吃吗",
                "target_text": "ឆ្ងាញ់ទេ?",
                "notes": None,
            },
            {
                "id": 2,
                "start": 12.0,
                "end": 14.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": "拜拜",
                "target_text": "លាហើយ។",
                "notes": None,
            },
        ],
    }


def write_silent_wav(path: Path, seconds: float, frame_rate: int = 16000) -> None:
    frame_count = int(round(seconds * frame_rate))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)


def test_probe_wav_duration_seconds_reads_frame_count(tmp_path):
    wav_path = tmp_path / "0000.wav"
    write_silent_wav(wav_path, seconds=1.5)

    assert duration_report.probe_wav_duration_seconds(wav_path) == 1.5


def test_probe_wav_duration_seconds_rejects_invalid_wav(tmp_path):
    wav_path = tmp_path / "broken.wav"
    wav_path.write_bytes(b"not a wav file")

    with pytest.raises(duration_report.DurationReportError, match="unable to read WAV duration"):
        duration_report.probe_wav_duration_seconds(wav_path)


def test_load_segment_windows_preserves_timing(tmp_path):
    translation_path = tmp_path / "translation.json"
    translation_path.write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    windows = duration_report.load_segment_windows(translation_path)

    assert windows == [
        duration_report.SegmentWindow(id=0, start=0.0, end=2.0),
        duration_report.SegmentWindow(id=1, start=2.0, end=12.0),
        duration_report.SegmentWindow(id=2, start=12.0, end=14.0),
    ]


def test_measure_segment_durations_skips_missing_wav_files(tmp_path):
    tts_dir = tmp_path / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0000.wav", seconds=1.9)
    write_silent_wav(tts_dir / "0001.wav", seconds=1.1)
    windows = [
        duration_report.SegmentWindow(id=0, start=0.0, end=2.0),
        duration_report.SegmentWindow(id=1, start=2.0, end=12.0),
        duration_report.SegmentWindow(id=2, start=12.0, end=14.0),
    ]

    durations = duration_report.measure_segment_durations(windows, tts_dir)

    assert [d.id for d in durations] == [0, 1]
    assert durations[0].expected_duration == 2.0
    assert durations[0].generated_duration == 1.9
    assert durations[0].difference_ms == -100.0
    assert durations[0].ratio == 0.95
    assert durations[1].expected_duration == 10.0
    assert durations[1].generated_duration == 1.1
    assert durations[1].ratio == 0.11


def test_run_duration_report_writes_report_and_ranks_worst_mismatches(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    tts_dir = output_dir / "tts"
    tts_dir.mkdir()
    write_silent_wav(tts_dir / "0000.wav", seconds=1.9)
    write_silent_wav(tts_dir / "0001.wav", seconds=1.1)
    write_silent_wav(tts_dir / "0002.wav", seconds=2.0)

    result = duration_report.run_duration_report(output_dir)

    assert result.report_path == output_dir / "duration_report.json"
    assert result.generated_wav_count == 3
    assert result.minimum_ratio == 0.11
    assert result.maximum_ratio == 1.0

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["generated_wav_count"] == 3
    assert payload["segments"][1]["id"] == 1
    assert payload["largest_mismatches"][0]["id"] == 1


def test_run_duration_report_requires_at_least_one_generated_wav(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "translation.json").write_text(
        json.dumps(minimal_translation_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(duration_report.DurationReportError, match="no synthesized speech"):
        duration_report.run_duration_report(output_dir)
