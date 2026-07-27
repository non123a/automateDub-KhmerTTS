"""Persist and restore per-segment edits without touching translation.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from automatedub_studio.project.models import Segment

if TYPE_CHECKING:
    from automatedub_studio.project.editable_project import EditableSegment

EDITED_FILENAME = "translation.edited.json"
_VERSION = 1

_FLOAT_FIELDS = {"speed", "volume"}
_INT_FIELDS = {"offset_ms", "fade_in_ms", "fade_out_ms"}
_BOOL_FIELDS = {"locked", "needs_regeneration"}
_STR_FIELDS = {"voice_id", "edited_text"}

_DEFAULTS: dict[str, object] = {
    "offset_ms": 0,
    "speed": 1.0,
    "volume": 1.0,
    "fade_in_ms": 0,
    "fade_out_ms": 0,
    "locked": False,
    "needs_regeneration": False,
    "voice_id": None,
    "edited_text": None,
}


def save_edits(
    segments: list[Segment],
    project_path: Path,
    editables: dict[int, EditableSegment] | None = None,
) -> None:
    records = []
    for s in segments:
        entry: dict[str, object] = {}
        if s.offset_ms != 0:
            entry["offset_ms"] = s.offset_ms
        if editables and (es := editables.get(s.id)):
            if es.speed != 1.0:
                entry["speed"] = round(es.speed, 4)
            if es.volume != 1.0:
                entry["volume"] = round(es.volume, 4)
            if es.fade_in_ms != 0:
                entry["fade_in_ms"] = es.fade_in_ms
            if es.fade_out_ms != 0:
                entry["fade_out_ms"] = es.fade_out_ms
            if es.locked:
                entry["locked"] = True
            if es.needs_regeneration:
                entry["needs_regeneration"] = True
            if es.voice_id is not None:
                entry["voice_id"] = es.voice_id
            if es.edited_text is not None:
                entry["edited_text"] = es.edited_text
        if entry:
            entry["id"] = s.id
            records.append(entry)
    payload = {"version": _VERSION, "segments": records}
    (project_path / EDITED_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_edits(project_path: Path) -> dict[int, dict]:
    """Return {segment_id: {field: value}} for each modified segment."""
    edited_path = project_path / EDITED_FILENAME
    if not edited_path.is_file():
        return {}
    try:
        data = json.loads(edited_path.read_text(encoding="utf-8"))
        result: dict[int, dict] = {}
        for seg in data.get("segments", []):
            raw_id = seg.get("id")
            if not isinstance(raw_id, (int, float)):
                continue
            seg_id = int(raw_id)
            entry: dict[str, object] = {}
            for field in _INT_FIELDS:
                if field in seg and isinstance(seg[field], (int, float)):
                    entry[field] = int(seg[field])
            for field in _FLOAT_FIELDS:
                if field in seg and isinstance(seg[field], (int, float)):
                    entry[field] = float(seg[field])
            for field in _BOOL_FIELDS:
                if field in seg and isinstance(seg[field], bool):
                    entry[field] = bool(seg[field])
            for field in _STR_FIELDS:
                if field in seg and isinstance(seg[field], str):
                    entry[field] = seg[field]
            if entry:
                result[seg_id] = entry
        return result
    except Exception:  # noqa: BLE001
        return {}


def apply_edits(
    segments: list[Segment],
    project_path: Path,
    editables: dict[int, EditableSegment] | None = None,
) -> None:
    from automatedub_studio.project.editable_project import EditableSegment as ES

    all_edits = load_edits(project_path)
    if not all_edits:
        return
    for seg in segments:
        entry = all_edits.get(seg.id)
        if not entry:
            continue
        if "offset_ms" in entry:
            seg.offset_ms = entry["offset_ms"]
        if editables is not None:
            es = editables.setdefault(seg.id, ES(id=seg.id))
            for field in (
                "speed",
                "volume",
                "fade_in_ms",
                "fade_out_ms",
                "locked",
                "needs_regeneration",
                "voice_id",
                "edited_text",
            ):
                if field in entry:
                    setattr(es, field, entry[field])
