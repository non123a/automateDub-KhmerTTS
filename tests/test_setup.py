from __future__ import annotations

import hashlib

import pytest

from automatedub import setup
from automatedub.config import ToolConfig
from automatedub.doctor import DoctorCheck


def test_run_setup_downloads_missing_model_and_runs_doctor(monkeypatch, tmp_path):
    model_path = tmp_path / "models" / "ggml-small.bin"
    monkeypatch.setattr(setup, "resolve_executable", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(setup, "verify_model_checksum", lambda path: None)
    monkeypatch.setattr(
        setup,
        "run_doctor",
        lambda config: [DoctorCheck("ffmpeg", True, "/usr/bin/ffmpeg")],
    )

    def fake_download(url, destination):
        destination.write_bytes(b"model")

    result = setup.run_setup(ToolConfig(whisper_model_path=model_path), download_file=fake_download)

    assert result.downloaded_model is True
    assert result.model_path == model_path
    assert model_path.read_bytes() == b"model"


def test_run_setup_reuses_existing_model(monkeypatch, tmp_path):
    model_path = tmp_path / "models" / "ggml-small.bin"
    model_path.parent.mkdir()
    model_path.write_bytes(b"model")
    monkeypatch.setattr(setup, "resolve_executable", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(setup, "verify_model_checksum", lambda path: None)
    monkeypatch.setattr(
        setup,
        "run_doctor",
        lambda config: [DoctorCheck("ffmpeg", True, "/usr/bin/ffmpeg")],
    )

    result = setup.run_setup(ToolConfig(whisper_model_path=model_path))

    assert result.downloaded_model is False
    assert result.model_path == model_path


def test_run_setup_fails_when_required_tool_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "resolve_executable", lambda executable: None)

    with pytest.raises(setup.SetupError, match="homebrew is required"):
        setup.run_setup(ToolConfig(whisper_model_path=tmp_path / "model.bin"))


def test_verify_model_checksum_reports_mismatch(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"wrong")
    actual = hashlib.sha256(b"wrong").hexdigest()

    with pytest.raises(setup.SetupError, match=actual):
        setup.verify_model_checksum(model)


def test_sha256_file(tmp_path):
    model = tmp_path / "model.bin"
    model.write_bytes(b"abc")

    assert setup.sha256_file(model) == hashlib.sha256(b"abc").hexdigest()
