from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from automatedub.config import ToolConfig
from automatedub_studio.project import video_proxy
from automatedub_studio.project.video_proxy import (
    EDITOR_PROXY_CODEC,
    PROXY_VIDEO_FILENAME,
    VideoProbe,
    prepare_editor_video,
    proxy_video_path,
    requires_proxy,
)


def _touch(path: Path, mtime: int) -> None:
    path.write_bytes(b"video")
    path.touch()
    os.utime(path, (mtime, mtime))


def test_av1_detection_requires_proxy():
    assert requires_proxy(VideoProbe(codec="av1", width=1920, height=1080, fps="30/1"))
    assert not requires_proxy(VideoProbe(codec="h264", width=1920, height=1080, fps="30/1"))


def test_existing_proxy_reuse(monkeypatch, tmp_path):
    source = tmp_path / "videoplayback3.mp4"
    proxy = proxy_video_path(tmp_path)
    _touch(source, 100)
    _touch(proxy, 200)
    monkeypatch.setattr(video_proxy, "resolve_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        video_proxy,
        "probe_video",
        lambda ffprobe, path: VideoProbe("av1", 1920, 1080, "30/1"),
    )
    calls = []
    monkeypatch.setattr(video_proxy.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    result = prepare_editor_video(tmp_path, source, ToolConfig())

    assert result.editor_video == proxy
    assert result.proxy_reused is True
    assert result.proxy_generated is False
    assert calls == []


def test_proxy_regeneration_after_source_changes(monkeypatch, tmp_path):
    source = tmp_path / "videoplayback3.mp4"
    proxy = proxy_video_path(tmp_path)
    _touch(source, 300)
    _touch(proxy, 100)
    monkeypatch.setattr(video_proxy, "resolve_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        video_proxy,
        "probe_video",
        lambda ffprobe, path: VideoProbe("av1", 1920, 1080, "30/1"),
    )
    commands = []

    def fake_run(command, check, capture_output, text):
        commands.append(command)
        proxy.write_bytes(b"proxy")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(video_proxy.subprocess, "run", fake_run)

    result = prepare_editor_video(tmp_path, source, ToolConfig())

    assert result.editor_video == proxy
    assert result.proxy_generated is True
    assert commands[0][commands[0].index("-c:v") + 1] == "libx264"
    assert commands[0][commands[0].index("-pix_fmt") + 1] == "yuv420p"
    assert commands[0][commands[0].index("-c:a") + 1] == "copy"


def test_h264_source_bypasses_proxy_generation(monkeypatch, tmp_path):
    source = tmp_path / "movie.mp4"
    _touch(source, 100)
    monkeypatch.setattr(video_proxy, "resolve_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        video_proxy,
        "probe_video",
        lambda ffprobe, path: VideoProbe("h264", 1280, 720, "24000/1001"),
    )
    calls = []
    monkeypatch.setattr(video_proxy.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    result = prepare_editor_video(tmp_path, source, ToolConfig())

    assert result.source_video == source
    assert result.editor_video == source
    assert result.proxy_required is False
    assert calls == []


def test_project_json_metadata_records_source_and_editor_video(monkeypatch, tmp_path):
    source = tmp_path / "videoplayback3.mp4"
    _touch(source, 100)
    monkeypatch.setattr(video_proxy, "resolve_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        video_proxy,
        "probe_video",
        lambda ffprobe, path: VideoProbe("av1", 1920, 1080, "30/1"),
    )

    def fake_run(command, check, capture_output, text):
        (tmp_path / PROXY_VIDEO_FILENAME).write_bytes(b"proxy")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(video_proxy.subprocess, "run", fake_run)

    result = prepare_editor_video(tmp_path, source, ToolConfig())

    metadata = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert metadata["source_video"] == "videoplayback3.mp4"
    assert metadata["editor_video"] == PROXY_VIDEO_FILENAME
    assert metadata["source_codec"] == "av1"
    assert metadata["editor_codec"] == EDITOR_PROXY_CODEC == "h264"
    assert result.editor_video == tmp_path / PROXY_VIDEO_FILENAME
