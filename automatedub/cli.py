"""Command-line interface for the vertical-slice harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automatedub.config import ToolConfig, load_tool_config
from automatedub.doctor import doctor_succeeded, run_doctor
from automatedub.setup import SetupError, run_setup
from automatedub.vertical_slice.audio import VS0Error, extract_audio
from automatedub.vertical_slice.localization import NBWCodeDialogueLocalizer, VS2Error
from automatedub.vertical_slice.paths import (
    transcript_output_path,
    translation_output_path,
    translation_prompt_output_path,
    tts_output_dir_path,
)
from automatedub.vertical_slice.transcription import VS1Error, WhisperCppTranscriber
from automatedub.vertical_slice.tts import NBWCodeTextToSpeechSynthesizer, VS3Error


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
    tts_parser.add_argument("output_dir", type=Path, help="Directory containing translation.json.")

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
) -> tuple[Path, Path, Path, Path, Path, int, int]:
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
    return (
        audio_path,
        transcript_path,
        translation_path,
        prompt_path,
        tts_dir,
        tts_generated_count,
        tts_failure_count,
    )


def run_tts(
    output_dir: Path,
    tool_config: ToolConfig | None = None,
) -> tuple[Path, int, int]:
    config = tool_config or load_tool_config()
    translation_path = translation_output_path(output_dir.expanduser())
    tts_dir = tts_output_dir_path(output_dir.expanduser())
    synthesizer = NBWCodeTextToSpeechSynthesizer(config)
    tts_result = synthesizer.synthesize_segments(
        translation_path=translation_path,
        tts_dir=tts_dir,
    )
    return tts_result.tts_dir, len(tts_result.generated), len(tts_result.failures)


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
        try:
            tts_dir, tts_generated_count, tts_failure_count = run_tts(args.output_dir)
        except VS3Error as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"tts written: {tts_dir}")
        print(f"tts segments generated: {tts_generated_count}")
        print(f"tts segments failed: {tts_failure_count}")
        return 0

    if args.command == "dub":
        try:
            (
                audio_path,
                transcript_path,
                translation_path,
                prompt_path,
                tts_dir,
                tts_generated_count,
                tts_failure_count,
            ) = run_dub(args.input, args.output_dir)
        except (VS0Error, VS1Error, VS2Error, VS3Error) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(f"audio extracted: {audio_path}")
        print(f"transcript written: {transcript_path}")
        print(f"translation prompt written: {prompt_path}")
        print(f"translation written: {translation_path}")
        print(f"tts written: {tts_dir}")
        print(f"tts segments generated: {tts_generated_count}")
        print(f"tts segments failed: {tts_failure_count}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def print_doctor_checks(checks) -> None:
    general_checks = [check for check in checks if not check.name.startswith("nbw ")]
    nbw_checks = {check.name: check for check in checks if check.name.startswith("nbw ")}

    for check in general_checks:
        status = "ok" if check.ok else "error"
        print(f"{status}: {check.name}: {check.detail}")

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


def format_doctor_value(check) -> str:
    if check is None:
        return "✗ Missing"
    symbol = "✓" if check.ok else "✗"
    return f"{symbol} {check.detail}"
