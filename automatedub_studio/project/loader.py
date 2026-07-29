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
    mixed_audio_output_path,
    translation_output_path,
    tts_combined_output_path,
    tts_output_dir_path,
)
from automatedub_studio.project.models import Project, Segment

# Supported source video extensions, matched case-insensitively.
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm")
EDITOR_PROXY_VIDEO_FILENAME = "proxy_video.mp4"

PROJECT_METADATA_FILENAME = "project.json"
VIDEO_SELECTION_FILENAME = "video_selection.json"


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


def find_video_candidates(project_dir: Path) -> list[Path]:
    """Return all supported video files in *project_dir*, case-insensitively sorted."""
    return sorted(
        p for p in project_dir.iterdir()
        if (
            p.is_file()
            and p.name != EDITOR_PROXY_VIDEO_FILENAME
            and p.suffix.lower() in VIDEO_EXTENSIONS
        )
    )


def _read_json_file(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _video_path_from_metadata(
    project_dir: Path, data: dict[str, object], *keys: str
) -> Path | None:
    chosen = next((data.get(key) for key in keys if isinstance(data.get(key), str)), None)
    if not isinstance(chosen, str):
        return None
    candidate = project_dir / chosen
    if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTENSIONS:
        return candidate
    return None


def load_project_metadata_video(project_dir: Path) -> Path | None:
    """Return the project metadata video file choice, or None."""
    return _video_path_from_metadata(
        project_dir,
        _read_json_file(project_dir / PROJECT_METADATA_FILENAME),
        "source_video",
        "video_filename",
    )


def load_project_metadata_editor_video(project_dir: Path) -> Path | None:
    """Return the editor/proxy video path from project metadata, or None."""
    return _video_path_from_metadata(
        project_dir,
        _read_json_file(project_dir / PROJECT_METADATA_FILENAME),
        "editor_video",
    )


def load_project_video_codecs(project_dir: Path) -> tuple[str | None, str | None]:
    data = _read_json_file(project_dir / PROJECT_METADATA_FILENAME)
    source_codec = data.get("source_codec")
    editor_codec = data.get("editor_codec")
    return (
        source_codec if isinstance(source_codec, str) else None,
        editor_codec if isinstance(editor_codec, str) else None,
    )


def load_video_selection(project_dir: Path) -> Path | None:
    """Return the remembered video choice for this project, or None.

    `project.json` is the current metadata source. `video_selection.json` is
    still read for backward compatibility with older Studio projects.
    """
    metadata_choice = load_project_metadata_video(project_dir)
    if metadata_choice is not None:
        return metadata_choice
    return _video_path_from_metadata(
        project_dir, _read_json_file(project_dir / VIDEO_SELECTION_FILENAME), "video_filename"
    )


def save_video_selection(project_dir: Path, video_path: Path) -> None:
    """Persist the user's video file choice in project metadata."""
    metadata_path = project_dir / PROJECT_METADATA_FILENAME
    payload = _read_json_file(metadata_path)
    payload["video_filename"] = video_path.name
    payload["source_video"] = video_path.name
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def load_project(project_dir: Path) -> Project:
    project_dir = Path(project_dir)
    validate_project_directory(project_dir)

    audio_path = audio_output_path(project_dir)
    translation_path = translation_output_path(project_dir)
    tts_directory = tts_output_dir_path(project_dir)

    segments = load_segments(translation_path)
    from automatedub_studio.project.edits import apply_edits

    apply_edits(segments, project_dir)
    tts_file_count = count_tts_files(tts_directory)

    metadata_video_path = load_project_metadata_video(project_dir)
    editor_video_path = load_project_metadata_editor_video(project_dir)
    source_codec, editor_codec = load_project_video_codecs(project_dir)
    if metadata_video_path is not None:
        video_path = metadata_video_path
        video_candidates = []
    else:
        candidates = find_video_candidates(project_dir)
        remembered = load_video_selection(project_dir)
        if remembered is not None:
            video_path = remembered
            video_candidates = []
        elif len(candidates) == 0:
            video_path: Path | None = None
            video_candidates: list[Path] = []
        elif len(candidates) == 1:
            video_path = candidates[0]
            video_candidates = []
        else:
            video_path = None
            video_candidates = candidates

    mixed_audio_path = mixed_audio_output_path(project_dir)
    if not mixed_audio_path.is_file():
        mixed_audio_path = None
    tts_combined_path = tts_combined_output_path(project_dir)
    if not tts_combined_path.is_file():
        tts_combined_path = None

    return Project(
        project_path=project_dir,
        audio_path=audio_path,
        translation_path=translation_path,
        tts_directory=tts_directory,
        video_path=video_path,
        editor_video_path=editor_video_path,
        source_codec=source_codec,
        editor_codec=editor_codec,
        mixed_audio_path=mixed_audio_path,
        tts_combined_path=tts_combined_path,
        segments=segments,
        tts_file_count=tts_file_count,
        video_candidates=video_candidates,
    )
