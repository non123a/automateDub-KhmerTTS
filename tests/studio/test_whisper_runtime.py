from __future__ import annotations

import io

import pytest

from automatedub_studio.runtime import whisper


@pytest.mark.parametrize(
    ("system", "filename"),
    [("windows", "whisper-cli.exe"), ("macos", "whisper-cli"), ("linux", "whisper-cli")],
)
def test_bundled_whisper_path_is_platform_specific(monkeypatch, tmp_path, system, filename):
    monkeypatch.setattr(whisper, "application_resource_directory", lambda: tmp_path)

    path = whisper.bundled_whisper_executable(system)

    assert path == tmp_path / "runtime" / "whisper" / system / filename


def test_whisper_resolution_requires_application_runtime_not_path(monkeypatch, tmp_path):
    monkeypatch.setattr(whisper, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/whisper-cli")

    with pytest.raises(whisper.WhisperRuntimeError, match="Bundled Whisper.cpp"):
        whisper.resolve_whisper_executable("linux")


def test_whisper_model_downloads_once(monkeypatch, tmp_path):
    calls = []

    class Response(io.BytesIO):
        headers = {"Content-Length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(_url, timeout):
        calls.append(timeout)
        return Response(b"model")

    monkeypatch.setattr(whisper.urllib.request, "urlopen", fake_urlopen)
    first = whisper.ensure_whisper_model(data_directory=tmp_path)
    second = whisper.ensure_whisper_model(data_directory=tmp_path)

    assert first == tmp_path / "models" / "ggml-small.bin"
    assert second == first
    assert first.read_bytes() == b"model"
    assert calls == [60]
