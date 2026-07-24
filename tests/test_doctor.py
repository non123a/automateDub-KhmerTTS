from __future__ import annotations

from pathlib import Path

from automatedub import doctor
from automatedub.config import ToolConfig


def test_run_doctor_reports_missing_tools_and_model(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "resolve_executable", lambda executable: None)
    monkeypatch.setattr(
        doctor,
        "check_nbw_status",
        lambda base_url, api_key, model: {
            "base_url": base_url,
            "api_key_present": False,
            "model": model,
            "endpoint": None,
            "authentication_valid": False,
            "connectivity_ok": False,
            "error": "NBW_AUTOMATEDUB_API_KEY is not set",
        },
    )

    checks = doctor.run_doctor(ToolConfig(whisper_model_path=tmp_path / "missing.bin"))

    assert doctor.doctor_succeeded(checks) is False
    assert [check.ok for check in checks] == [
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        True,
        False,
        False,
        False,
        True,
        True,
        False,
        True,
        True,
    ]


def test_run_doctor_reports_available_tools_and_model(monkeypatch, tmp_path):
    model = tmp_path / "ggml-small.bin"
    model.write_bytes(b"model")
    monkeypatch.setattr(doctor, "resolve_executable", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        doctor,
        "check_nbw_status",
        lambda base_url, api_key, model: {
            "base_url": base_url,
            "api_key_present": True,
            "model": model,
            "endpoint": "responses",
            "authentication_valid": True,
            "connectivity_ok": True,
            "error": None,
        },
    )

    checks = doctor.run_doctor(
        ToolConfig(
            whisper_model_path=model,
            nbw_base_url="https://gateway.example/v1",
            nbw_automatedub_api_key="test-key",
            localization_model="test-model",
            camb_voice_id="170542",
        )
    )

    assert doctor.doctor_succeeded(checks) is True
    assert [check.ok for check in checks] == [
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]


def test_check_model_rejects_directory(tmp_path):
    check = doctor.check_model(ToolConfig(whisper_model_path=Path(tmp_path)))

    assert check.ok is False
    assert "not a file" in check.detail
