"""Export the final dubbed MP4, reusing the existing mix backend."""

from __future__ import annotations

import enum
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice.duration_report import (
    DurationReportError,
    probe_wav_duration_seconds,
)
from automatedub.vertical_slice.mix import (
    MixSpeechTrack,
    VS4Error,
    build_duck_windows,
    build_mix_command,
    compute_atempo,
    validate_ffmpeg,
    validate_ffprobe,
)
from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project, Segment


class ExportError(RuntimeError):
    """Raised when export cannot complete."""


class ExportStage(enum.StrEnum):
    PREPARING = "Preparing"
    MIXING_AUDIO = "Mixing audio"
    RENDERING_VIDEO = "Rendering video"
    FINALIZING = "Finalizing"
    COMPLETED = "Completed"


@dataclass(frozen=True)
class ExportOptions:
    output_path: Path


@dataclass(frozen=True)
class ExportResult:
    output_path: Path


def build_export_speech_tracks(
    segments: list[Segment],
    editables: dict[int, EditableSegment],
    tts_dir: Path,
    tool_config: ToolConfig,
) -> list[MixSpeechTrack]:
    tracks: list[MixSpeechTrack] = []
    for segment in segments:
        tts_path = tts_segment_output_path(tts_dir, segment.id)
        if not tts_path.exists():
            continue
        try:
            generated_duration = probe_wav_duration_seconds(tts_path)
        except DurationReportError as exc:
            raise ExportError(f"segment {segment.id}: {exc}") from exc

        es = editables.get(segment.id)
        # offset_ms is tracked on both Segment (timeline drag/undo flow) and
        # EditableSegment (regeneration/property-edit flow) — sum both since
        # each writer only ever touches its own field.
        offset_extra = segment.offset_ms + (es.offset_ms if es is not None else 0)
        speed = es.speed if es is not None else 1.0
        volume = es.volume if es is not None else 1.0
        fade_in_ms = es.fade_in_ms if es is not None else 0
        fade_out_ms = es.fade_out_ms if es is not None else 0

        delay_ms = max(
            0,
            int(round(segment.start * 1000)) + tool_config.tts_sync_offset_ms + offset_extra,
        )
        base_atempo = compute_atempo(generated_duration, segment.end - segment.start)
        atempo = round(min(2.0, max(0.5, base_atempo * speed)), 4)

        tracks.append(
            MixSpeechTrack(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                delay_ms=delay_ms,
                atempo=atempo,
                generated_duration=generated_duration,
                tts_path=tts_path,
                volume=volume,
                fade_in_ms=fade_in_ms,
                fade_out_ms=fade_out_ms,
            )
        )
    return tracks


def build_mux_command(
    ffmpeg: str,
    video_path: Path,
    mixed_audio_path: Path,
    output_path: Path,
) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(mixed_audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        str(output_path),
    ]


def export_project(
    project: Project,
    editables: dict[int, EditableSegment],
    tool_config: ToolConfig,
    options: ExportOptions,
    on_stage: Callable[[ExportStage], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> ExportResult:
    def _stage(s: ExportStage) -> None:
        if on_stage:
            on_stage(s)

    def _cancelled() -> bool:
        return is_cancelled is not None and is_cancelled()

    _stage(ExportStage.PREPARING)

    if project.video_path is None or not project.video_path.exists():
        raise ExportError(f"source video not found: {project.video_path}")
    if not project.audio_path.exists():
        raise ExportError(f"source audio not found: {project.audio_path}")

    try:
        ffmpeg = validate_ffmpeg(tool_config)
        validate_ffprobe(tool_config)
    except VS4Error as exc:
        raise ExportError(str(exc)) from exc

    if _cancelled():
        raise ExportError("export cancelled")

    output_path = options.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _stage(ExportStage.MIXING_AUDIO)

    speech_tracks = build_export_speech_tracks(
        project.segments, editables, project.tts_directory, tool_config
    )
    if not speech_tracks:
        raise ExportError("no synthesized speech WAV files were found — nothing to export")

    if _cancelled():
        raise ExportError("export cancelled")

    duck_windows = build_duck_windows(speech_tracks)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=output_path.parent)
    mixed_audio_path = Path(tmp_name)
    try:
        import os
        os.close(tmp_fd)

        mix_command = build_mix_command(
            ffmpeg=ffmpeg,
            source_audio_path=project.audio_path,
            speech_tracks=speech_tracks,
            duck_windows=duck_windows,
            duck_volume=tool_config.duck_volume,
            mixed_audio_path=mixed_audio_path,
        )
        try:
            subprocess.run(mix_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
            raise ExportError(f"audio mix failed: {msg}") from exc

        if not mixed_audio_path.exists():
            raise ExportError("audio mix did not produce expected file")

        if _cancelled():
            raise ExportError("export cancelled")

        _stage(ExportStage.RENDERING_VIDEO)

        mux_command = build_mux_command(
            ffmpeg=ffmpeg,
            video_path=project.video_path,
            mixed_audio_path=mixed_audio_path,
            output_path=output_path,
        )
        try:
            subprocess.run(mux_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
            raise ExportError(f"video render failed: {msg}") from exc

        if not output_path.exists():
            raise ExportError(f"export did not produce expected file: {output_path}")

    finally:
        mixed_audio_path.unlink(missing_ok=True)

    _stage(ExportStage.FINALIZING)

    if _cancelled():
        output_path.unlink(missing_ok=True)
        raise ExportError("export cancelled")

    _stage(ExportStage.COMPLETED)
    return ExportResult(output_path=output_path)
