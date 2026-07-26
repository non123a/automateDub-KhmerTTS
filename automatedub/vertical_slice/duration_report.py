"""TTS duration diagnostics comparing segment timing windows to generated speech length."""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path

from automatedub.vertical_slice.paths import (
    duration_report_output_path,
    translation_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.tts import tts_segment_output_path

DURATION_REPORT_VERSION = 1
LARGEST_MISMATCH_COUNT = 20


class DurationReportError(RuntimeError):
    """Raised when the TTS duration report cannot be generated."""


@dataclass(frozen=True)
class SegmentWindow:
    id: int
    start: float
    end: float


@dataclass(frozen=True)
class SegmentDuration:
    id: int
    expected_duration: float
    generated_duration: float
    difference_ms: float
    ratio: float


@dataclass(frozen=True)
class DurationReportResult:
    report_path: Path
    generated_wav_count: int
    average_ratio: float
    minimum_ratio: float
    maximum_ratio: float


def run_duration_report(output_dir: Path) -> DurationReportResult:
    output_root = output_dir.expanduser()
    translation_path = translation_output_path(output_root)
    tts_dir = tts_output_dir_path(output_root)
    report_path = duration_report_output_path(output_root)

    windows = load_segment_windows(translation_path)
    durations = measure_segment_durations(windows, tts_dir)
    if not durations:
        raise DurationReportError(f"no synthesized speech WAV files were found in {tts_dir}")

    ratios = [duration.ratio for duration in durations]
    write_duration_report(
        report_path=report_path,
        translation_path=translation_path,
        tts_dir=tts_dir,
        durations=durations,
    )
    return DurationReportResult(
        report_path=report_path,
        generated_wav_count=len(durations),
        average_ratio=round(sum(ratios) / len(ratios), 4),
        minimum_ratio=min(ratios),
        maximum_ratio=max(ratios),
    )


def load_segment_windows(translation_path: Path) -> list[SegmentWindow]:
    if not translation_path.exists():
        raise DurationReportError(f"translation file does not exist: {translation_path}")
    try:
        payload = json.loads(translation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DurationReportError(
            f"translation file is not valid JSON: {translation_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise DurationReportError("translation JSON root must be an object")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise DurationReportError("translation JSON must contain a segments list")

    windows: list[SegmentWindow] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise DurationReportError("each translation segment must be an object")
        segment_id = raw_segment.get("id")
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        if not isinstance(segment_id, int):
            raise DurationReportError("each translation segment must contain integer id")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            raise DurationReportError(
                "each translation segment must contain numeric start and end"
            )
        windows.append(SegmentWindow(id=segment_id, start=float(start), end=float(end)))
    return windows


def measure_segment_durations(
    windows: list[SegmentWindow],
    tts_dir: Path,
) -> list[SegmentDuration]:
    durations: list[SegmentDuration] = []
    for window in windows:
        wav_path = tts_segment_output_path(tts_dir, window.id)
        if not wav_path.exists():
            continue
        expected_duration = round(window.end - window.start, 4)
        generated_duration = probe_wav_duration_seconds(wav_path)
        durations.append(
            SegmentDuration(
                id=window.id,
                expected_duration=expected_duration,
                generated_duration=generated_duration,
                difference_ms=round((generated_duration - expected_duration) * 1000, 1),
                ratio=compute_ratio(generated_duration, expected_duration),
            )
        )
    return durations


def compute_ratio(generated_duration: float, expected_duration: float) -> float:
    if expected_duration <= 0:
        return 0.0
    return round(generated_duration / expected_duration, 4)


def probe_wav_duration_seconds(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
    except (wave.Error, EOFError) as exc:
        raise DurationReportError(f"unable to read WAV duration: {wav_path}") from exc
    if frame_rate <= 0:
        raise DurationReportError(f"WAV file has an invalid frame rate: {wav_path}")
    return round(frame_count / frame_rate, 4)


def write_duration_report(
    report_path: Path,
    translation_path: Path,
    tts_dir: Path,
    durations: list[SegmentDuration],
) -> None:
    ratios = [duration.ratio for duration in durations]
    ranked_by_mismatch = sorted(durations, key=lambda d: abs(d.difference_ms), reverse=True)
    payload = {
        "version": DURATION_REPORT_VERSION,
        "translation": str(translation_path),
        "tts_dir": str(tts_dir),
        "generated_wav_count": len(durations),
        "average_ratio": round(sum(ratios) / len(ratios), 4),
        "minimum_ratio": min(ratios),
        "maximum_ratio": max(ratios),
        "largest_mismatches": [
            duration_to_dict(duration) for duration in ranked_by_mismatch[:LARGEST_MISMATCH_COUNT]
        ],
        "segments": [duration_to_dict(duration) for duration in durations],
    }
    write_json(report_path, payload)


def duration_to_dict(duration: SegmentDuration) -> dict[str, object]:
    return {
        "id": duration.id,
        "expected_duration": duration.expected_duration,
        "generated_duration": duration.generated_duration,
        "difference_ms": duration.difference_ms,
        "ratio": duration.ratio,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
