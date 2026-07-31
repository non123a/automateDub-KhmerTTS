"""Recent-project persistence for the Studio home dashboard."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from automatedub_studio.project.manager import PROJECT_METADATA_FILENAME


@dataclass(frozen=True)
class RecentProject:
    project_path: Path
    name: str
    last_opened: str
    status: str = "unknown"
    pinned: bool = False


class RecentProjectsManager:
    """Qt-free manager for persisted recent projects."""

    def __init__(self, path: Path):
        self.path = path

    def list_projects(self) -> list[RecentProject]:
        projects = [_recent_from_payload(item) for item in self._read().get("projects", [])]
        existing = [project for project in projects if project is not None]
        return sorted(existing, key=lambda item: (item.pinned, item.last_opened), reverse=True)

    def add_project(
        self,
        project_path: Path,
        *,
        metadata: dict[str, object] | None = None,
        opened_at: str | None = None,
    ) -> RecentProject:
        project_path = Path(project_path).expanduser()
        metadata = metadata if metadata is not None else _read_metadata(project_path)
        name = str(metadata.get("project_name") or project_path.stem)
        status = _project_status(metadata)
        opened_at = opened_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        existing = {project.project_path: project for project in self.list_projects()}
        pinned = existing.get(project_path, RecentProject(project_path, name, opened_at)).pinned
        project = RecentProject(
            project_path=project_path,
            name=name,
            last_opened=opened_at,
            status=status,
            pinned=pinned,
        )
        existing[project_path] = project
        self._write_projects(existing.values())
        return project

    def pin_project(self, project_path: Path, pinned: bool = True) -> None:
        projects = [
            RecentProject(
                project_path=project.project_path,
                name=project.name,
                last_opened=project.last_opened,
                status=project.status,
                pinned=pinned if project.project_path == Path(project_path) else project.pinned,
            )
            for project in self.list_projects()
        ]
        self._write_projects(projects)

    def remove_project(self, project_path: Path) -> None:
        target = Path(project_path)
        self._write_projects(
            project for project in self.list_projects() if project.project_path != target
        )

    @staticmethod
    def containing_folder(project_path: Path) -> Path:
        return Path(project_path).expanduser().parent

    def _read(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"projects": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"projects": []}
        return payload if isinstance(payload, dict) else {"projects": []}

    def _write_projects(self, projects) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "projects": [
                {
                    **asdict(project),
                    "project_path": str(project.project_path),
                }
                for project in sorted(
                    projects, key=lambda item: (item.pinned, item.last_opened), reverse=True
                )
            ]
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def default_recent_projects_path() -> Path:
    return Path.home() / ".automatedub_studio" / "recent_projects.json"


def _read_metadata(project_path: Path) -> dict[str, object]:
    metadata_path = project_path / PROJECT_METADATA_FILENAME
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_status(metadata: dict[str, object]) -> str:
    pipeline = metadata.get("pipeline")
    if isinstance(pipeline, dict):
        status = pipeline.get("status")
        if isinstance(status, str):
            return status
    return "unknown"


def _recent_from_payload(value: object) -> RecentProject | None:
    if not isinstance(value, dict):
        return None
    path = value.get("project_path")
    if not isinstance(path, str):
        return None
    return RecentProject(
        project_path=Path(path),
        name=str(value.get("name") or Path(path).stem),
        last_opened=str(value.get("last_opened") or ""),
        status=str(value.get("status") or "unknown"),
        pinned=bool(value.get("pinned", False)),
    )
