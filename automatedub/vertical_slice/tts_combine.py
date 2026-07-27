"""Optional Khmer-only TTS timeline artifact (tts_combined.wav)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from automatedub.config import ToolConfig, load_tool_config
from automatedub.vertical_slice.mix import (
    MIX_SAMPLE_RATE,
    MixTranslationSegment,
    load_translation_segments,
    probe_audio_duration,
    validate_ffmpeg,
    validate_ffprobe,
    validate_source_audio,
)
from automatedub.vertical_slice.paths import (
    audio_output_path,
    translation_output_path,
    tts_combined_output_path,
    tts_combined_plan_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.tts import tts_segment_output_path

TTS_COMBINE_VERSION = 1


class TtsCombineError(RuntimeError):
    """Raised when the Khmer-only TTS timeline artifact cannot be built."""


@dataclass(frozen=True)
class CombineSpeechTrack:
    id: int
    start: float
    delay_ms: int
    tts_path: Path


@dataclass(frozen=True)
class TtsCombineResult:
    tts_combined_path: Path
    tts_combined_plan_path: Path
    included_segments: int
    skipped_segments: int


def run_tts_combine(
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> TtsCombineResult:
    config = tool_config or load_tool_config()
    output_root = output_dir.expanduser()
    source_audio_path = audio_output_path(output_root)
    translation_path = translation_output_path(output_root)
    tts_dir = tts_output_dir_path(output_root)
    tts_combined_path = tts_combined_output_path(output_root)
    tts_combined_plan_path = tts_combined_plan_output_path(output_root)

    validate_source_audio(source_audio_path)
    ffmpeg = validate_ffmpeg(config)
    ffprobe = validate_ffprobe(config)
    source_duration = probe_audio_duration(ffprobe, source_audio_path)

    segments = load_translation_segments(translation_path)
    speech_tracks = build_combine_speech_tracks(segments, tts_dir)
    command = build_combine_command(
        ffmpeg=ffmpeg,
        source_duration=source_duration,
        speech_tracks=speech_tracks,
        tts_combined_path=tts_combined_path,
    )

    write_tts_combine_plan(
        tts_combined_plan_path=tts_combined_plan_path,
        source_audio_path=source_audio_path,
        translation_path=translation_path,
        tts_dir=tts_dir,
        tts_combined_path=tts_combined_path,
        source_duration=source_duration,
        segments=segments,
        speech_tracks=speech_tracks,
        command=command,
    )

    if not speech_tracks:
        raise TtsCombineError(f"no synthesized speech WAV files were found in {tts_dir}")

    tts_combined_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
        raise TtsCombineError(f"tts combine failed: {message}") from exc

    if not tts_combined_path.exists():
        raise TtsCombineError(f"tts combine did not create expected file: {tts_combined_path}")

    return TtsCombineResult(
        tts_combined_path=tts_combined_path,
        tts_combined_plan_path=tts_combined_plan_path,
        included_segments=len(speech_tracks),
        skipped_segments=len(segments) - len(speech_tracks),
    )


def build_combine_speech_tracks(
    segments: list[MixTranslationSegment],
    tts_dir: Path,
) -> list[CombineSpeechTrack]:
    tracks: list[CombineSpeechTrack] = []
    for segment in segments:
        tts_path = tts_segment_output_path(tts_dir, segment.id)
        if not tts_path.exists():
            continue
        tracks.append(
            CombineSpeechTrack(
                id=segment.id,
                start=segment.start,
                delay_ms=max(0, int(round(segment.start * 1000))),
                tts_path=tts_path,
            )
        )
    return tracks


def build_combine_command(
    ffmpeg: str,
    source_duration: float,
    speech_tracks: list[CombineSpeechTrack],
    tts_combined_path: Path,
) -> list[str]:
    duration_arg = f"{source_duration:.3f}"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-t",
        duration_arg,
        "-i",
        f"anullsrc=channel_layout=mono:sample_rate={MIX_SAMPLE_RATE}",
    ]
    for track in speech_tracks:
        command.extend(["-i", str(track.tts_path)])
    command.extend(
        [
            "-filter_complex",
            build_combine_filter_complex(speech_tracks),
            "-map",
            "[combined]",
            "-t",
            duration_arg,
            "-ac",
            "1",
            "-ar",
            str(MIX_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(tts_combined_path),
        ]
    )
    return command


def build_combine_filter_complex(speech_tracks: list[CombineSpeechTrack]) -> str:
    filters = []
    mix_inputs = ["[0:a]"]
    for input_index, track in enumerate(speech_tracks, start=1):
        label = f"[seg{input_index}]"
        filters.append(
            f"[{input_index}:a]aresample={MIX_SAMPLE_RATE},"
            f"adelay={track.delay_ms}:all=1{label}"
        )
        mix_inputs.append(label)
    filters.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:"
        "duration=first:dropout_transition=0:normalize=0[combined]"
    )
    return ";".join(filters)


def write_tts_combine_plan(
    tts_combined_plan_path: Path,
    source_audio_path: Path,
    translation_path: Path,
    tts_dir: Path,
    tts_combined_path: Path,
    source_duration: float,
    segments: list[MixTranslationSegment],
    speech_tracks: list[CombineSpeechTrack],
    command: list[str],
) -> None:
    tracks_by_id = {track.id: track for track in speech_tracks}
    included_ids = set(tracks_by_id)
    payload = {
        "version": TTS_COMBINE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_audio": source_audio_path.name,
        "translation": translation_path.name,
        "tts_dir": tts_dir.name,
        "tts_combined": tts_combined_path.name,
        "duration_seconds": source_duration,
        "sample_rate": MIX_SAMPLE_RATE,
        "included_segments": len(speech_tracks),
        "skipped_segments": len(segments) - len(speech_tracks),
        "ffmpeg_command": command,
        "segments": [
            {
                "id": segment.id,
                "start": segment.start,
                "delay_ms": max(0, int(round(segment.start * 1000))),
                "tts_path": str(Path(tts_dir.name) / f"{segment.id:04d}.wav"),
                "status": "included" if segment.id in included_ids else "missing_tts",
            }
            for segment in segments
        ],
    }
    write_json(tts_combined_plan_path, payload)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
