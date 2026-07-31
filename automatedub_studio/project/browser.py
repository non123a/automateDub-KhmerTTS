"""Project browsing and project-level actions."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from automatedub_studio.project.manager import PROJECT_METADATA_FILENAME, project_folder_name


@dataclass(frozen=True)
class ProjectDetails:
    project_path: Path
    name: str
    created_at: str
    last_modified: str
    status: str
    export_history: tuple[Path, ...]


class ProjectBrowser:
    """Qt-free service behind the project browser UI."""

    def details(self, project_path: Path) -> ProjectDetails:
        project_path = Path(project_path).expanduser()
        metadata = _read_metadata(project_path)
        stat = project_path.stat()
        exports_dir = project_path / "exports"
        exports = tuple(sorted(exports_dir.glob("*.json"))) if exports_dir.is_dir() else ()
        return ProjectDetails(
            project_path=project_path,
            name=str(metadata.get("project_name") or project_path.stem),
            created_at=str(metadata.get("created_at") or ""),
            last_modified=datetime.fromtimestamp(stat.st_mtime, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            status=_project_status(metadata),
            export_history=exports,
        )

    def rename_project(self, project_path: Path, new_name: str) -> Path:
        project_path = Path(project_path).expanduser()
        destination = project_path.parent / project_folder_name(new_name)
        if destination.exists():
            raise FileExistsError(destination)
        project_path.rename(destination)
        metadata = _read_metadata(destination)
        metadata["project_name"] = new_name.strip()
        _write_metadata(destination, metadata)
        return destination

    def duplicate_project(
        self,
        project_path: Path,
        destination_parent: Path | None = None,
        new_name: str | None = None,
    ) -> Path:
        project_path = Path(project_path).expanduser()
        destination_parent = (
            Path(destination_parent).expanduser()
            if destination_parent is not None
            else project_path.parent
        )
        name = new_name or f"{project_path.stem} Copy"
        destination = destination_parent / project_folder_name(name)
        if destination.exists():
            raise FileExistsError(destination)
        shutil.copytree(project_path, destination)
        metadata = _read_metadata(destination)
        metadata["project_name"] = name
        metadata["created_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        _write_metadata(destination, metadata)
        return destination

    def archive_project(self, project_path: Path, archive_root: Path | None = None) -> Path:
        project_path = Path(project_path).expanduser()
        archive_root = (
            Path(archive_root).expanduser()
            if archive_root is not None
            else project_path.parent / "Archived Projects"
        )
        archive_root.mkdir(parents=True, exist_ok=True)
        destination = archive_root / project_path.name
        if destination.exists():
            raise FileExistsError(destination)
        project_path.rename(destination)
        return destination

    def delete_project(self, project_path: Path) -> None:
        shutil.rmtree(Path(project_path).expanduser())


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


def _project_status(metadata: dict[str, object]) -> str:
    pipeline = metadata.get("pipeline")
    if isinstance(pipeline, dict) and isinstance(pipeline.get("status"), str):
        return str(pipeline["status"])
    return "unknown"
