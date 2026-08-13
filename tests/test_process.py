from __future__ import annotations

import subprocess

from automatedub import process


def test_non_windows_gui_subprocess_kwargs_are_empty(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "darwin")

    assert process.gui_subprocess_kwargs() == {}


def test_windows_frozen_gui_subprocess_hides_console(monkeypatch):
    class StartupInfo:
        dwFlags = 0
        wShowWindow = 0

    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setattr(process.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        process.subprocess, "STARTUPINFO", StartupInfo, raising=False
    )
    monkeypatch.setattr(process.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(process.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(process.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    kwargs = process.gui_subprocess_kwargs()

    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags & 1
    assert kwargs["startupinfo"].wShowWindow == 0


def test_run_preserves_captured_output_and_command(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(process.subprocess, "run", fake_run)

    result = process.run(["ffprobe", "-version"], capture_output=True, text=True)

    assert result.stdout == "ok"
    assert captured["command"] == ["ffprobe", "-version"]
    assert captured["kwargs"]["capture_output"] is True


def test_popen_preserves_termination_interface(monkeypatch):
    class FakeProcess:
        def terminate(self):
            self.terminated = True

    child = FakeProcess()
    monkeypatch.setattr(process.subprocess, "Popen", lambda _command, **_kwargs: child)

    launched = process.popen(["ffmpeg", "-progress", "pipe:1"])
    launched.terminate()

    assert launched is child
    assert child.terminated is True
