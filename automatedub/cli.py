"""Command-line interface for the vertical-slice harness."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from automatedub.config import ToolConfig, load_tool_config, resolve_executable
from automatedub.doctor import doctor_succeeded, run_doctor
from automatedub.setup import SetupError, run_setup
from automatedub.vertical_slice.audio import VS0Error, extract_audio
from automatedub.vertical_slice.duration_report import (
    DurationReportError,
    DurationReportResult,  # noqa: F401  re-exported for test access via cli.DurationReportResult
    run_duration_report,
)
from automatedub.vertical_slice.localization import NBWCodeDialogueLocalizer, VS2Error
from automatedub.vertical_slice.mix import MixResult, VS4Error, run_mix
from automatedub.vertical_slice.paths import (
    transcript_output_path,
    translation_output_path,
    translation_prompt_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.transcription import VS1Error, WhisperCppTranscriber
from automatedub.vertical_slice.tts import (
    ProviderTextToSpeechSynthesizer,
    VS3Error,
    create_tts_provider,
    list_cambai_voices,
    select_sample_segments,
    tts_segment_output_path,
    validate_wav_audio,
)
from automatedub.vertical_slice.tts import (
    load_translation_segments as load_tts_translation_segments,
)
from automatedub.vertical_slice.tts_combine import (
    TtsCombineError,
    TtsCombineResult,  # noqa: F401  re-exported for test access via cli.TtsCombineResult
    run_tts_combine,
)


@dataclass(frozen=True)
class DubResult:
    audio_path: Path
    transcript_path: Path
    translation_path: Path
    prompt_path: Path
    tts_dir: Path
    tts_generated_count: int
    tts_failure_count: int
    mix_result: MixResult


@dataclass(frozen=True)
class TtsProviderStatus:
    available_providers: list[str]
    current_provider: str
    current_model: str
    current_voice: str | None


@dataclass(frozen=True)
class CambTestResult:
    output_path: Path
    provider: str
    model: str
    voice: str | None
    generation_time: float
    characters: int


@dataclass(frozen=True)
class TtsSampleResult:
    output_dir: Path
    sample_wav_path: Path
    sample_text_path: Path
    generated_count: int
    characters: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="automatedub",
        description="AutomateDub vertical-slice CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "doctor",
        help="Validate local tools and configuration for the current vertical slice.",
    )
    subparsers.add_parser(
        "setup",
        help="Prepare local tools and model files for the current vertical slice.",
    )
    tts_parser = subparsers.add_parser(
        "tts",
        help="Generate Khmer speech WAV files from an existing translation.json.",
    )
    tts_parser.add_argument(
        "target",
        nargs="?",
        help="Output directory containing translation.json, 'providers', 'sample', or 'combine'.",
    )
    tts_parser.add_argument(
        "sample_source_dir",
        nargs="?",
        type=Path,
        help=(
            "Output directory containing translation.json when using 'tts sample' or 'tts combine'."
        ),
    )
    tts_parser.add_argument(
        "--start-segment",
        type=int,
        default=0,
        help="First translated segment ID to include in a TTS sample.",
    )
    tts_parser.add_argument(
        "--minutes",
        type=float,
        default=2.0,
        help="Approximate translated timestamp duration to include in a TTS sample.",
    )
    tts_parser.add_argument(
        "--output",
        type=Path,
        help="Directory for sampled TTS WAV files. Defaults to <output_dir>/sample/.",
    )

    camb_parser = subparsers.add_parser(
        "camb",
        help="Camb.ai provider utilities.",
    )
    camb_subparsers = camb_parser.add_subparsers(dest="camb_command", required=True)
    camb_subparsers.add_parser("voices", help="List Camb.ai voices.")
    camb_test_parser = camb_subparsers.add_parser(
        "test",
        help="Generate one Camb.ai test WAV from the first translation segment.",
    )
    camb_test_parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=Path("output"),
        help="Directory containing translation.json. Defaults to output/.",
    )

    mix_parser = subparsers.add_parser(
        "mix",
        help="Mix generated Khmer speech with the extracted source audio.",
    )
    mix_parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory containing audio.wav, translation.json, and tts/*.wav.",
    )

    duration_report_parser = subparsers.add_parser(
        "duration-report",
        help="Compare translation segment timing windows to generated TTS WAV durations.",
    )
    duration_report_parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory containing translation.json and tts/*.wav.",
    )

    dub_parser = subparsers.add_parser(
        "dub",
        help="Run the current vertical slice for one MP4 input.",
    )
    dub_parser.add_argument("input", type=Path, help="Path to the source Chinese MP4 file.")
    dub_parser.add_argument("output_dir", type=Path, help="Directory for vertical-slice outputs.")

    return parser


def run_dub(
    input_path: Path,
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> DubResult:
    config = tool_config or load_tool_config()
    audio_path = extract_audio(input_path=input_path, output_dir=output_dir, tool_config=config)
    transcript_path = transcript_output_path(output_dir.expanduser())
    transcriber = WhisperCppTranscriber(config)
    transcriber.transcribe(audio_path=audio_path, transcript_path=transcript_path)
    translation_path = translation_output_path(output_dir.expanduser())
    prompt_path = translation_prompt_output_path(output_dir.expanduser())
    localizer = NBWCodeDialogueLocalizer(config)
    localizer.localize(
        transcript_path=transcript_path,
        translation_path=translation_path,
        prompt_path=prompt_path,
    )
    tts_dir, tts_generated_count, tts_failure_count = run_tts(output_dir, config)
    mix_result = run_mix(output_dir, config)
    return DubResult(
        audio_path=audio_path,
        transcript_path=transcript_path,
        translation_path=translation_path,
        prompt_path=prompt_path,
        tts_dir=tts_dir,
        tts_generated_count=tts_generated_count,
        tts_failure_count=tts_failure_count,
        mix_result=mix_result,
    )


def run_tts(
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> tuple[Path, int, int]:
    config = tool_config or load_tool_config()
    output_root = output_dir.expanduser()
    translation_path = translation_output_path(output_root)
    tts_dir = tts_output_dir_path(output_root)
    synthesizer = ProviderTextToSpeechSynthesizer(
        provider=create_tts_provider(config),
        output_dir=output_root,
    )
    tts_result = synthesizer.synthesize_segments(
        translation_path=translation_path,
        tts_dir=tts_dir,
    )
    return tts_result.tts_dir, len(tts_result.generated), len(tts_result.failures)


def run_tts_sample(
    output_dir: Path,
    start_segment: int = 0,
    minutes: float = 2.0,
    sample_output_dir: Path | None = None,
    tool_config: ToolConfig | None = None,
) -> TtsSampleResult:
    config = tool_config or load_tool_config()
    output_root = output_dir.expanduser()
    translation_path = translation_output_path(output_root)
    selected_segments = select_sample_segments(
        translation_path=translation_path,
        start_segment=start_segment,
        minutes=minutes,
    )
    sample_dir = (sample_output_dir or (output_root / "sample")).expanduser()
    sample_dir.mkdir(parents=True, exist_ok=True)

    provider = create_tts_provider(config)
    generated_count = 0
    characters = 0
    wav_paths: list[Path] = []
    target_texts: list[str] = []
    for segment in selected_segments:
        speech = provider.generate(segment.target_text)
        validate_wav_audio(speech.audio, segment.id)
        wav_path = tts_segment_output_path(sample_dir, segment.id)
        wav_path.write_bytes(speech.audio)
        wav_paths.append(wav_path)
        target_texts.append(segment.target_text)
        generated_count += 1
        characters += len(segment.target_text)

    sample_text_path = sample_dir / "sample.txt"
    sample_text_path.write_text("\n".join(target_texts) + "\n", encoding="utf-8")
    sample_wav_path = sample_dir / "sample.wav"
    concatenate_sample_wavs(
        ffmpeg=validate_sample_ffmpeg(config),
        wav_paths=wav_paths,
        sample_wav_path=sample_wav_path,
    )

    return TtsSampleResult(
        output_dir=sample_dir,
        sample_wav_path=sample_wav_path,
        sample_text_path=sample_text_path,
        generated_count=generated_count,
        characters=characters,
    )


def validate_sample_ffmpeg(tool_config: ToolConfig) -> str:
    ffmpeg = resolve_executable(tool_config.ffmpeg_path)
    if ffmpeg is None:
        raise VS3Error("AutomateDub media runtime is unavailable. Please reinstall AutomateDub.")
    return ffmpeg


def concatenate_sample_wavs(
    ffmpeg: str,
    wav_paths: list[Path],
    sample_wav_path: Path,
) -> None:
    if not wav_paths:
        raise VS3Error("no sample WAV files were generated")

    manifest_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=sample_wav_path.parent,
            prefix=".sample_concat_",
            suffix=".txt",
            delete=False,
        ) as manifest:
            manifest_path = Path(manifest.name)
            for wav_path in wav_paths:
                escaped_path = str(wav_path.resolve()).replace("'", "'\\''")
                manifest.write(f"file '{escaped_path}'\n")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest_path),
            "-c",
            "copy",
            str(sample_wav_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            message = (
                exc.stderr.strip()
                or exc.stdout.strip()
                or f"ffmpeg exited with {exc.returncode}"
            )
            raise VS3Error(f"sample concatenation failed: {message}") from exc
    finally:
        if manifest_path is not None:
            manifest_path.unlink(missing_ok=True)


def get_tts_provider_status(tool_config: ToolConfig | None = None) -> TtsProviderStatus:
    config = tool_config or load_tool_config()
    voice = config.camb_voice_id if config.tts_provider == "cambai" else "alloy"
    return TtsProviderStatus(
        available_providers=["cambai", "nbwcode"],
        current_provider=config.tts_provider,
        current_model=config.tts_model,
        current_voice=voice,
    )


def run_camb_test(
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> CambTestResult:
    config = tool_config or load_tool_config()
    if config.tts_provider != "cambai":
        config = ToolConfig(**{**config.__dict__, "tts_provider": "cambai"})
    output_root = output_dir.expanduser()
    translation_path = translation_output_path(output_root)
    tts_dir = tts_output_dir_path(output_root)
    segments = load_tts_translation_segments(translation_path)
    if not segments:
        raise VS3Error("translation JSON contains no segments")

    first_segment = segments[0]
    provider = create_tts_provider(config)
    started_at = time.monotonic()
    speech = provider.generate(first_segment.target_text)
    generation_time = round(time.monotonic() - started_at, 3)
    validate_wav_audio(speech.audio, first_segment.id)

    tts_dir.mkdir(parents=True, exist_ok=True)
    output_path = tts_dir / "test.wav"
    output_path.write_bytes(speech.audio)
    info = provider.describe()
    return CambTestResult(
        output_path=output_path,
        provider=info.provider,
        model=info.model,
        voice=info.voice_id,
        generation_time=generation_time,
        characters=len(first_segment.target_text),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        checks = run_doctor(load_tool_config())
        print_doctor_checks(checks)
        return 0 if doctor_succeeded(checks) else 2

    if args.command == "setup":
        try:
            result = run_setup(load_tool_config())
        except SetupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        action = "downloaded" if result.downloaded_model else "found"
        print(f"model {action}: {result.model_path}")
        for check in result.checks:
            print(f"ok: {check.name}: {check.detail}")
        return 0

    if args.command == "tts":
        if args.target == "providers":
            status = get_tts_provider_status()
            print("available providers:")
            for provider in status.available_providers:
                print(f"- {provider}")
            print(f"current provider: {status.current_provider}")
            print(f"current model: {status.current_model}")
            print(f"current voice: {status.current_voice or 'not set'}")
            return 0
        if args.target == "sample":
            if args.sample_source_dir is None:
                print("error: tts sample requires an output directory", file=sys.stderr)
                return 2
            try:
                sample_result = run_tts_sample(
                    output_dir=args.sample_source_dir,
                    start_segment=args.start_segment,
                    minutes=args.minutes,
                    sample_output_dir=args.output,
                )
            except VS3Error as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"sample written: {sample_result.output_dir}")
            print(f"sample wav: {sample_result.sample_wav_path}")
            print(f"sample text: {sample_result.sample_text_path}")
            print(f"sample segments generated: {sample_result.generated_count}")
            print(f"sample characters: {sample_result.characters}")
            return 0
        if args.target == "combine":
            if args.sample_source_dir is None:
                print("error: tts combine requires an output directory", file=sys.stderr)
                return 2
            try:
                combine_result = run_tts_combine(args.sample_source_dir)
            except TtsCombineError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"tts combined audio written: {combine_result.tts_combined_path}")
            print(f"tts combined plan written: {combine_result.tts_combined_plan_path}")
            print(f"tts combine segments included: {combine_result.included_segments}")
            print(f"tts combine segments skipped: {combine_result.skipped_segments}")
            return 0
        if args.target is None:
            print("error: tts requires an output directory or 'providers'", file=sys.stderr)
            return 2
        try:
            tts_dir, tts_generated_count, tts_failure_count = run_tts(Path(args.target))
        except VS3Error as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"tts written: {tts_dir}")
        print(f"tts segments generated: {tts_generated_count}")
        print(f"tts segments failed: {tts_failure_count}")
        return 0

    if args.command == "camb":
        if args.camb_command == "voices":
            try:
                voices = list_cambai_voices(load_tool_config())
            except VS3Error as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print("Voice ID\tVoice Name\tGender\tLanguage")
            for voice in voices:
                marker = " * Khmer" if (voice.language or "").lower() in {"km", "km-kh"} else ""
                print(
                    f"{voice.id}\t{voice.name or 'unknown'}\t"
                    f"{voice.gender or 'unknown'}\t{voice.language or 'unknown'}{marker}"
                )
            return 0
        if args.camb_command == "test":
            try:
                result = run_camb_test(args.output_dir)
            except VS3Error as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"test wav written: {result.output_path}")
            print(f"provider: {result.provider}")
            print(f"model: {result.model}")
            print(f"voice: {result.voice or 'not set'}")
            print(f"generation time: {result.generation_time}")
            print(f"characters: {result.characters}")
            return 0

    if args.command == "mix":
        try:
            mix_result = run_mix(args.output_dir)
        except VS4Error as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"mixed audio written: {mix_result.mixed_audio_path}")
        print(f"mix plan written: {mix_result.mix_plan_path}")
        print(f"mix segments included: {mix_result.mixed_segments}")
        print(f"mix segments skipped: {mix_result.skipped_segments}")
        return 0

    if args.command == "duration-report":
        try:
            report_result = run_duration_report(args.output_dir)
        except DurationReportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"duration report written: {report_result.report_path}")
        print(f"segments measured: {report_result.generated_wav_count}")
        print(f"average ratio: {report_result.average_ratio}")
        print(f"minimum ratio: {report_result.minimum_ratio}")
        print(f"maximum ratio: {report_result.maximum_ratio}")
        return 0

    if args.command == "dub":
        try:
            dub_result = run_dub(args.input, args.output_dir)
        except (VS0Error, VS1Error, VS2Error, VS3Error, VS4Error) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(f"audio extracted: {dub_result.audio_path}")
        print(f"transcript written: {dub_result.transcript_path}")
        print(f"translation prompt written: {dub_result.prompt_path}")
        print(f"translation written: {dub_result.translation_path}")
        print(f"tts written: {dub_result.tts_dir}")
        print(f"tts segments generated: {dub_result.tts_generated_count}")
        print(f"tts segments failed: {dub_result.tts_failure_count}")
        print(f"mixed audio written: {dub_result.mix_result.mixed_audio_path}")
        print(f"mix plan written: {dub_result.mix_result.mix_plan_path}")
        print(f"mix segments included: {dub_result.mix_result.mixed_segments}")
        print(f"mix segments skipped: {dub_result.mix_result.skipped_segments}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def print_doctor_checks(checks) -> None:
    general_checks = [
        check
        for check in checks
        if not check.name.startswith("nbw ")
        and not check.name.startswith("camb ")
        and check.name != "tts speed"
    ]
    tts_speed_check = next((check for check in checks if check.name == "tts speed"), None)
    nbw_checks = {check.name: check for check in checks if check.name.startswith("nbw ")}
    camb_checks = {check.name: check for check in checks if check.name.startswith("camb ")}

    for check in general_checks:
        status = "ok" if check.ok else "error"
        print(f"{status}: {check.name}: {check.detail}")

    if tts_speed_check is not None:
        print()
        print("TTS Speed:")
        print(format_doctor_value(tts_speed_check))

    if nbw_checks:
        print()
        print("=== NBWCode ===")
        print()
        print("Base URL:")
        print(format_doctor_value(nbw_checks.get("nbw base url")))
        print()
        print("API Key:")
        print(format_doctor_value(nbw_checks.get("nbw api key")))
        print()
        print("Model:")
        print(format_doctor_value(nbw_checks.get("nbw model")))
        print()
        print("Endpoint:")
        print(format_doctor_value(nbw_checks.get("nbw endpoint")))
        print()
        print("Authentication:")
        print(format_doctor_value(nbw_checks.get("nbw authentication")))
        print()
        print("Connectivity:")
        print(format_doctor_value(nbw_checks.get("nbw connectivity")))

    if camb_checks:
        print()
        print("=== Camb.ai ===")
        print()
        print("Provider:")
        print(format_doctor_value(camb_checks.get("camb provider")))
        print()
        print("Model:")
        print(format_doctor_value(camb_checks.get("camb model")))
        print()
        print("Voice ID:")
        print(format_doctor_value(camb_checks.get("camb voice id")))
        print()
        print("Language:")
        print(format_doctor_value(camb_checks.get("camb language")))
        print()
        print("TTS Sync Offset:")
        print(format_doctor_value(camb_checks.get("camb tts sync offset")))


def format_doctor_value(check) -> str:
    if check is None:
        return "✗ Missing"
    symbol = "✓" if check.ok else "✗"
    return f"{symbol} {check.detail}"
