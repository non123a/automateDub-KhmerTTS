from __future__ import annotations

import json

import pytest

from automatedub_studio.project.manager import (
    PROJECT_DIRECTORIES,
    NewProjectRequest,
    ProjectCreationError,
    ProjectManager,
    project_folder_name,
)


def test_project_folder_name_adds_autodub_suffix():
    assert project_folder_name("My Film") == "My Film.autodub"
    assert project_folder_name("My Film.autodub") == "My Film.autodub"


def test_create_project_initializes_autodub_folder(tmp_path):
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")

    created = ProjectManager().create_project(
        NewProjectRequest(
            project_name="Khmer Cut",
            project_location=tmp_path,
            video_file=video_file,
            source_language="Chinese",
            target_language="Khmer",
        )
    )

    assert created.project_path == tmp_path / "Khmer Cut.autodub"
    assert created.metadata_path == created.project_path / "project.json"
    for directory_name in PROJECT_DIRECTORIES:
        assert (created.project_path / directory_name).is_dir()
    assert created.source_video_path == created.project_path / "source" / "movie.mp4"
    assert created.source_video_path.read_bytes() == b"video"

    metadata = json.loads(created.metadata_path.read_text(encoding="utf-8"))
    assert metadata["project_name"] == "Khmer Cut"
    assert metadata["source_language"] == "Chinese"
    assert metadata["target_language"] == "Khmer"
    assert metadata["source_video"] == "source/movie.mp4"
    assert metadata["editor_video"] == "source/movie.mp4"
    assert metadata["pipeline"]["status"] == "created"


def test_create_project_rejects_existing_project_folder(tmp_path):
    video_file = tmp_path / "movie.mp4"
    video_file.write_bytes(b"video")
    (tmp_path / "Khmer Cut.autodub").mkdir()

    with pytest.raises(ProjectCreationError, match="already exists"):
        ProjectManager().create_project(
            NewProjectRequest(
                project_name="Khmer Cut",
                project_location=tmp_path,
                video_file=video_file,
                source_language="Chinese",
                target_language="Khmer",
            )
        )


def test_create_project_requires_existing_video_file(tmp_path):
    with pytest.raises(ProjectCreationError, match="Video file not found"):
        ProjectManager().create_project(
            NewProjectRequest(
                project_name="Khmer Cut",
                project_location=tmp_path,
                video_file=tmp_path / "missing.mp4",
                source_language="Chinese",
                target_language="Khmer",
            )
        )
