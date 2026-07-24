from __future__ import annotations

from pathlib import Path

from automatedub import cli
from automatedub.doctor import DoctorCheck
from automatedub.setup import SetupResult
from automatedub.vertical_slice.tts import TtsVoice


def test_dub_command_returns_success_and_prints_artifact_paths(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "movie.mp4"
    output_dir = tmp_path / "output"
    expected_audio = output_dir / "audio.wav"
    expected_transcript = output_dir / "transcript.json"
    expected_translation = output_dir / "translation.json"
    expected_prompt = output_dir / "translation_prompt.json"
    expected_tts_dir = output_dir / "tts"
    expected_mixed_audio = output_dir / "mixed_audio.wav"
    expected_mix_plan = output_dir / "mix_plan.json"

    def fake_run_dub(
        input_arg: Path,
        output_arg: Path,
        tool_config=None,
    ) -> cli.DubResult:
        assert input_arg == input_path
        assert output_arg == output_dir
        assert tool_config is None
        return cli.DubResult(
            audio_path=expected_audio,
            transcript_path=expected_transcript,
            translation_path=expected_translation,
            prompt_path=expected_prompt,
            tts_dir=expected_tts_dir,
            tts_generated_count=2,
            tts_failure_count=1,
            mix_result=cli.MixResult(
                mixed_audio_path=expected_mixed_audio,
                mix_plan_path=expected_mix_plan,
                mixed_segments=2,
                skipped_segments=1,
            ),
        )

    monkeypatch.setattr(cli, "run_dub", fake_run_dub)

    exit_code = cli.main(["dub", str(input_path), str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"audio extracted: {expected_audio}" in output
    assert f"transcript written: {expected_transcript}" in output
    assert f"translation prompt written: {expected_prompt}" in output
    assert f"translation written: {expected_translation}" in output
    assert f"tts written: {expected_tts_dir}" in output
    assert "tts segments generated: 2" in output
    assert "tts segments failed: 1" in output
    assert f"mixed audio written: {expected_mixed_audio}" in output
    assert f"mix plan written: {expected_mix_plan}" in output
    assert "mix segments included: 2" in output
    assert "mix segments skipped: 1" in output


def test_dub_command_returns_error_for_vs0_failure(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "movie.mp4"
    output_dir = tmp_path / "output"

    def fake_run_dub(
        input_arg: Path,
        output_arg: Path,
        tool_config=None,
    ) -> tuple[Path, Path, Path, Path, Path, int, int]:
        raise cli.VS0Error("ffmpeg is not available on PATH")

    monkeypatch.setattr(cli, "run_dub", fake_run_dub)

    exit_code = cli.main(["dub", str(input_path), str(output_dir)])

    assert exit_code == 2
    assert "error: ffmpeg is not available on PATH" in capsys.readouterr().err


def test_tts_command_returns_success_and_prints_counts(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"
    expected_tts_dir = output_dir / "tts"

    def fake_run_tts(output_arg: Path, tool_config=None) -> tuple[Path, int, int]:
        assert output_arg == output_dir
        assert tool_config is None
        return expected_tts_dir, 3, 1

    monkeypatch.setattr(cli, "run_tts", fake_run_tts)

    exit_code = cli.main(["tts", str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"tts written: {expected_tts_dir}" in output
    assert "tts segments generated: 3" in output
    assert "tts segments failed: 1" in output


def test_tts_providers_command_prints_status(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "get_tts_provider_status",
        lambda: cli.TtsProviderStatus(
            available_providers=["cambai", "nbwcode"],
            current_provider="cambai",
            current_model="mars-flash",
            current_voice="123",
        ),
    )

    exit_code = cli.main(["tts", "providers"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "available providers:" in output
    assert "- cambai" in output
    assert "- nbwcode" in output
    assert "current provider: cambai" in output
    assert "current model: mars-flash" in output
    assert "current voice: 123" in output


def test_camb_voices_command_prints_voices(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_tool_config", lambda: object())
    monkeypatch.setattr(
        cli,
        "list_cambai_voices",
        lambda config: [
            TtsVoice(
                id="123",
                name="Khmer Female",
                gender="female",
                language="km-kh",
                metadata={},
            )
        ],
    )

    exit_code = cli.main(["camb", "voices"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Voice ID\tVoice Name\tGender\tLanguage" in output
    assert "123\tKhmer Female\tfemale\tkm-kh * Khmer" in output


def test_camb_test_command_prints_one_wav_result(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"
    result = cli.CambTestResult(
        output_path=output_dir / "tts" / "test.wav",
        provider="cambai",
        model="mars-flash",
        voice="123",
        generation_time=1.25,
        characters=7,
    )
    monkeypatch.setattr(cli, "run_camb_test", lambda output_arg: result)

    exit_code = cli.main(["camb", "test", str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"test wav written: {result.output_path}" in output
    assert "provider: cambai" in output
    assert "model: mars-flash" in output
    assert "voice: 123" in output
    assert "generation time: 1.25" in output
    assert "characters: 7" in output


def test_mix_command_returns_success_and_prints_counts(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"
    expected_mixed_audio = output_dir / "mixed_audio.wav"
    expected_mix_plan = output_dir / "mix_plan.json"

    def fake_run_mix(output_arg: Path, tool_config=None) -> cli.MixResult:
        assert output_arg == output_dir
        assert tool_config is None
        return cli.MixResult(
            mixed_audio_path=expected_mixed_audio,
            mix_plan_path=expected_mix_plan,
            mixed_segments=3,
            skipped_segments=1,
        )

    monkeypatch.setattr(cli, "run_mix", fake_run_mix)

    exit_code = cli.main(["mix", str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"mixed audio written: {expected_mixed_audio}" in output
    assert f"mix plan written: {expected_mix_plan}" in output
    assert "mix segments included: 3" in output
    assert "mix segments skipped: 1" in output


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
