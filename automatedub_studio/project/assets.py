"""Missing media detection and relinking for Studio projects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from automatedub_studio.project.manager import PROJECT_METADATA_FILENAME


@dataclass(frozen=True)
class MissingAsset:
    key: str
    path: Path
    description: str


class MissingAssetRecovery:
    """Detects and relinks project assets referenced by project metadata."""

    def missing_assets(self, project_path: Path) -> list[MissingAsset]:
        project_path = Path(project_path).expanduser()
        metadata = _read_metadata(project_path)
        missing: list[MissingAsset] = []
        for key, description in (
            ("source_video", "Source media"),
            ("editor_video", "Editor playback media"),
        ):
            value = metadata.get(key)
            if not isinstance(value, str) or not value:
                continue
            path = _resolve_project_path(project_path, value)
            if not path.is_file():
                missing.append(MissingAsset(key=key, path=path, description=description))
        return missing

    def relink_source_video(self, project_path: Path, replacement: Path) -> None:
        project_path = Path(project_path).expanduser()
        replacement = Path(replacement).expanduser()
        if not replacement.is_file():
            raise FileNotFoundError(replacement)
        metadata = _read_metadata(project_path)
        try:
            source_value = replacement.relative_to(project_path).as_posix()
        except ValueError:
            source_value = str(replacement)
        metadata["source_video"] = source_value
        if metadata.get("editor_video") in (None, "") or any(
            item.key == "editor_video" for item in self.missing_assets(project_path)
        ):
            metadata["editor_video"] = source_value
        _write_metadata(project_path, metadata)


def _resolve_project_path(project_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_path / path


def _read_metadata(project_path: Path) -> dict[str, object]:
    metadata_path = project_path / PROJECT_METADATA_FILENAME
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_metadata(project_path: Path, metadata: dict[str, object]) -> None:
    (project_path / PROJECT_METADATA_FILENAME).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
