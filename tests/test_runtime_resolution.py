from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from automatedub import config, runtime

_PACKAGING_MODULE = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "prepare_ffmpeg_runtime",
        Path(__file__).parents[1] / "packaging" / "prepare_ffmpeg_runtime.py",
    )
)
assert _PACKAGING_MODULE.__spec__ is not None
assert _PACKAGING_MODULE.__spec__.loader is not None
_PACKAGING_MODULE.__spec__.loader.exec_module(_PACKAGING_MODULE)
_resolve_windows_binary = _PACKAGING_MODULE._resolve_windows_binary
_windows_binary_candidates = _PACKAGING_MODULE._windows_binary_candidates
_contains_chocolatey_reference = _PACKAGING_MODULE._contains_chocolatey_reference
_clean_destination = _PACKAGING_MODULE._clean_destination


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


def test_windows_staging_searches_real_binary_below_chocolatey_shim(tmp_path):
    shim = tmp_path / "chocolatey" / "bin" / "ffmpeg.exe"
    real = (
        tmp_path
        / "chocolatey"
        / "lib"
        / "ffmpeg"
        / "tools"
        / "ffmpeg"
        / "bin"
        / "ffmpeg.exe"
    )
    real.parent.mkdir(parents=True)
    shim.parent.mkdir(parents=True)
    shim.write_bytes(b"shim")
    real.write_bytes(b"real")

    candidates = _windows_binary_candidates("ffmpeg", shim)

    assert candidates[-1] == shim
    assert real in candidates


def test_windows_staging_rejects_non_runnable_binary(monkeypatch, tmp_path):
    source = tmp_path / "bin" / "ffmpeg.exe"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"launcher reference")
    monkeypatch.setattr(_PACKAGING_MODULE, "_runs_without_path", lambda _path: False)

    with pytest.raises(RuntimeError, match="not a runnable native Windows"):
        _resolve_windows_binary("ffmpeg", source)


def test_windows_staging_rejects_chocolatey_reference(monkeypatch, tmp_path):
    source = tmp_path / "ffmpeg.exe"
    source.write_bytes(b"MZ ..\\lib\\ffmpeg\\tools\\ffmpeg\\bin\\ffmpeg.exe")
    monkeypatch.setattr(_PACKAGING_MODULE, "_runs_without_path", lambda _path: True)

    assert _contains_chocolatey_reference(source)
    with pytest.raises(RuntimeError, match="not a runnable native Windows"):
        _resolve_windows_binary("ffmpeg", source)


def test_windows_staging_cleans_stale_destination(tmp_path):
    destination = tmp_path / "runtime" / "bin" / "windows"
    stale = destination / "ffmpeg.exe"
    nested = destination / "lib" / "stale.dll"
    nested.parent.mkdir(parents=True)
    stale.write_bytes(b"shim")
    nested.write_bytes(b"stale")

    _clean_destination(destination)

    assert list(destination.iterdir()) == []
