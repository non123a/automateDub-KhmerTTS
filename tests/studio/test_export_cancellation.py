"""Regression coverage for non-blocking managed-export cancellation."""

from __future__ import annotations

import io
import subprocess
import time

import pytest

from automatedub_studio.backend import export_service
from automatedub_studio.backend.export_service import (
    ExportCancelledError,
    ExportProcessController,
    _run_ffmpeg_with_progress,
)


class _Process:
    def __init__(self, *, running: bool = True, stderr: str = "") -> None:
        self.returncode: int | None = None if running else 0
        self.stdout = io.StringIO()
        self.stderr = io.StringIO(stderr)
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired(["ffmpeg"], timeout)
        return self.returncode


def test_cancel_request_does_not_wait_for_the_process() -> None:
    child = _Process()
    controller = ExportProcessController()
    controller.register(child)  # type: ignore[arg-type]

    started = time.monotonic()
    assert controller.request_cancel() is True

    assert time.monotonic() - started < 0.1
    assert child.terminate_calls == 1
    assert child.wait_calls == 0
    assert controller.request_cancel() is False
    assert child.terminate_calls == 1


def test_cancel_before_process_registration_terminates_new_child() -> None:
    controller = ExportProcessController()
    controller.request_cancel()
    child = _Process()

    controller.register(child)  # type: ignore[arg-type]

    assert child.terminate_calls == 1
    assert child.wait_calls == 0


def test_cancellable_runner_escalates_from_terminate_to_kill(monkeypatch) -> None:
    child = _Process()
    monkeypatch.setattr(export_service.subprocess, "Popen", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(export_service, "FFMPEG_TERMINATE_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(export_service, "FFMPEG_KILL_GRACE_SECONDS", 0.1)

    with pytest.raises(ExportCancelledError):
        _run_ffmpeg_with_progress(["ffmpeg", "out.mp4"], None, lambda _progress: None, lambda: True)

    assert child.terminate_calls == 1
    assert child.kill_calls == 1
    assert child.wait_calls == 1


def test_cancellable_runner_drains_stderr_before_returning(monkeypatch) -> None:
    child = _Process(running=False, stderr="ffmpeg diagnostic\n" * 100)
    child.stdout = io.StringIO("progress=end\n")
    monkeypatch.setattr(export_service.subprocess, "Popen", lambda *_args, **_kwargs: child)

    result = _run_ffmpeg_with_progress(["ffmpeg", "out.mp4"], None, lambda _progress: None)

    assert "ffmpeg diagnostic" in result.stderr
    assert result.returncode == 0
