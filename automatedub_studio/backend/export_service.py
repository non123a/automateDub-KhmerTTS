"""Export the final dubbed MP4, reusing the existing mix backend."""

from __future__ import annotations

import enum
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from automatedub import process
from automatedub.config import ToolConfig
from automatedub.vertical_slice.duration_report import (
    DurationReportError,
    probe_wav_duration_seconds,
)
from automatedub.vertical_slice.mix import (
    MIX_SAMPLE_RATE,
    MixSpeechTrack,
    VS4Error,
    build_duck_windows,
    build_mix_command,
    build_mix_filter_complex,
    compute_atempo,
    validate_ffmpeg,
    validate_ffprobe,
)
from automatedub.vertical_slice.tts import tts_segment_output_path
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project, Segment
from automatedub_studio.timeline.timeline_clip import (
    ORIGINAL_AUDIO_TRACK_ID,
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
    Timeline,
)

EXPORT_REENCODE_REQUIRED_CODECS = {"av1"}
EXPORT_H264_ENCODER = "libx264"
EXPORT_H265_ENCODER = "libx265"
H264_ENCODER_PREFERENCE = ("h264_videotoolbox", "libx264")
H265_ENCODER_PREFERENCE = ("hevc_videotoolbox", "libx265")
STREAM_COPY_SAFE_CODECS = {"h264", "hevc", "h265", "mpeg4"}
STREAM_COPY_SAFE_CONTAINERS = {"mp4", "mov"}


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
    video_codec: str = "h264"
    video_quality: str = "High"
    video_preset: str = "compatible_h264"
    include_original_movie_audio: bool = False


@dataclass(frozen=True)
class ExportResult:
    output_path: Path


@dataclass(frozen=True)
class FFmpegProgress:
    """Machine-readable encoding telemetry emitted by FFmpeg's progress pipe."""

    percent: int
    frame: int | None = None
    fps: float | None = None
    encoded_time_seconds: float | None = None
    elapsed_seconds: float | None = None
    remaining_seconds: float | None = None
    output_size_bytes: int | None = None
    speed: float | None = None
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExportStreamSummary:
    video_streams: int
    audio_streams: int
    raw_streams: list[dict[str, object]]
    container_names: tuple[str, ...] = ()

    @property
    def first_video_codec(self) -> str | None:
        for stream in self.raw_streams:
            if stream.get("codec_type") == "video":
                codec = stream.get("codec_name")
                return str(codec).lower() if codec else None
        return None

    @property
    def container_name(self) -> str | None:
        return self.container_names[0] if self.container_names else None


@dataclass(frozen=True)
class ExportEncoderCapabilities:
    """The encoders this FFmpeg build can use for playable MP4 exports."""

    h264_encoder: str | None
    h265_encoder: str | None


@dataclass(frozen=True)
class ExportSystemCapabilities:
    """FFmpeg features that determine whether an export can be produced."""

    ffmpeg_version: str
    available_encoders: frozenset[str]
    available_muxers: frozenset[str]
    h264_encoder: str | None
    h265_encoder: str | None

    @property
    def supports_mp4_muxing(self) -> bool:
        return "mp4" in self.available_muxers


def probe_export_system_capabilities(ffmpeg: str) -> ExportSystemCapabilities:
    """Collect FFmpeg version, video encoders, and MP4 muxer support."""
    version = _run_ffmpeg_capability_command(ffmpeg, "-version")
    encoders_output = _run_ffmpeg_capability_command(ffmpeg, "-hide_banner", "-encoders")
    muxers_output = _run_ffmpeg_capability_command(ffmpeg, "-hide_banner", "-muxers")
    encoders = _parse_ffmpeg_encoders(encoders_output or "")
    muxers = _parse_ffmpeg_muxers(muxers_output or "")
    return ExportSystemCapabilities(
        ffmpeg_version=_parse_ffmpeg_version(version or ""),
        available_encoders=frozenset(encoders),
        available_muxers=frozenset(muxers),
        h264_encoder=_preferred_encoder(encoders, H264_ENCODER_PREFERENCE),
        h265_encoder=_preferred_encoder(encoders, H265_ENCODER_PREFERENCE),
    )


