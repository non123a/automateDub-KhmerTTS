from __future__ import annotations

from pathlib import Path

from automatedub import cli
from automatedub.config import DEFAULT_TTS_MODEL
from automatedub.doctor import DoctorCheck
from automatedub.setup import SetupResult
from automatedub.vertical_slice.tts import GeneratedSpeech, SampleSegment, TtsVoice


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
            current_model=DEFAULT_TTS_MODEL,
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
    assert f"current model: {DEFAULT_TTS_MODEL}" in output
    assert "current voice: 123" in output


def test_tts_sample_command_generates_sample_wavs(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"
    sample_dir = tmp_path / "sample"

    def fake_run_tts_sample(
        output_dir: Path,
        start_segment: int = 0,
        minutes: float = 2.0,
        sample_output_dir: Path | None = None,
        tool_config=None,
    ) -> cli.TtsSampleResult:
        assert output_dir == tmp_path / "output"
        assert start_segment == 4
        assert minutes == 1.5
        assert sample_output_dir == sample_dir
        assert tool_config is None
        return cli.TtsSampleResult(
            output_dir=sample_dir,
            sample_wav_path=sample_dir / "sample.wav",
            sample_text_path=sample_dir / "sample.txt",
            generated_count=3,
            characters=42,
        )

    monkeypatch.setattr(cli, "run_tts_sample", fake_run_tts_sample)

    exit_code = cli.main(
        [
            "tts",
            "sample",
            str(output_dir),
            "--start-segment",
            "4",
            "--minutes",
            "1.5",
            "--output",
            str(sample_dir),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"sample written: {sample_dir}" in output
    assert f"sample wav: {sample_dir / 'sample.wav'}" in output
    assert f"sample text: {sample_dir / 'sample.txt'}" in output
    assert "sample segments generated: 3" in output
    assert "sample characters: 42" in output


def test_run_tts_sample_writes_selected_segment_wavs_and_text(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    sample_dir = output_dir / "sample"
    selected = [
        SampleSegment(id=0, start=0.0, end=1.0, target_text="មួយ"),
        SampleSegment(id=2, start=1.0, end=2.0, target_text="ពីរ"),
    ]
    calls: list[str] = []

    class FakeProvider:
        def generate(self, text: str) -> GeneratedSpeech:
            calls.append(text)
            return GeneratedSpeech(audio=b"RIFF\x24\x00\x00\x00WAVEfmt ")

    def fake_select_sample_segments(translation_path, start_segment, minutes):
        assert translation_path == output_dir / "translation.json"
        assert start_segment == 0
        assert minutes == 2.0
        return selected

    concat_calls: list[tuple[str, list[Path], Path]] = []

    monkeypatch.setattr(cli, "select_sample_segments", fake_select_sample_segments)
    monkeypatch.setattr(cli, "create_tts_provider", lambda config: FakeProvider())
    monkeypatch.setattr(cli, "validate_sample_ffmpeg", lambda config: "ffmpeg")
    monkeypatch.setattr(
        cli,
        "concatenate_sample_wavs",
        lambda ffmpeg, wav_paths, sample_wav_path: concat_calls.append(
            (ffmpeg, wav_paths, sample_wav_path)
        ),
    )

    result = cli.run_tts_sample(output_dir, tool_config=object())

    assert result == cli.TtsSampleResult(
        output_dir=sample_dir,
        sample_wav_path=sample_dir / "sample.wav",
        sample_text_path=sample_dir / "sample.txt",
        generated_count=2,
        characters=6,
    )
    assert calls == ["មួយ", "ពីរ"]
    assert (sample_dir / "0000.wav").exists()
    assert (sample_dir / "0002.wav").exists()
    assert (sample_dir / "sample.txt").read_text(encoding="utf-8") == "មួយ\nពីរ\n"
    assert concat_calls == [
        (
            "ffmpeg",
            [sample_dir / "0000.wav", sample_dir / "0002.wav"],
            sample_dir / "sample.wav",
        )
    ]


def test_concatenate_sample_wavs_builds_ffmpeg_command(monkeypatch, tmp_path):
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    wav_paths = [sample_dir / "0000.wav", sample_dir / "0001.wav"]
    for wav_path in wav_paths:
        wav_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
    sample_wav_path = sample_dir / "sample.wav"
    commands: list[list[str]] = []

    def fake_run(command, check, capture_output, text):
        commands.append(command)
        sample_wav_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    cli.concatenate_sample_wavs("ffmpeg", wav_paths, sample_wav_path)

    assert commands == [
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            commands[0][10],
            "-c",
            "copy",
            str(sample_wav_path),
        ]
    ]
    assert sample_wav_path.exists()


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
        model=DEFAULT_TTS_MODEL,
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
    assert f"model: {DEFAULT_TTS_MODEL}" in output
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


def test_duration_report_command_returns_success_and_prints_ratios(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"
    expected_report_path = output_dir / "duration_report.json"

    def fake_run_duration_report(output_arg: Path) -> cli.DurationReportResult:
        assert output_arg == output_dir
        return cli.DurationReportResult(
            report_path=expected_report_path,
            generated_wav_count=3,
            average_ratio=0.77,
            minimum_ratio=0.1,
            maximum_ratio=1.2,
        )

    monkeypatch.setattr(cli, "run_duration_report", fake_run_duration_report)

    exit_code = cli.main(["duration-report", str(output_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert f"duration report written: {expected_report_path}" in output
    assert "segments measured: 3" in output
    assert "average ratio: 0.77" in output
    assert "minimum ratio: 0.1" in output
    assert "maximum ratio: 1.2" in output


def test_duration_report_command_reports_error(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "output"

    def fake_run_duration_report(output_arg: Path) -> cli.DurationReportResult:
        raise cli.DurationReportError("no synthesized speech WAV files were found")

    monkeypatch.setattr(cli, "run_duration_report", fake_run_duration_report)

    exit_code = cli.main(["duration-report", str(output_dir)])

    assert exit_code == 2
    error_output = capsys.readouterr().err
    assert "no synthesized speech WAV files were found" in error_output


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
        DoctorCheck("camb provider", True, "Camb.ai"),
        DoctorCheck("camb model", True, DEFAULT_TTS_MODEL),
        DoctorCheck("camb voice id", True, "170542"),
        DoctorCheck("camb language", True, "km-kh"),
        DoctorCheck("camb tts sync offset", True, "200 ms"),
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
    assert "=== Camb.ai ===" in output
    assert "Provider:\n✓ Camb.ai" in output
    assert f"Model:\n✓ {DEFAULT_TTS_MODEL}" in output
    assert "Voice ID:\n✓ 170542" in output
    assert "Language:\n✓ km-kh" in output
    assert "TTS Sync Offset:\n✓ 200 ms" in output


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
