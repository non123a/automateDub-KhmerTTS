from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def cleanup_qt_widgets():
    """Flush multimedia teardown between tests.

    QMediaPlayer opens media asynchronously; leaving top-level widgets alive
    until Python shutdown lets queued FFmpeg callbacks outlive temp fixtures.
    """
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        widget.close()
        widget.deleteLater()
    app.processEvents()
    app.sendPostedEvents(None, 0)
    app.processEvents()


def make_valid_project(root: Path, segment_count: int = 3, with_video: bool = False) -> Path:
    """Build a minimal-but-valid AutomateDub output/ directory under `root`."""
    project_dir = root / "output"
    project_dir.mkdir()
    (project_dir / "audio.wav").write_bytes(b"RIFF....WAVEfmt ")

    tts_dir = project_dir / "tts"
    tts_dir.mkdir()

    segments = []
    for index in range(segment_count):
        segments.append(
            {
                "id": index,
                "start": float(index),
                "end": float(index) + 1.0,
                "source_language": "zh",
                "target_language": "km",
                "source_text": f"source {index}",
                "target_text": f"target {index}",
                "notes": None,
            }
        )
        (tts_dir / f"{index:04d}.wav").write_bytes(b"RIFF....WAVEfmt ")

    payload = {
        "version": 1,
        "source_transcript": "transcript.json",
        "prompt_artifact": "translation_prompt.json",
        "engine": {"provider": "openai-compatible", "model": "test-model"},
        "segments": segments,
    }
    (project_dir / "translation.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    if with_video:
        (project_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
        (project_dir / "project.json").write_text(
            json.dumps(
                {
                    "source_video": "video.mp4",
                    "editor_video": "video.mp4",
                    "source_codec": "h264",
                    "editor_codec": "h264",
                    "video_filename": "video.mp4",
                }
            ),
            encoding="utf-8",
        )

    return project_dir