def _run_ffmpeg_capability_command(ffmpeg: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            [ffmpeg, *args],
            check=True,
            capture_output=True,
            text=True,
            **process.gui_subprocess_kwargs(),
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    stdout = getattr(result, "stdout", "")
    return stdout if isinstance(stdout, str) else None


def _parse_ffmpeg_version(output: str) -> str:
    return output.splitlines()[0].strip() if output else "FFmpeg version unavailable"


def _parse_ffmpeg_encoders(output: str) -> set[str]:
    return {
        parts[1]
        for line in output.splitlines()
        if len(parts := line.split()) >= 2 and parts[0].startswith(("V", "."))
    }


def _parse_ffmpeg_muxers(output: str) -> set[str]:
    return {
        parts[1]
        for line in output.splitlines()
        if len(parts := line.split()) >= 2 and "E" in parts[0]
    }


def probe_export_encoder_capabilities(ffmpeg: str) -> ExportEncoderCapabilities:
    """Inspect FFmpeg rather than assuming optional H.265 support exists."""
    output = _run_ffmpeg_capability_command(ffmpeg, "-hide_banner", "-encoders")
    if output is None:
        # Preserve deterministic unit tests whose subprocess boundary is mocked.
        return ExportEncoderCapabilities(EXPORT_H264_ENCODER, EXPORT_H265_ENCODER)
    if not output:
        return ExportEncoderCapabilities(None, None)
    encoders = _parse_ffmpeg_encoders(output)
    return ExportEncoderCapabilities(
        _preferred_encoder(encoders, H264_ENCODER_PREFERENCE),
        _preferred_encoder(encoders, H265_ENCODER_PREFERENCE),
    )


def _preferred_encoder(available: set[str], preferred: tuple[str, ...]) -> str | None:
    return next((encoder for encoder in preferred if encoder in available), None)


def stream_copy_safety(
    source_summary: ExportStreamSummary,
    source_video: Path | None,
    *,
    source_container: str | None = None,
) -> tuple[bool, str]:
    """Return whether stream-copying the source video into an MP4 is safe."""
    if source_video is None:
        return False, "A source video is required for stream copy."
    source_codec = source_summary.first_video_codec
    if source_codec is None:
        return False, "The source video codec could not be determined."
    if source_codec not in STREAM_COPY_SAFE_CODECS:
        return (
            False,
            f"{source_codec.upper()} stream copy is not approved for a compatible MP4 export.",
        )
    container = source_container or source_video.suffix.lower().lstrip(".")
    if container not in STREAM_COPY_SAFE_CONTAINERS:
        label = container.upper() if container else "unknown"
        return (
            False,
            f"{label} source containers are not approved for stream-copy MP4 export.",
        )
    return True, f"{source_codec.upper()} in {container.upper()} can be stream-copied safely."


def probe_stream_copy_capability(ffmpeg: str, source_video: Path) -> tuple[bool, str]:
    """Verify that this FFmpeg can mux the source video stream into an MP4."""
    if not source_video.is_file():
        return False, "A readable source video is required for stream copy."
    with tempfile.TemporaryDirectory(prefix="automatedub-stream-copy-") as directory:
        probe_output = Path(directory) / "stream-copy-check.mp4"
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-t",
            "1",
            "-i",
            str(source_video),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            str(probe_output),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                **process.gui_subprocess_kwargs(),
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            stderr = getattr(exc, "stderr", "")
            detail = stderr.strip() if isinstance(stderr, str) else ""
            return False, detail or "FFmpeg could not stream-copy this video into MP4."
        if not probe_output.is_file() or probe_output.stat().st_size == 0:
            return False, "FFmpeg did not create a stream-copy MP4."
        return True, "FFmpeg verified -c:v copy for this source and MP4 output."


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


def build_export_timeline_speech_tracks(
    timeline: Timeline,
    tool_config: ToolConfig,
) -> list[MixSpeechTrack]:
    """Build export inputs from the editable timeline, never transcript references.

    Multiple TimelineClip objects can intentionally point at the same WAV.  Each
    is a separate, independently positioned export input; reference-only and
    muted clips are deliberately excluded.
    """
    tracks: list[MixSpeechTrack] = []
    for timeline_track in timeline.tracks:
        if (
            not timeline_track.is_audio
            or timeline_track.reference_only
            or timeline_track.muted
            or timeline_track.id == ORIGINAL_AUDIO_TRACK_ID
            or timeline_track.id == ORIGINAL_MOVIE_AUDIO_TRACK_ID
        ):
            continue
        for clip in timeline_track.clips:
            if clip.muted or clip.source_path is None or not clip.source_path.is_file():
                continue
            try:
                generated_duration = probe_wav_duration_seconds(clip.source_path)
            except DurationReportError as exc:
                raise ExportError(f"timeline clip {clip.id}: {exc}") from exc
            base_atempo = compute_atempo(generated_duration, clip.duration)
            atempo = round(min(2.0, max(0.5, base_atempo * clip.speaking_rate)), 4)
            tracks.append(
                MixSpeechTrack(
                    id=len(tracks),
                    start=clip.start_time,
                    end=clip.end_time,
                    delay_ms=max(
                        0,
                        int(round(clip.start_time * 1000))
                        + tool_config.tts_sync_offset_ms,
                    ),
                    atempo=atempo,
                    generated_duration=generated_duration,
                    tts_path=clip.source_path,
                    volume=clip.volume,
                    fade_in_ms=round(clip.fade_in * 1000),
                    fade_out_ms=round(clip.fade_out * 1000),
                )
            )
    return tracks


def build_mux_command(
    ffmpeg: str,
    video_path: Path,
    mixed_audio_path: Path,
    output_path: Path,
    *,
    video_encoder: str = "copy",
    video_quality: str = "High",
    source_video_bitrate: int | None = None,
    loglevel: str = "error",
) -> list[str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        loglevel,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(mixed_audio_path),
    ]
    if video_encoder in H264_ENCODER_PREFERENCE:
        command.extend(
            [
                "-c:v",
                video_encoder,
                "-pix_fmt",
                "yuv420p",
            ]
        )
        command.extend(_encoder_quality_args(video_encoder, video_quality, source_video_bitrate))
    elif video_encoder in H265_ENCODER_PREFERENCE:
        command.extend(
            [
                "-c:v",
                video_encoder,
                "-pix_fmt",
                "yuv420p",
            ]
        )
        command.extend(_encoder_quality_args(video_encoder, video_quality, source_video_bitrate))
    else:
        command.extend(["-c:v", "copy"])
    command.extend(
        [
        "-c:a",
        "aac",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        str(output_path),
        ]
    )
    return command


def _encoder_quality_args(
    video_encoder: str,
    video_quality: str,
    source_video_bitrate: int | None = None,
) -> list[str]:
    if video_encoder.endswith("videotoolbox"):
        bitrate = _target_hardware_bitrate(video_quality, source_video_bitrate)
        args: list[str] = []
        if video_encoder == "hevc_videotoolbox":
            # A listed VideoToolbox encoder can still lack a hardware session.
            # Allow FFmpeg's supported software fallback instead of failing late.
            args.extend(["-allow_sw", "1"])
        args.extend(["-b:v", str(bitrate)])
        return args
    encoder = (
        EXPORT_H265_ENCODER
        if video_encoder in H265_ENCODER_PREFERENCE
        else EXPORT_H264_ENCODER
    )
    return ["-preset", "medium", "-crf", str(_crf_for_quality(video_quality, encoder=encoder))]


def _target_hardware_bitrate(video_quality: str, source_video_bitrate: int | None) -> int:
    """Keep hardware exports proportional to the source instead of using 5M blindly."""
    baseline = source_video_bitrate or 2_000_000
    multiplier = {
        "highest quality": 1.5,
        "high": 1.2,
        "balanced": 1.0,
        "small file": 0.7,
    }.get(video_quality.lower(), 1.0)
    return max(500_000, round(baseline * multiplier / 10_000) * 10_000)


def build_tts_only_mix_command(
    ffmpeg: str,
    speech_tracks: list[MixSpeechTrack],
    mixed_audio_path: Path,
) -> list[str]:
    """Mix visible TTS clips over silence without leaking pipeline/audio.wav."""
    duration = max(
        (
            track.delay_ms / 1000.0
            + track.generated_duration / track.atempo
            for track in speech_tracks
            if track.atempo > 0
        ),
        default=0.0,
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        "anullsrc=channel_layout=mono:sample_rate=16000",
    ]
    for track in speech_tracks:
        command.extend(["-i", str(track.tts_path)])
    command.extend(
        [
            "-filter_complex",
            build_mix_filter_complex(speech_tracks, [], 0.0),
            "-map",
            "[mixed]",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(mixed_audio_path),
        ]
    )
    return command


def build_output_probe_command(ffprobe: str, output_path: Path) -> list[str]:
    return [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,width,height,pix_fmt,bit_rate,nb_frames,"
            "r_frame_rate,avg_frame_rate,time_base,duration:stream_tags=rotate:"
            "format=duration,format_name:format_tags=major_brand,compatible_brands"
        ),
        "-of",
        "json",
        str(output_path),
    ]


