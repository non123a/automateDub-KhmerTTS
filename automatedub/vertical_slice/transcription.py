"""VS1 local transcription through a generic local transcriber boundary."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from automatedub import process
from automatedub.config import ToolConfig, resolve_executable


class VS1Error(RuntimeError):
    """Raised when the VS1 transcription step cannot complete."""


@dataclass(frozen=True)
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    edited_text: str | None = None


@dataclass(frozen=True)
class Transcript:
    version: int
    language: str
    source_audio: str
    engine: dict[str, str]
    text: str
    segments: list[TranscriptSegment]


class LocalTranscriber(Protocol):
    def transcribe(self, audio_path: Path, transcript_path: Path) -> Transcript:
        """Transcribe local audio into a transcript JSON file."""


class WhisperCppTranscriber:
    def __init__(self, tool_config: ToolConfig) -> None:
        self.tool_config = tool_config

    def transcribe(self, audio_path: Path, transcript_path: Path) -> Transcript:
        source = validate_audio_input(audio_path)
        binary = validate_whisper_cpp(self.tool_config)
        model = validate_model_path(self.tool_config.whisper_model_path)

        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="automatedub-whisper-") as temp_dir:
            output_base = Path(temp_dir) / "transcript"
            command = build_whisper_cpp_command(binary, model, source, output_base)
            run_whisper_cpp(command)
            raw_json_path = output_base.with_suffix(".json")
            raw_payload = read_raw_transcript(raw_json_path)

        transcript = normalize_whisper_cpp_payload(
            raw_payload=raw_payload,
            source_audio=source.name,
            model_path=model,
        )
        write_transcript(transcript_path, transcript)
        return transcript


def validate_audio_input(audio_path: Path) -> Path:
    resolved = audio_path.expanduser()
    if not resolved.exists():
        raise VS1Error(f"audio file does not exist: {audio_path}")
    if not resolved.is_file():
        raise VS1Error(f"audio path is not a file: {audio_path}")
    if resolved.suffix.lower() != ".wav":
        raise VS1Error(f"audio file must be a WAV: {audio_path}")
    return resolved


def validate_whisper_cpp(tool_config: ToolConfig) -> str:
    binary = resolve_executable(tool_config.whisper_cpp_path)
    if binary is None:
        raise VS1Error(
            "AutomateDub speech recognition runtime is unavailable. Please reinstall AutomateDub."
        )
    return binary


def validate_model_path(model_path: Path) -> Path:
    resolved = model_path.expanduser()
    if not resolved.exists():
        raise VS1Error(f"whisper.cpp model file does not exist: {model_path}")
    if not resolved.is_file():
        raise VS1Error(f"whisper.cpp model path is not a file: {model_path}")
    return resolved


def build_whisper_cpp_command(
    whisper_cpp: str,
    model_path: Path,
    audio_path: Path,
    output_base: Path,
) -> list[str]:
    return [
        whisper_cpp,
        "-m",
        str(model_path),
        "-f",
        str(audio_path),
        "-l",
        "zh",
        "-oj",
        "-of",
        str(output_base),
        "-np",
    ]


def run_whisper_cpp(command: list[str]) -> None:
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, **process.gui_subprocess_kwargs()
        )
    except subprocess.CalledProcessError as exc:
        if exc.returncode < 0 and "-ng" not in command:
            retry_command = [*command, "-ng"]
            try:
                subprocess.run(
                    retry_command,
                    check=True,
                    capture_output=True,
                    text=True,
                    **process.gui_subprocess_kwargs(),
                )
                return
            except subprocess.CalledProcessError as retry_exc:
                exc = retry_exc
        message = (
            exc.stderr.strip()
            or exc.stdout.strip()
            or f"whisper.cpp exited with {exc.returncode}"
        )
        raise VS1Error(f"transcription failed: {message}") from exc


def read_raw_transcript(raw_json_path: Path) -> dict[str, object]:
    if not raw_json_path.exists():
        raise VS1Error(f"transcription did not create expected JSON file: {raw_json_path}")
    try:
        with raw_json_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise VS1Error(f"transcription produced invalid JSON: {raw_json_path}") from exc
    if not isinstance(payload, dict):
        raise VS1Error("transcription JSON root must be an object")
    return payload


def normalize_whisper_cpp_payload(
    raw_payload: dict[str, object],
    source_audio: str,
    model_path: Path,
) -> Transcript:
    raw_segments = raw_payload.get("transcription")
    if not isinstance(raw_segments, list):
        raise VS1Error("whisper.cpp JSON does not contain a transcription segment list")

    segments: list[TranscriptSegment] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            continue
        start, end = extract_segment_times(raw_segment)
        text = str(raw_segment.get("text", "")).strip()
        if text:
            segments.append(TranscriptSegment(id=len(segments), start=start, end=end, text=text))

    full_text = " ".join(segment.text for segment in segments).strip()
    return Transcript(
        version=1,
        language="zh",
        source_audio=source_audio,
        engine={
            "provider": "local",
            "model": f"whisper.cpp:{model_path.name}",
        },
        text=full_text,
        segments=segments,
    )


def extract_segment_times(raw_segment: dict[str, object]) -> tuple[float, float]:
    offsets = raw_segment.get("offsets")
    if isinstance(offsets, dict):
        start = offsets.get("from")
        end = offsets.get("to")
        if isinstance(start, int | float) and isinstance(end, int | float):
            return round(float(start) / 1000.0, 3), round(float(end) / 1000.0, 3)

    timestamps = raw_segment.get("timestamps")
    if isinstance(timestamps, dict):
        start = parse_timestamp(str(timestamps.get("from", "0")))
        end = parse_timestamp(str(timestamps.get("to", "0")))
        return start, end

    start = raw_segment.get("start")
    end = raw_segment.get("end")
    if isinstance(start, int | float) and isinstance(end, int | float):
        return round(float(start), 3), round(float(end), 3)

    return 0.0, 0.0


def parse_timestamp(value: str) -> float:
    normalized = value.strip().replace(",", ".")
    parts = normalized.split(":")
    try:
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return round(hours * 3600 + minutes * 60 + seconds, 3)
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return round(minutes * 60 + seconds, 3)
        return round(float(normalized), 3)
    except ValueError:
        return 0.0


def transcript_to_json_dict(transcript: Transcript) -> dict[str, object]:
    return {
        "version": transcript.version,
        "language": transcript.language,
        "source_audio": transcript.source_audio,
        "engine": transcript.engine,
        "text": transcript.text,
        "segments": [_transcript_segment_to_json(segment) for segment in transcript.segments],
    }


def _transcript_segment_to_json(segment: TranscriptSegment) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": segment.id,
        "start": segment.start,
        "end": segment.end,
        "text": segment.text,
    }
    if segment.edited_text is not None:
        payload["edited_text"] = segment.edited_text
    return payload


def write_transcript(transcript_path: Path, transcript: Transcript) -> None:
    temp_path = transcript_path.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(transcript_to_json_dict(transcript), file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(transcript_path)
