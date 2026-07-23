from __future__ import annotations

from pathlib import Path

from automatedub import doctor
from automatedub.config import ToolConfig


def test_run_doctor_reports_missing_tools_and_model(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "resolve_executable", lambda executable: None)

    checks = doctor.run_doctor(ToolConfig(whisper_model_path=tmp_path / "missing.bin"))

    assert doctor.doctor_succeeded(checks) is False
    assert [check.ok for check in checks] == [False, False, False, False, False]


def test_run_doctor_reports_available_tools_and_model(monkeypatch, tmp_path):
    model = tmp_path / "ggml-small.bin"
    model.write_bytes(b"model")
    monkeypatch.setattr(doctor, "resolve_executable", lambda executable: f"/usr/bin/{executable}")

    checks = doctor.run_doctor(ToolConfig(whisper_model_path=model))

    assert doctor.doctor_succeeded(checks) is True
    assert [check.ok for check in checks] == [True, True, True, True, True]


def test_check_model_rejects_directory(tmp_path):
    check = doctor.check_model(ToolConfig(whisper_model_path=Path(tmp_path)))

    assert check.ok is False
    assert "not a file" in check.detail