def probe_output_streams(ffprobe: str, output_path: Path) -> ExportStreamSummary:
    command = build_output_probe_command(ffprobe, output_path)
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, **process.gui_subprocess_kwargs()
        )
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr.strip() or exc.stdout.strip() or f"ffprobe exited with {exc.returncode}"
        raise ExportError(f"export output probe failed: {msg}") from exc

    stdout = getattr(result, "stdout", "")
    if not isinstance(stdout, str):
        # Unit tests often use MagicMock subprocess results. Real ffprobe always
        # returns text because this call uses text=True.
        return ExportStreamSummary(video_streams=1, audio_streams=1, raw_streams=[])
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ExportError("export output probe failed: invalid ffprobe JSON") from exc

    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    video_count = sum(
        1 for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    )
    audio_count = sum(
        1 for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    )
    format_payload = payload.get("format", {})
    format_name = format_payload.get("format_name") if isinstance(format_payload, dict) else None
    container_names = tuple(
        name.strip().lower() for name in str(format_name or "").split(",") if name.strip()
    )
    return ExportStreamSummary(
        video_streams=video_count,
        audio_streams=audio_count,
        raw_streams=[stream for stream in streams if isinstance(stream, dict)],
        container_names=container_names,
    )


def validate_export_streams(ffprobe: str, output_path: Path) -> ExportStreamSummary:
    summary = probe_output_streams(ffprobe, output_path)
    missing = []
    if summary.video_streams == 0:
        missing.append("video")
    if summary.audio_streams == 0:
        missing.append("audio")
    if missing:
        raise ExportError(
            "export output is missing required stream(s): " + ", ".join(missing)
        )
    return summary


