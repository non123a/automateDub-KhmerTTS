from __future__ import annotations

import pytest

from automatedub import config, runtime


@pytest.mark.parametrize(
    ("system", "name"),
    [("windows", "ffprobe.exe"), ("macos", "ffprobe"), ("linux", "ffprobe")],
)
def test_ffprobe_packaged_path_is_platform_specific(monkeypatch, tmp_path, system, name):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)

    assert runtime.bundled_binary_path("ffprobe", system) == (
        tmp_path / "runtime" / "bin" / system / name
    )


def test_config_resolves_bundled_media_without_path(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    binary = tmp_path / "runtime" / "bin" / "windows" / "ffmpeg.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")

    assert config.resolve_executable("ffmpeg.exe") is None
    assert runtime.resolve_runtime_binary("ffmpeg", system="windows") == str(binary)


def test_missing_packaged_media_runtime_has_no_path_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path)
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/developer/ffmpeg")

    assert runtime.resolve_runtime_binary("ffprobe", system="linux") is None


def test_macos_frozen_runtime_resolves_frameworks_location(monkeypatch, tmp_path):
    executable = tmp_path / "AutomateDub.app" / "Contents" / "MacOS" / "AutomateDub Studio"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"app")
    binary = (
        tmp_path
        / "AutomateDub.app"
        / "Contents"
        / "Frameworks"
        / "runtime"
        / "bin"
        / "macos"
        / "ffmpeg"
    )
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", str(executable))
    monkeypatch.setattr(runtime, "application_resource_directory", lambda: tmp_path / "resources")

    assert runtime.resolve_runtime_binary("ffmpeg", system="macos") == str(binary)
