from __future__ import annotations

from pathlib import Path

from automatedub import cli
from automatedub.doctor import DoctorCheck
from automatedub.setup import SetupResult


def test_dub_command_returns_success_and_prints_artifact_paths(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "movie.mp4"
    output_dir = tmp_path / "output"
    expected_audio = output_dir / "audio.wav"
    expected_transcript = output_dir / "transcript.json"
    expected_translation = output_dir / "translation.json"
    expected_prompt = output_dir / "translation_prompt.json"

    def fake_run_dub(
        input_arg: Path,
        output_arg: Path,
        tool_config=None,
    ) -> tuple[Path, Path, Path, Path]:
        assert input_arg == input_path
        assert output_arg == output_dir
        assert tool_config is None
        return expected_audio, expected_transcript, expected_translation, expected_prompt

    monkeypatch.setattr(cli, "run_dub", fake_run_dub)

    exit_code = cli.main(["dub", str(input_path), str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"audio extracted: {expected_audio}" in output
    assert f"transcript written: {expected_transcript}" in output
    assert f"translation prompt written: {expected_prompt}" in output
    assert f"translation written: {expected_translation}" in output


def test_dub_command_returns_error_for_vs0_failure(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "movie.mp4"
    output_dir = tmp_path / "output"

    def fake_run_dub(
        input_arg: Path,
        output_arg: Path,
        tool_config=None,
    ) -> tuple[Path, Path, Path, Path]:
        raise cli.VS0Error("ffmpeg is not available on PATH")

    monkeypatch.setattr(cli, "run_dub", fake_run_dub)

    exit_code = cli.main(["dub", str(input_path), str(output_dir)])

    assert exit_code == 2
    assert "error: ffmpeg is not available on PATH" in capsys.readouterr().err


def test_doctor_command_prints_checks(monkeypatch, capsys):
    checks = [
        DoctorCheck("ffmpeg", True, "/usr/bin/ffmpeg"),
        DoctorCheck("whisper model", False, "not found"),
        DoctorCheck("nbw base url", True, "https://www.nbwcode.top/v1"),
        DoctorCheck("nbw api key", True, "Present"),
        DoctorCheck("nbw model", True, "gpt-5.5"),
        DoctorCheck("nbw endpoint", True, "Responses"),
        DoctorCheck("nbw authentication", True, "Valid"),
        DoctorCheck("nbw connectivity", True, "OK"),
    ]
    monkeypatch.setattr(cli, "run_doctor", lambda config: checks)
    monkeypatch.setattr(cli, "doctor_succeeded", lambda doctor_checks: False)

    exit_code = cli.main(["doctor"])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "ok: ffmpeg: /usr/bin/ffmpeg" in output
    assert "error: whisper model: not found" in output
    assert "=== NBWCode ===" in output
    assert "Base URL:\n✓ https://www.nbwcode.top/v1" in output
    assert "API Key:\n✓ Present" in output
    assert "Model:\n✓ gpt-5.5" in output
    assert "Endpoint:\n✓ Responses" in output
    assert "Authentication:\n✓ Valid" in output
    assert "Connectivity:\n✓ OK" in output


def test_setup_command_prints_result(monkeypatch, tmp_path, capsys):
    checks = [DoctorCheck("ffmpeg", True, "/usr/bin/ffmpeg")]
    result = SetupResult(
        model_path=tmp_path / "ggml-small.bin",
        downloaded_model=True,
        checks=checks,
    )
    monkeypatch.setattr(cli, "run_setup", lambda config: result)

    exit_code = cli.main(["setup"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"model downloaded: {result.model_path}" in output
    assert "ok: ffmpeg: /usr/bin/ffmpeg" in output


def test_setup_command_returns_error(monkeypatch, capsys):
    def fail_setup(config):
        raise cli.SetupError("homebrew is required")

    monkeypatch.setattr(cli, "run_setup", fail_setup)

    exit_code = cli.main(["setup"])

    assert exit_code == 2
    assert "error: homebrew is required" in capsys.readouterr().err
