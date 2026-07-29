"""Persist and restore the Studio TimelineClip editing model."""

from __future__ import annotations

import json
from pathlib import Path

from automatedub_studio.timeline.timeline_clip import Timeline

TIMELINE_EDITED_FILENAME = "timeline.edited.json"
_VERSION = 1


def save_timeline_edits(timeline: Timeline, project_path: Path) -> Path:
    payload = timeline.to_dict()
    payload["version"] = _VERSION
    _relativize_source_paths(payload, project_path)
    output_path = project_path / TIMELINE_EDITED_FILENAME
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output_path


def load_timeline_edits(project_path: Path) -> Timeline | None:
    edited_path = project_path / TIMELINE_EDITED_FILENAME
    if not edited_path.is_file():
        return None
    try:
        payload = json.loads(edited_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    _absolutize_source_paths(payload, project_path)
    return Timeline.from_dict(payload)


def _relativize_source_paths(payload: dict, project_path: Path) -> None:
    for track in payload.get("tracks", []):
        for clip in track.get("clips", []):
            source_path = clip.get("source_path")
            if not source_path:
                continue
            path = Path(source_path)
            try:
                clip["source_path"] = str(path.relative_to(project_path))
            except ValueError:
                clip["source_path"] = str(path)


def _absolutize_source_paths(payload: dict, project_path: Path) -> None:
    for track in payload.get("tracks", []):
        for clip in track.get("clips", []):
            source_path = clip.get("source_path")
            if not source_path:
                continue
            path = Path(source_path)
            if not path.is_absolute():
                clip["source_path"] = str(project_path / path)
