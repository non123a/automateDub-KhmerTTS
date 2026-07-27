"""Persist and restore per-segment offset edits without touching translation.json."""

from __future__ import annotations

import json
from pathlib import Path

from automatedub_studio.project.models import Segment

EDITED_FILENAME = "translation.edited.json"
_VERSION = 1


def save_edits(segments: list[Segment], project_path: Path) -> None:
    modified = [{"id": s.id, "offset_ms": s.offset_ms} for s in segments if s.offset_ms != 0]
    payload = {"version": _VERSION, "segments": modified}
    edited_path = project_path / EDITED_FILENAME
    edited_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_edits(project_path: Path) -> dict[int, int]:
    edited_path = project_path / EDITED_FILENAME
    if not edited_path.is_file():
        return {}
    try:
        data = json.loads(edited_path.read_text(encoding="utf-8"))
        return {
            int(seg["id"]): int(seg["offset_ms"])
            for seg in data.get("segments", [])
            if isinstance(seg.get("id"), (int, float))
            and isinstance(seg.get("offset_ms"), (int, float))
        }
    except Exception:  # noqa: BLE001
        return {}


def apply_edits(segments: list[Segment], project_path: Path) -> None:
    edits = load_edits(project_path)
    if not edits:
        return
    for segment in segments:
        if segment.id in edits:
            segment.offset_ms = edits[segment.id]
