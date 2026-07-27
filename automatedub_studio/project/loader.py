"""Loading and validation for an existing AutomateDub output/ project directory.

Kept independent of the GUI: every failure raises ProjectLoadError with a
human-readable message, never lets a parsing exception escape uncaught.
Reuses automatedub.vertical_slice.mix.load_translation_segments directly
(the same translation.json parsing/validation the CLI's mix step already
does) rather than re-implementing JSON validation here.
"""

from __future__ import annotations

import json
from pathlib import Path

from automatedub.vertical_slice import mix
from automatedub.vertical_slice.paths import (
    AUDIO_FILENAME,
    TRANSLATION_FILENAME,
    TTS_DIRECTORY_NAME,
    audio_output_path,
    translation_output_path,
    tts_output_dir_path,
)
from automatedub_studio.project.models import Project, Segment

VIDEO_FILENAME = "video.mp4"

# Common source video filenames the CLI or a user might place alongside the
# rest of the output/ artifacts. Checked in order; the first match wins.
VIDEO_CANDIDATE_FILENAMES = ("video.mp4", "movie.mp4", "input.mp4")


class ProjectLoadError(Exception):
    """Raised when a directory cannot be opened as a Studio project."""


def validate_project_directory(project_dir: Path) -> None:
    if not project_dir.is_dir():
        raise ProjectLoadError(f"{project_dir} is not a directory.")

    missing = []
    if not audio_output_path(project_dir).is_file():
        missing.append(AUDIO_FILENAME)
    if not translation_output_path(project_dir).is_file():
        missing.append(TRANSLATION_FILENAME)
    if not tts_output_dir_path(project_dir).is_dir():
        missing.append(f"{TTS_DIRECTORY_NAME}/")

    if missing:
        raise ProjectLoadError(
            "This does not look like an AutomateDub output folder.\n"
            f"Missing: {', '.join(missing)}"
        )


def load_segments(translation_path: Path) -> list[Segment]:
    try:
        mix_segments = mix.load_translation_segments(translation_path)
    except mix.VS4Error as exc:
        raise ProjectLoadError(str(exc)) from exc

    # load_translation_segments only captures target_text; read the raw JSON
    # once more to also capture source_text for the timeline tooltip.
    try:
        raw = json.loads(translation_path.read_text(encoding="utf-8"))
        source_map: dict[int, str] = {
            seg["id"]: seg.get("source_text", "")
            for seg in raw.get("segments", [])
            if isinstance(seg, dict) and isinstance(seg.get("id"), int)
        }
    except Exception:  # noqa: BLE001
        source_map = {}

    return [
        Segment(
            id=segment.id,
            start=segment.start,
            end=segment.end,
            source_text=source_map.get(segment.id, ""),
            target_text=segment.target_text,
        )
        for segment in mix_segments
    ]


def count_tts_files(tts_dir: Path) -> int:
    return sum(1 for path in tts_dir.iterdir() if path.is_file() and path.suffix.lower() == ".wav")


def find_video_path(project_dir: Path) -> Path | None:
    for filename in VIDEO_CANDIDATE_FILENAMES:
        video_path = project_dir / filename
        if video_path.is_file():
            return video_path
    return None


def load_project(project_dir: Path) -> Project:
    project_dir = Path(project_dir)
    validate_project_directory(project_dir)

    audio_path = audio_output_path(project_dir)
    translation_path = translation_output_path(project_dir)
    tts_directory = tts_output_dir_path(project_dir)

    segments = load_segments(translation_path)
    tts_file_count = count_tts_files(tts_directory)
    video_path = find_video_path(project_dir)

    return Project(
        project_path=project_dir,
        audio_path=audio_path,
        translation_path=translation_path,
        tts_directory=tts_directory,
        video_path=video_path,
        segments=segments,
        tts_file_count=tts_file_count,
    )