def probe_source_streams_for_export(
    ffprobe: str,
    source_video: Path,
    *,
    known_source_codec: str | None = None,
) -> ExportStreamSummary:
    try:
        return probe_output_streams(ffprobe, source_video)
    except ExportError:
        if known_source_codec:
            return ExportStreamSummary(
                video_streams=1,
                audio_streams=0,
                raw_streams=[
                    {
                        "codec_type": "video",
                        "codec_name": known_source_codec,
                    }
                ],
            )
        return ExportStreamSummary(video_streams=0, audio_streams=0, raw_streams=[])


def choose_export_video_encoder(
    source_summary: ExportStreamSummary,
    requested_codec: str,
    *,
    video_preset: str = "compatible_h264",
    encoder_capabilities: ExportEncoderCapabilities | None = None,
) -> tuple[str, str]:
    source_codec = source_summary.first_video_codec
    preset = video_preset.lower()
    if preset in {"fastest", "original_codec"}:
        return "copy", f"{preset} preset keeps the source video stream"
    if preset == "high_compression_h265":
        encoder = (
            encoder_capabilities.h265_encoder
            if encoder_capabilities is not None
            else EXPORT_H265_ENCODER
        )
        if encoder is None:
            raise ExportError("H.265 preset unavailable: no supported H.265 encoder is available.")
        return encoder, "H.265 preset re-encodes to a playable MP4"
    if preset == "compatible_h264":
        encoder = (
            encoder_capabilities.h264_encoder
            if encoder_capabilities is not None
            else EXPORT_H264_ENCODER
        )
        if encoder is None:
            raise ExportError("H.264 preset unavailable: no supported H.264 encoder is available.")
        suffix = f" from {source_codec}" if source_codec else ""
        return encoder, f"Compatible preset re-encodes{suffix} to H.264"
    requested = requested_codec.lower()
    if requested in {"h264", "libx264"} and source_codec in EXPORT_REENCODE_REQUIRED_CODECS:
        return EXPORT_H264_ENCODER, f"source codec {source_codec} requires H.264 export"
    return "copy", "source codec can be stream-copied"


