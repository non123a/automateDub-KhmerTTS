from __future__ import annotations

import io

import pytest

from automatedub import runtime
from automatedub_studio.runtime import whisper


@pytest.mark.parametrize(
    ("system", "filename"),
    [("windows", "whisper-cli.exe"), ("macos", "whisper-cli"), ("linux", "whisper-cli")],
)
def test_bundled_whisper_path_is_platform_specific(monkeypatch, tmp_path, system, filename):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)

    path = whisper.bundled_whisper_executable(system)

    assert path == tmp_path / "runtime" / "whisper" / system / filename


def test_whisper_resolution_requires_application_runtime_not_path(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/whisper-cli")

    with pytest.raises(whisper.WhisperRuntimeError, match="Bundled Whisper.cpp"):
        whisper.resolve_whisper_executable("linux")


def test_whisper_resolution_uses_macos_frameworks_runtime(monkeypatch, tmp_path):
    executable = tmp_path / "AutomateDub.app" / "Contents" / "MacOS" / "AutomateDub Studio"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"app")
    bundled = (
        tmp_path
        / "AutomateDub.app"
        / "Contents"
        / "Frameworks"
        / "runtime"
        / "whisper"
        / "macos"
        / "whisper-cli"
    )
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"binary")
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", str(executable))
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path / "resources")

    assert whisper.resolve_whisper_executable("macos") == bundled


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


@pytest.mark.parametrize("system", ("windows", "macos", "linux"))
def test_packaged_runtime_does_not_fall_back_to_path(monkeypatch, tmp_path, system):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/developer/path/ffmpeg")

    assert runtime.resolve_runtime_binary("ffmpeg", system=system) is None


@pytest.mark.parametrize(
    ("system", "filename"),
    [("windows", "ffmpeg.exe"), ("macos", "ffmpeg"), ("linux", "ffmpeg")],
)
def test_packaged_runtime_resolves_bundled_media_binary(monkeypatch, tmp_path, system, filename):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    binary = tmp_path / "runtime" / "bin" / system / filename
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")

    assert runtime.resolve_runtime_binary("ffmpeg", system=system) == str(binary)


def test_development_runtime_prefers_configured_path(monkeypatch, tmp_path):
    executable = tmp_path / "custom-ffmpeg"
    executable.write_bytes(b"binary")
    monkeypatch.delattr(runtime.sys, "frozen", raising=False)

    assert runtime.resolve_runtime_binary("ffmpeg", str(executable)) == str(executable)
