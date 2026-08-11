"""Editor video proxy preparation for Studio preview playback."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from automatedub.config import ToolConfig, resolve_executable
from automatedub_studio.project.loader import (
    PROJECT_METADATA_FILENAME,
    _read_json_file,
)

PROXY_VIDEO_FILENAME = "proxy_video.mp4"
PROXY_REQUIRED_CODECS = {"av1"}
EDITOR_PROXY_CODEC = "h264"


class VideoProxyError(Exception):
    """Raised when Studio cannot prepare a video for editor playback."""


@dataclass(frozen=True)
class VideoProbe:
    codec: str
    width: int
    height: int
    fps: str


@dataclass(frozen=True)
class VideoProxyResult:
    source_video: Path
    editor_video: Path
    source_codec: str
    editor_codec: str
    proxy_required: bool
    proxy_reused: bool = False
    proxy_generated: bool = False


def requires_proxy(probe: VideoProbe) -> bool:
    return probe.codec.lower() in PROXY_REQUIRED_CODECS


def proxy_video_path(project_dir: Path) -> Path:
    return project_dir / PROXY_VIDEO_FILENAME


def proxy_is_current(source_video: Path, proxy_video: Path) -> bool:
    if not proxy_video.is_file():
        return False
    return proxy_video.stat().st_mtime >= source_video.stat().st_mtime


def probe_video(ffprobe: str, video_path: Path) -> VideoProbe:
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoProxyError("ffprobe is not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or f"ffprobe exited with {exc.returncode}"
        )
        raise VideoProxyError(f"ffprobe failed for {video_path.name}: {message}") from exc

    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise VideoProxyError(
            f"ffprobe did not report a video stream for {video_path.name}"
        ) from exc

    codec = str(stream.get("codec_name") or "").lower()
    if not codec:
        raise VideoProxyError(f"ffprobe did not report a codec for {video_path.name}")
    return VideoProbe(
        codec=codec,
        width=int(stream.get("width") or 0),
        height=int(stream.get("height") or 0),
        fps=str(stream.get("r_frame_rate") or ""),
    )


def build_proxy_command(
    ffmpeg: str, source_video: Path, proxy_video: Path
) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-fps_mode",
        "passthrough",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(proxy_video),
    ]


def prepare_editor_video(
    project_dir: Path,
    source_video: Path,
    tool_config: ToolConfig,
    on_progress: Callable[[str], None] | None = None,
) -> VideoProxyResult:
    ffprobe = resolve_executable(tool_config.ffprobe_path)
    if ffprobe is None:
        raise VideoProxyError("ffprobe is not available on PATH")
    if on_progress is not None:
        on_progress("Preparing video for editing...")
    source_probe = probe_video(ffprobe, source_video)
    if not requires_proxy(source_probe):
        result = VideoProxyResult(
            source_video=source_video,
            editor_video=source_video,
            source_codec=source_probe.codec,
            editor_codec=source_probe.codec,
            proxy_required=False,
        )
        save_project_video_metadata(project_dir, result)
        return result

    proxy_video = proxy_video_path(project_dir)
    if proxy_is_current(source_video, proxy_video):
        result = VideoProxyResult(
            source_video=source_video,
            editor_video=proxy_video,
            source_codec=source_probe.codec,
            editor_codec=EDITOR_PROXY_CODEC,
            proxy_required=True,
            proxy_reused=True,
        )
        save_project_video_metadata(project_dir, result)
        return result

    ffmpeg = resolve_executable(tool_config.ffmpeg_path)
    if ffmpeg is None:
        raise VideoProxyError("ffmpeg is not available on PATH")

    if on_progress is not None:
        on_progress("Optimizing video...")
    command = build_proxy_command(ffmpeg, source_video, proxy_video)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoProxyError("ffmpeg is not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or f"ffmpeg exited with {exc.returncode}"
        )
        raise VideoProxyError(f"ffmpeg failed to create proxy video: {message}") from exc

    result = VideoProxyResult(
        source_video=source_video,
        editor_video=proxy_video,
        source_codec=source_probe.codec,
        editor_codec=EDITOR_PROXY_CODEC,
        proxy_required=True,
        proxy_generated=True,
    )
    save_project_video_metadata(project_dir, result)
    return result


def save_project_video_metadata(project_dir: Path, result: VideoProxyResult) -> None:
    metadata_path = project_dir / PROJECT_METADATA_FILENAME
    payload = _read_json_file(metadata_path)
    try:
        source_value = result.source_video.relative_to(project_dir).as_posix()
    except ValueError:
        source_value = result.source_video.name
    try:
        editor_value = result.editor_video.relative_to(project_dir).as_posix()
    except ValueError:
        editor_value = result.editor_video.name
    payload.update(
        {
            "source_video": source_value,
            "editor_video": editor_value,
            "editor_codec": result.editor_codec,
            "source_codec": result.source_codec,
            "video_filename": source_value,
        }
    )
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
