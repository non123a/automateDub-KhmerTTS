"""Command-line interface for the vertical-slice harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automatedub.config import ToolConfig, load_tool_config
from automatedub.doctor import doctor_succeeded, run_doctor
from automatedub.setup import SetupError, run_setup
from automatedub.vertical_slice.audio import VS0Error, extract_audio
from automatedub.vertical_slice.paths import transcript_output_path
from automatedub.vertical_slice.transcription import VS1Error, WhisperCppTranscriber


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
) -> tuple[Path, Path]:
    config = tool_config or load_tool_config()
    audio_path = extract_audio(input_path=input_path, output_dir=output_dir, tool_config=config)
    transcript_path = transcript_output_path(output_dir.expanduser())
    transcriber = WhisperCppTranscriber(config)
    transcriber.transcribe(audio_path=audio_path, transcript_path=transcript_path)
    return audio_path, transcript_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        checks = run_doctor(load_tool_config())
        for check in checks:
            status = "ok" if check.ok else "error"
            print(f"{status}: {check.name}: {check.detail}")
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

    if args.command == "dub":
        try:
            audio_path, transcript_path = run_dub(args.input, args.output_dir)
        except (VS0Error, VS1Error) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(f"audio extracted: {audio_path}")
        print(f"transcript written: {transcript_path}")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
