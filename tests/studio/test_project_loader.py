from __future__ import annotations

import json
import shutil

import pytest
from conftest import make_valid_project

from automatedub_studio.project.loader import ProjectLoadError, load_project
from automatedub_studio.project.models import Project, Segment


def test_load_project_succeeds_for_valid_project(tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=5)

    project = load_project(project_dir)

    assert isinstance(project, Project)
    assert project.project_path == project_dir
    assert project.audio_path == project_dir / "audio.wav"
    assert project.translation_path == project_dir / "translation.json"
    assert project.tts_directory == project_dir / "tts"
    assert project.video_path is None
    assert project.has_video is False
    assert project.segment_count == 5
    assert project.tts_file_count == 5
    assert all(isinstance(segment, Segment) for segment in project.segments)
    assert project.segments[0] == Segment(id=0, start=0.0, end=1.0, target_text="target 0")


def test_load_project_detects_video(tmp_path):
    project_dir = make_valid_project(tmp_path, with_video=True)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "video.mp4"
    assert project.has_video is True


def test_load_project_missing_audio(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "audio.wav").unlink()

    with pytest.raises(ProjectLoadError, match="audio.wav"):
        load_project(project_dir)


def test_load_project_missing_translation(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "translation.json").unlink()

    with pytest.raises(ProjectLoadError, match="translation.json"):
        load_project(project_dir)


def test_load_project_missing_tts_directory(tmp_path):
    project_dir = make_valid_project(tmp_path)
    shutil.rmtree(project_dir / "tts")

    with pytest.raises(ProjectLoadError, match="tts"):
        load_project(project_dir)


def test_load_project_empty_directory_reports_everything_missing(tmp_path):
    project_dir = tmp_path / "output"
    project_dir.mkdir()

    with pytest.raises(ProjectLoadError) as exc_info:
        load_project(project_dir)

    message = str(exc_info.value)
    assert "audio.wav" in message
    assert "translation.json" in message
    assert "tts" in message


def test_load_project_rejects_nonexistent_directory(tmp_path):
    with pytest.raises(ProjectLoadError):
        load_project(tmp_path / "does-not-exist")


def test_load_project_invalid_json(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "translation.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ProjectLoadError, match="not valid JSON"):
        load_project(project_dir)


def test_load_project_malformed_segment_missing_id(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "translation.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1, "target_text": "x"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectLoadError, match="integer id"):
        load_project(project_dir)


def test_load_project_malformed_segment_missing_target_text(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "translation.json").write_text(
        json.dumps({"segments": [{"id": 0, "start": 0, "end": 1}]}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectLoadError, match="target_text"):
        load_project(project_dir)


def test_load_project_translation_root_not_an_object(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "translation.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ProjectLoadError):
        load_project(project_dir)


def test_load_project_empty_tts_directory_does_not_fail(tmp_path):
    project_dir = make_valid_project(tmp_path, segment_count=2)
    for wav_file in (project_dir / "tts").glob("*.wav"):
        wav_file.unlink()

    project = load_project(project_dir)

    assert project.tts_file_count == 0
    assert project.segment_count == 2
