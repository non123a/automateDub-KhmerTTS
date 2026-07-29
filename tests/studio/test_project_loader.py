from __future__ import annotations

import json
import shutil

import pytest
from conftest import make_valid_project

from automatedub_studio.project.loader import (
    PROJECT_METADATA_FILENAME,
    ProjectLoadError,
    load_project,
    save_video_selection,
)
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
    assert project.segments[0] == Segment(
        id=0, start=0.0, end=1.0, source_text="source 0", target_text="target 0"
    )


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


_VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42"


def test_video_discovery_single_mp4(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.mp4").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.mp4"
    assert project.has_video is True
    assert project.video_candidates == []


def test_video_discovery_arbitrary_mp4_filename(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "videoplayback3.mp4").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "videoplayback3.mp4"
    assert project.has_video is True
    assert project.video_candidates == []


def test_video_discovery_movie_mp4_filename(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "movie.mp4").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "movie.mp4"
    assert project.has_video is True
    assert project.video_candidates == []


def test_video_discovery_single_mov(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.mov").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.mov"
    assert project.has_video is True


def test_project_metadata_video_takes_precedence(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "alpha.mp4").write_bytes(_VIDEO_BYTES)
    (project_dir / "clip.mov").write_bytes(_VIDEO_BYTES)
    (project_dir / PROJECT_METADATA_FILENAME).write_text(
        json.dumps({"video_filename": "clip.mov"}), encoding="utf-8"
    )

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.mov"
    assert project.has_video is True
    assert project.video_candidates == []


def test_video_discovery_single_mkv(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.mkv").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.mkv"
    assert project.has_video is True


def test_video_discovery_single_avi(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.avi").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.avi"
    assert project.has_video is True


def test_video_discovery_single_webm(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.webm").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.webm"
    assert project.has_video is True


def test_video_discovery_mixed_case_extension(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "clip.MOV").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path == project_dir / "clip.MOV"
    assert project.has_video is True


def test_video_discovery_zero_videos(tmp_path):
    project_dir = make_valid_project(tmp_path)

    project = load_project(project_dir)

    assert project.video_path is None
    assert project.has_video is False
    assert project.video_candidates == []


def test_video_discovery_multiple_videos_no_selection(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "alpha.mp4").write_bytes(_VIDEO_BYTES)
    (project_dir / "beta.mp4").write_bytes(_VIDEO_BYTES)

    project = load_project(project_dir)

    assert project.video_path is None
    assert project.has_video is False
    assert len(project.video_candidates) == 2
    assert project_dir / "alpha.mp4" in project.video_candidates
    assert project_dir / "beta.mp4" in project.video_candidates


def test_video_discovery_multiple_videos_with_saved_selection(tmp_path):
    project_dir = make_valid_project(tmp_path)
    (project_dir / "alpha.mp4").write_bytes(_VIDEO_BYTES)
    (project_dir / "beta.mp4").write_bytes(_VIDEO_BYTES)
    save_video_selection(project_dir, project_dir / "beta.mp4")

    project = load_project(project_dir)

    assert project.video_path == project_dir / "beta.mp4"
    assert project.has_video is True
    assert project.video_candidates == []
    assert json.loads((project_dir / PROJECT_METADATA_FILENAME).read_text()) == {
        "source_video": "beta.mp4",
        "video_filename": "beta.mp4",
    }


def test_video_discovery_legacy_filenames(tmp_path):
    for i, name in enumerate(("video.mp4", "movie.mp4", "input.mp4")):
        root = tmp_path / f"proj{i}"
        root.mkdir()
        project_dir = make_valid_project(root)
        (project_dir / name).write_bytes(_VIDEO_BYTES)

        project = load_project(project_dir)

        assert project.video_path == project_dir / name
        assert project.has_video is True
