"""VS4 dialogue replacement and mix using FFmpeg."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from automatedub.config import ToolConfig, load_tool_config, resolve_executable
from automatedub.vertical_slice.paths import (
    audio_output_path,
    mix_plan_output_path,
    mixed_audio_output_path,
    translation_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.tts import tts_segment_output_path

MIX_VERSION = 1
SOURCE_AUDIO_DUCK_VOLUME = 0.35
MIX_SAMPLE_RATE = 16000


class VS4Error(RuntimeError):
    """Raised when the VS4 dialogue mix step cannot complete."""


@dataclass(frozen=True)
class MixTranslationSegment:
    id: int
    start: float
    end: float
    target_text: str


@dataclass(frozen=True)
class MixSpeechTrack:
    id: int
    start: float
    end: float
    delay_ms: int
    tts_path: Path


@dataclass(frozen=True)
class MixResult:
    mixed_audio_path: Path
    mix_plan_path: Path
    mixed_segments: int
    skipped_segments: int


def run_mix(
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> MixResult:
    config = tool_config or load_tool_config()
    output_root = output_dir.expanduser()
    source_audio_path = audio_output_path(output_root)
    translation_path = translation_output_path(output_root)
    tts_dir = tts_output_dir_path(output_root)
    mixed_audio_path = mixed_audio_output_path(output_root)
    mix_plan_path = mix_plan_output_path(output_root)

    validate_source_audio(source_audio_path)
    ffmpeg = validate_ffmpeg(config)
    ffprobe = validate_ffprobe(config)
    source_duration = probe_audio_duration(ffprobe, source_audio_path)

    segments = load_translation_segments(translation_path)
    speech_tracks = build_speech_tracks(segments, tts_dir, config)
    write_mix_plan(
        mix_plan_path=mix_plan_path,
        source_audio_path=source_audio_path,
        translation_path=translation_path,
        tts_dir=tts_dir,
        mixed_audio_path=mixed_audio_path,
        source_duration=source_duration,
        tts_sync_offset_ms=config.tts_sync_offset_ms,
        segments=segments,
        speech_tracks=speech_tracks,
    )

    if not speech_tracks:
        raise VS4Error(f"no synthesized speech WAV files were found in {tts_dir}")

    mixed_audio_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_mix_command(
        ffmpeg=ffmpeg,
        source_audio_path=source_audio_path,
        speech_tracks=speech_tracks,
        mixed_audio_path=mixed_audio_path,
    )
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
        raise VS4Error(f"dialogue mix failed: {message}") from exc

    if not mixed_audio_path.exists():
        raise VS4Error(f"dialogue mix did not create expected file: {mixed_audio_path}")

    return MixResult(
        mixed_audio_path=mixed_audio_path,
        mix_plan_path=mix_plan_path,
        mixed_segments=len(speech_tracks),
        skipped_segments=len(segments) - len(speech_tracks),
    )


def validate_source_audio(source_audio_path: Path) -> None:
    if not source_audio_path.exists():
        raise VS4Error(f"source audio does not exist: {source_audio_path}")
    if not source_audio_path.is_file():
        raise VS4Error(f"source audio path is not a file: {source_audio_path}")
    if source_audio_path.suffix.lower() != ".wav":
        raise VS4Error(f"source audio must be a WAV: {source_audio_path}")


def validate_ffmpeg(tool_config: ToolConfig) -> str:
    ffmpeg = resolve_executable(tool_config.ffmpeg_path)
    if ffmpeg is None:
        raise VS4Error("ffmpeg is not available on PATH")
    return ffmpeg


def validate_ffprobe(tool_config: ToolConfig) -> str:
    ffprobe = resolve_executable(tool_config.ffprobe_path)
    if ffprobe is None:
        raise VS4Error("ffprobe is not available on PATH")
    return ffprobe


def probe_audio_duration(ffprobe: str, audio_path: Path) -> float:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or f"ffprobe exited with {exc.returncode}"
        )
        raise VS4Error(f"source audio duration probe failed: {message}") from exc

    try:
        return round(float(result.stdout.strip()), 3)
    except ValueError as exc:
        message = f"source audio duration probe returned invalid output: {result.stdout}"
        raise VS4Error(message) from exc


def load_translation_segments(translation_path: Path) -> list[MixTranslationSegment]:
    if not translation_path.exists():
        raise VS4Error(f"translation file does not exist: {translation_path}")
    try:
        payload = json.loads(translation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VS4Error(f"translation file is not valid JSON: {translation_path}") from exc

    if not isinstance(payload, dict):
        raise VS4Error("translation JSON root must be an object")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise VS4Error("translation JSON must contain a segments list")

    segments: list[MixTranslationSegment] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise VS4Error("each translation segment must be an object")
        segment_id = raw_segment.get("id")
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        target_text = raw_segment.get("target_text")
        if not isinstance(segment_id, int):
            raise VS4Error("each translation segment must contain integer id")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            raise VS4Error("each translation segment must contain numeric start and end")
        if not isinstance(target_text, str) or not target_text.strip():
            raise VS4Error(f"translation segment {segment_id} is missing target_text")
        segments.append(
            MixTranslationSegment(
                id=segment_id,
                start=float(start),
                end=float(end),
                target_text=target_text.strip(),
            )
        )
    return segments


def build_speech_tracks(
    segments: list[MixTranslationSegment],
    tts_dir: Path,
    tool_config: ToolConfig,
) -> list[MixSpeechTrack]:
    tracks: list[MixSpeechTrack] = []
    for segment in segments:
        tts_path = tts_segment_output_path(tts_dir, segment.id)
        if not tts_path.exists():
            continue
        tracks.append(
            MixSpeechTrack(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                delay_ms=max(
                    0,
                    int(round(segment.start * 1000)) + tool_config.tts_sync_offset_ms,
                ),
                tts_path=tts_path,
            )
        )
    return tracks


def build_mix_command(
    ffmpeg: str,
    source_audio_path: Path,
    speech_tracks: list[MixSpeechTrack],
    mixed_audio_path: Path,
) -> list[str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_audio_path),
    ]
    for track in speech_tracks:
        command.extend(["-i", str(track.tts_path)])
    command.extend(
        [
            "-filter_complex",
            build_mix_filter_complex(speech_tracks),
            "-map",
            "[mixed]",
            "-ac",
            "1",
            "-ar",
            str(MIX_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(mixed_audio_path),
        ]
    )
    return command


def build_mix_filter_complex(speech_tracks: list[MixSpeechTrack]) -> str:
    filters = [f"[0:a]volume={SOURCE_AUDIO_DUCK_VOLUME:.2f}[base]"]
    mix_inputs = ["[base]"]
    for input_index, track in enumerate(speech_tracks, start=1):
        label = f"[seg{input_index}]"
        filters.append(
            f"[{input_index}:a]aresample={MIX_SAMPLE_RATE},"
            f"adelay={track.delay_ms}:all=1{label}"
        )
        mix_inputs.append(label)
    filters.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:"
        "duration=longest:dropout_transition=0:normalize=0[mixed]"
    )
    return ";".join(filters)


def write_mix_plan(
    mix_plan_path: Path,
    source_audio_path: Path,
    translation_path: Path,
    tts_dir: Path,
    mixed_audio_path: Path,
    source_duration: float,
    tts_sync_offset_ms: int,
    segments: list[MixTranslationSegment],
    speech_tracks: list[MixSpeechTrack],
) -> None:
    included_ids = {track.id for track in speech_tracks}
    payload = {
        "version": MIX_VERSION,
        "source_audio": source_audio_path.name,
        "translation": translation_path.name,
        "tts_dir": tts_dir.name,
        "mixed_audio": mixed_audio_path.name,
        "source_duration_seconds": source_duration,
        "source_volume": SOURCE_AUDIO_DUCK_VOLUME,
        "sample_rate": MIX_SAMPLE_RATE,
        "tts_sync_offset_ms": tts_sync_offset_ms,
        "mixed_segments": len(speech_tracks),
        "skipped_segments": len(segments) - len(speech_tracks),
        "segments": [
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "delay_ms": max(
                    0,
                    int(round(segment.start * 1000)) + tts_sync_offset_ms,
                ),
                "tts_path": str(Path(tts_dir.name) / f"{segment.id:04d}.wav"),
                "status": "included" if segment.id in included_ids else "missing_tts",
            }
            for segment in segments
        ],
    }
    write_json(mix_plan_path, payload)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
