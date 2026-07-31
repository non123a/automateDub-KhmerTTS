"""Project creation services for AutomateDub Studio."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_EXTENSION = ".autodub"
PROJECT_METADATA_FILENAME = "project.json"
PROJECT_DIRECTORIES = (
    "source",
    "pipeline",
    "timeline",
    "tts",
    "cache",
    "exports",
    "logs",
)


class ProjectCreationError(Exception):
    """Raised when a new project cannot be created."""


@dataclass(frozen=True)
class NewProjectRequest:
    project_name: str
    project_location: Path
    video_file: Path
    source_language: str
    target_language: str


@dataclass(frozen=True)
class CreatedProject:
    project_path: Path
    source_video_path: Path
    metadata_path: Path
    metadata: dict[str, object]


def project_folder_name(project_name: str) -> str:
    """Return a filesystem-friendly `.autodub` folder name."""
    normalized = re.sub(r"\s+", " ", project_name.strip())
    if not normalized:
        raise ProjectCreationError("Project name is required.")
    safe = re.sub(r"[^\w .-]", "-", normalized, flags=re.UNICODE).strip(" .")
    if not safe:
        raise ProjectCreationError("Project name must contain a valid filename character.")
    if not safe.endswith(PROJECT_EXTENSION):
        safe = f"{safe}{PROJECT_EXTENSION}"
    return safe


class ProjectManager:
    """Qt-free application service for creating Studio projects."""

    def create_project(self, request: NewProjectRequest) -> CreatedProject:
        created = self.create_project_structure(request)
        try:
            self.copy_source_video(request, created)
        except Exception:
            if created.project_path.exists():
                shutil.rmtree(created.project_path)
            raise
        return self.write_project_metadata(
            created,
            {
                "source_video": created.source_video_path.relative_to(
                    created.project_path
                ).as_posix(),
                "editor_video": created.source_video_path.relative_to(
                    created.project_path
                ).as_posix(),
            },
        )

    def create_project_structure(self, request: NewProjectRequest) -> CreatedProject:
        project_name = request.project_name.strip()
        if not project_name:
            raise ProjectCreationError("Project name is required.")

        location = Path(request.project_location).expanduser()
        video_file = Path(request.video_file).expanduser()

        location.mkdir(parents=True, exist_ok=True)
        project_path = location / project_folder_name(project_name)
        if project_path.exists():
            raise ProjectCreationError(f"Project already exists: {project_path}")

        try:
            project_path.mkdir()
            for directory_name in PROJECT_DIRECTORIES:
                (project_path / directory_name).mkdir()

            source_video_path = project_path / "source" / video_file.name
            metadata: dict[str, object] = {
                "version": 1,
                "project_name": project_name,
                "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "source_language": request.source_language,
                "target_language": request.target_language,
                "source_video": source_video_path.relative_to(project_path).as_posix(),
                "editor_video": source_video_path.relative_to(project_path).as_posix(),
                "pipeline": {
                    "status": "created",
                    "stages": [],
                },
            }
            metadata_path = project_path / PROJECT_METADATA_FILENAME
            self._write_metadata(metadata_path, metadata)
        except Exception as exc:
            if project_path.exists():
                shutil.rmtree(project_path)
            if isinstance(exc, ProjectCreationError):
                raise
            raise ProjectCreationError(f"Failed to create project: {exc}") from exc

        return CreatedProject(
            project_path=project_path,
            source_video_path=source_video_path,
            metadata_path=metadata_path,
            metadata=metadata,
        )

    def copy_source_video(
        self, request: NewProjectRequest, created_project: CreatedProject
    ) -> Path:
        source_video = Path(request.video_file).expanduser()
        if not source_video.is_file():
            raise ProjectCreationError(f"Video file not found: {source_video}")
        created_project.source_video_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_video, created_project.source_video_path)
        return created_project.source_video_path

    def write_project_metadata(
        self,
        created_project: CreatedProject,
        updates: dict[str, object] | None = None,
    ) -> CreatedProject:
        metadata = dict(created_project.metadata)
        if updates:
            metadata.update(updates)
        self._write_metadata(created_project.metadata_path, metadata)
        return CreatedProject(
            project_path=created_project.project_path,
            source_video_path=created_project.source_video_path,
            metadata_path=created_project.metadata_path,
            metadata=metadata,
        )

    @staticmethod
    def _write_metadata(metadata_path: Path, metadata: dict[str, object]) -> None:
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