def _crf_for_quality(video_quality: str, *, encoder: str = EXPORT_H264_ENCODER) -> int:
    quality = video_quality.lower()
    if encoder == EXPORT_H265_ENCODER:
        return {
            "highest quality": 18,
            "high": 22,
            "balanced": 26,
            "small file": 30,
        }.get(quality, 26)
    return {
        "highest quality": 16,
        "high": 18,
        "balanced": 22,
        "small file": 28,
    }.get(quality, 22)


def _source_video_bitrate(source_summary: ExportStreamSummary) -> int | None:
    for stream in source_summary.raw_streams:
        if stream.get("codec_type") != "video":
            continue
        value = stream.get("bit_rate")
        try:
            bitrate = int(str(value))
        except (TypeError, ValueError):
            return None
        return bitrate if bitrate > 0 else None
    return None


def _run_ffmpeg_with_progress(
    command: list[str],
    duration_seconds: float | None,
    on_progress: Callable[[FFmpegProgress], None],
    is_cancelled: Callable[[], bool] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg while consuming its key/value progress pipe."""
    if command and command[-1] != "-progress":
        command = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]
    started = time.monotonic()
    ffmpeg_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        **process.gui_subprocess_kwargs(),
    )
    values: dict[str, str] = {}
    if ffmpeg_process.stdout is not None:
        for line in ffmpeg_process.stdout:
            if is_cancelled is not None and is_cancelled():
                ffmpeg_process.terminate()
                break
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value
            if key not in {"progress", "out_time_ms"}:
                continue
            try:
                encoded_seconds = float(values.get("out_time_ms", "0")) / 1_000_000
            except ValueError:
                encoded_seconds = None
            percent = (
                min(99, max(0, round(encoded_seconds / duration_seconds * 100)))
                if duration_seconds and encoded_seconds is not None
                else 0
            )
            elapsed = time.monotonic() - started
            remaining = (
                max(0.0, elapsed * (duration_seconds / encoded_seconds - 1))
                if duration_seconds and encoded_seconds and elapsed > 0
                else None
            )
            on_progress(
                FFmpegProgress(
                    percent=100 if value == "end" else percent,
                    frame=_int_or_none(values.get("frame")),
                    fps=_float_or_none(values.get("fps")),
                    encoded_time_seconds=encoded_seconds,
                    elapsed_seconds=elapsed,
                    remaining_seconds=remaining,
                    output_size_bytes=_int_or_none(values.get("total_size")),
                    speed=_parse_speed(values.get("speed")),
                    command=tuple(command),
                )
            )
    stdout, stderr = ffmpeg_process.communicate()
    result = subprocess.CompletedProcess(command, ffmpeg_process.returncode, stdout, stderr)
    if ffmpeg_process.returncode:
        raise subprocess.CalledProcessError(
            ffmpeg_process.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )
    return result


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _parse_speed(value: str | None) -> float | None:
    if not value or value == "N/A":
        return None
    try:
        return float(value.rstrip("x"))
    except ValueError:
        return None


def export_project(
    project: Project,
    editables: dict[int, EditableSegment],
    tool_config: ToolConfig,
    options: ExportOptions,
    timeline: Timeline | None = None,
    on_stage: Callable[[ExportStage], None] | None = None,
    on_progress: Callable[[FFmpegProgress], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> ExportResult:
    def _stage(s: ExportStage) -> None:
        if on_stage:
            on_stage(s)

    def _cancelled() -> bool:
        return is_cancelled is not None and is_cancelled()

    _stage(ExportStage.PREPARING)

    source_video = project.export_video_path
    if source_video is None or not source_video.exists():
        raise ExportError(f"source video not found: {source_video}")
    source_audio = project.extracted_audio_path
    if options.include_original_movie_audio and not source_audio.exists():
        raise ExportError(f"source audio not found: {source_audio}")

    try:
        ffmpeg = validate_ffmpeg(tool_config)
        ffprobe = validate_ffprobe(tool_config)
    except VS4Error as exc:
        raise ExportError(str(exc)) from exc
    encoder_capabilities = probe_export_encoder_capabilities(ffmpeg)

    source_stream_summary = probe_source_streams_for_export(
        ffprobe,
        source_video,
        known_source_codec=project.source_codec,
    )
    if options.video_preset.lower() in {"fastest", "original_codec"}:
        can_stream_copy, reason = probe_stream_copy_capability(ffmpeg, source_video)
        if not can_stream_copy:
            raise ExportError(f"Stream-copy preset unavailable: {reason}")
    video_encoder, video_encoder_reason = choose_export_video_encoder(
        source_stream_summary,
        options.video_codec,
        video_preset=options.video_preset,
        encoder_capabilities=encoder_capabilities,
    )

    if _cancelled():
        raise ExportError("export cancelled")

    output_path = options.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _stage(ExportStage.MIXING_AUDIO)

    speech_tracks = (
        build_export_timeline_speech_tracks(timeline, tool_config)
        if timeline is not None
        else build_export_speech_tracks(
            project.segments, editables, project.tts_directory, tool_config
        )
    )
    if not speech_tracks:
        raise ExportError("no synthesized speech WAV files were found — nothing to export")

    if _cancelled():
        raise ExportError("export cancelled")

    duck_windows = build_duck_windows(speech_tracks)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=output_path.parent)
    mixed_audio_path = Path(tmp_name)
    mix_failure: dict | None = None
    try:
        os.close(tmp_fd)

        if options.include_original_movie_audio:
            mix_command = build_mix_command(
                ffmpeg=ffmpeg,
                source_audio_path=source_audio,
                speech_tracks=speech_tracks,
                duck_windows=duck_windows,
                duck_volume=tool_config.duck_volume,
                mixed_audio_path=mixed_audio_path,
            )
        else:
            mix_command = build_tts_only_mix_command(
                ffmpeg=ffmpeg,
                speech_tracks=speech_tracks,
                mixed_audio_path=mixed_audio_path,
            )
        try:
            subprocess.run(
                mix_command,
                check=True,
                capture_output=True,
                text=True,
                **process.gui_subprocess_kwargs(),
            )
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
            mix_failure = _audio_mix_diagnostics(
                output_path=output_path,
                mixed_audio_path=mixed_audio_path,
                speech_tracks=speech_tracks,
                source_audio_path=source_audio if options.include_original_movie_audio else None,
            )
            mix_failure.update(
                {
                    "phase": "audio_mix",
                    "ffmpeg_command": mix_command,
                    "exit_code": exc.returncode,
                    "ffmpeg_stderr": msg,
                }
            )
            if "no space left on device" in msg.lower():
                free_space = _format_bytes(mix_failure["free_space_bytes"])
                required = _format_bytes(mix_failure["estimated_temp_bytes"])
                raise ExportError(
                    "Export failed because there is not enough disk space. "
                    f"Free space: {free_space}. Estimated temporary audio space: {required}."
                ) from exc
            raise ExportError(f"audio mix failed: {msg}") from exc

        if not mixed_audio_path.exists():
            raise ExportError("audio mix did not produce expected file")

        if _cancelled():
            raise ExportError("export cancelled")

        _stage(ExportStage.RENDERING_VIDEO)

        mux_command = build_mux_command(
            ffmpeg=ffmpeg,
            video_path=source_video,
            mixed_audio_path=mixed_audio_path,
            output_path=output_path,
            video_encoder=video_encoder,
            video_quality=options.video_quality,
            source_video_bitrate=_source_video_bitrate(source_stream_summary),
            loglevel="info",
        )
        try:
            if on_progress is not None:
                duration = _duration_seconds(source_stream_summary)
                mux_result = _run_ffmpeg_with_progress(
                    mux_command,
                    duration,
                    on_progress,
                    _cancelled,
                )
            else:
                mux_result = subprocess.run(
                    mux_command,
                    check=True,
                    capture_output=True,
                    text=True,
                    **process.gui_subprocess_kwargs(),
                )
        except subprocess.CalledProcessError as exc:
            _write_export_failure_debug(
                project.project_path,
                mux_command,
                output_path,
                exc.returncode,
                exc.stderr if isinstance(exc.stderr, str) else "",
            )
            if _cancelled():
                output_path.unlink(missing_ok=True)
                raise ExportError("export cancelled") from exc
            msg = exc.stderr.strip() or exc.stdout.strip() or f"ffmpeg exited with {exc.returncode}"
            raise ExportError(f"video render failed: {msg}") from exc

        if not output_path.exists():
            raise ExportError(f"export did not produce expected file: {output_path}")
        stream_summary = probe_output_streams(ffprobe, output_path)
        _write_export_debug(
            project.project_path,
            project_name=project.project_path.name,
            input_video=source_video,
            input_audio=source_audio,
            mixed_audio=mixed_audio_path,
            mux_command=mux_command,
            ffmpeg_stdout=getattr(mux_result, "stdout", ""),
            ffmpeg_stderr=getattr(mux_result, "stderr", ""),
            output_path=output_path,
            source_stream_summary=source_stream_summary,
            stream_summary=stream_summary,
            video_encoder=video_encoder,
            video_encoder_reason=video_encoder_reason,
        )
        if stream_summary.video_streams == 0 or stream_summary.audio_streams == 0:
            missing = []
            if stream_summary.video_streams == 0:
                missing.append("video")
            if stream_summary.audio_streams == 0:
                missing.append("audio")
            raise ExportError(
                "export output is missing required stream(s): " + ", ".join(missing)
            )

    finally:
        if mix_failure is not None:
            mix_failure["temporary_file_size_before_cleanup_bytes"] = (
                mixed_audio_path.stat().st_size if mixed_audio_path.exists() else 0
            )
        mixed_audio_path.unlink(missing_ok=True)
        if mix_failure is not None:
            mix_failure["temporary_file_cleaned"] = not mixed_audio_path.exists()
            _write_export_failure_debug(
                project.project_path,
                mix_failure.get("ffmpeg_command", []),
                output_path,
                int(mix_failure.get("exit_code", 1)),
                str(mix_failure.get("ffmpeg_stderr", "")),
                diagnostics=mix_failure,
            )

    _stage(ExportStage.FINALIZING)

    if _cancelled():
        output_path.unlink(missing_ok=True)
        raise ExportError("export cancelled")

    _stage(ExportStage.COMPLETED)
    return ExportResult(output_path=output_path)


def _duration_seconds(summary: ExportStreamSummary) -> float | None:
    for stream in summary.raw_streams:
        if stream.get("codec_type") != "video":
            continue
        try:
            duration = float(str(stream.get("duration")))
        except (TypeError, ValueError):
            return None
        return duration if duration > 0 else None
    return None


def _audio_mix_diagnostics(
    *,
    output_path: Path,
    mixed_audio_path: Path,
    speech_tracks: list[MixSpeechTrack],
    source_audio_path: Path | None,
) -> dict:
    """Collect compact, non-user-facing facts for a failed PCM mix."""
    destination = output_path.parent
    free_space = shutil.disk_usage(destination).free
    timeline_end = max(
        (
            track.delay_ms / 1000.0 + track.generated_duration / track.atempo
            for track in speech_tracks
            if track.atempo > 0
        ),
        default=0.0,
    )
    source_duration = 0.0
    if source_audio_path is not None and source_audio_path.is_file():
        try:
            source_duration = probe_wav_duration_seconds(source_audio_path)
        except DurationReportError:
            source_duration = 0.0
    estimated_duration = max(timeline_end, source_duration)
    return {
        "output_path": str(output_path),
        "temporary_directory": str(destination),
        "temporary_audio_path": str(mixed_audio_path),
        "free_space_bytes": free_space,
        "audio_input_count": len(speech_tracks) + (1 if source_audio_path else 0),
        "tts_input_count": len(speech_tracks),
        "total_input_duration_seconds": round(
            sum(track.generated_duration for track in speech_tracks) + source_duration, 3
        ),
        "estimated_mix_duration_seconds": round(estimated_duration, 3),
        "estimated_temp_bytes": math.ceil(estimated_duration * MIX_SAMPLE_RATE * 2 + 44),
        "source_audio_path": str(source_audio_path) if source_audio_path else None,
    }


def _format_bytes(value: int) -> str:
    if value < 1024**3:
        return f"{value / 1024**2:.1f} MB"
    return f"{value / 1024**3:.2f} GB"


def _write_export_debug(
    project_path: Path,
    *,
    project_name: str,
    input_video: Path,
    input_audio: Path,
    mixed_audio: Path,
    mux_command: list[str],
    ffmpeg_stdout: str,
    ffmpeg_stderr: str,
    output_path: Path,
    source_stream_summary: ExportStreamSummary,
    stream_summary: ExportStreamSummary,
    video_encoder: str,
    video_encoder_reason: str,
) -> None:
    debug_path = project_path / "exports" / "last_export_debug.json"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(
        json.dumps(
            {
                "project_path": str(project_path),
                "project_name": project_name,
                "input_video": str(input_video),
                "input_audio": str(input_audio),
                "mixed_audio": str(mixed_audio),
                "ffmpeg_command": mux_command,
                "ffmpeg_stdout": ffmpeg_stdout if isinstance(ffmpeg_stdout, str) else "",
                "ffmpeg_stderr": ffmpeg_stderr if isinstance(ffmpeg_stderr, str) else "",
                "mapped_streams": ["0:v:0", "1:a:0"],
                "video_encoder": video_encoder,
                "video_encoder_reason": video_encoder_reason,
                "output_path": str(output_path),
                "source_streams": {
                    "video": source_stream_summary.video_streams,
                    "audio": source_stream_summary.audio_streams,
                    "raw": source_stream_summary.raw_streams,
                },
                "output_streams": {
                    "video": stream_summary.video_streams,
                    "audio": stream_summary.audio_streams,
                    "raw": stream_summary.raw_streams,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_export_failure_debug(
    project_path: Path,
    command: list[str],
    output_path: Path,
    exit_code: int,
    stderr: str,
    *,
    diagnostics: dict | None = None,
) -> None:
    debug_path = project_path / "exports" / "last_export_debug.json"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(
        json.dumps(
            {
                "ffmpeg_command": command,
                "output_path": str(output_path),
                "exit_code": exit_code,
                "ffmpeg_stderr": stderr,
                "diagnostics": diagnostics or {},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
