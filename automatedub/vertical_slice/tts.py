"""VS3 Khmer speech generation from localized dialogue segments."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from automatedub.config import ToolConfig

TTS_HTTP_TIMEOUT_SECONDS = 300
DEFAULT_TTS_VOICE = "alloy"


class VS3Error(RuntimeError):
    """Raised when the VS3 speech generation step cannot start."""


@dataclass(frozen=True)
class TtsSegment:
    id: int
    target_text: str


@dataclass(frozen=True)
class TtsFailure:
    id: int
    target_text: str
    error: str


@dataclass(frozen=True)
class TtsResult:
    tts_dir: Path
    generated: list[Path]
    failures: list[TtsFailure]


class TextToSpeechSynthesizer(Protocol):
    def synthesize_segments(self, translation_path: Path, tts_dir: Path) -> TtsResult:
        """Generate speech audio for all translated segments."""


class NBWCodeTextToSpeechSynthesizer:
    def __init__(self, tool_config: ToolConfig) -> None:
        self.tool_config = tool_config

    def synthesize_segments(self, translation_path: Path, tts_dir: Path) -> TtsResult:
        validate_tts_config(self.tool_config)
        segments = load_translation_segments(translation_path)
        tts_dir.mkdir(parents=True, exist_ok=True)

        generated: list[Path] = []
        failures: list[TtsFailure] = []
        for segment in segments:
            output_path = tts_segment_output_path(tts_dir, segment.id)
            try:
                audio = synthesize_nbwcode_speech(
                    base_url=self.tool_config.nbw_base_url,
                    api_key=self.tool_config.nbw_automatedub_api_key or "",
                    model=self.tool_config.tts_model,
                    text=segment.target_text,
                )
                validate_wav_audio(audio, segment.id)
                output_path.write_bytes(audio)
                generated.append(output_path)
            except Exception as exc:
                failures.append(
                    TtsFailure(id=segment.id, target_text=segment.target_text, error=str(exc))
                )

        write_tts_error_log(tts_dir, failures)
        return TtsResult(tts_dir=tts_dir, generated=generated, failures=failures)


def validate_tts_config(tool_config: ToolConfig) -> None:
    if tool_config.tts_provider != "nbwcode":
        raise VS3Error("TTS_PROVIDER must be nbwcode for VS3")
    if not tool_config.tts_model:
        raise VS3Error("TTS_MODEL is required for VS3")
    if not tool_config.nbw_automatedub_api_key:
        raise VS3Error("NBW_AUTOMATEDUB_API_KEY is required for VS3 speech generation")


def load_translation_segments(translation_path: Path) -> list[TtsSegment]:
    if not translation_path.exists():
        raise VS3Error(f"translation file does not exist: {translation_path}")
    try:
        payload = json.loads(translation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VS3Error(f"translation file is not valid JSON: {translation_path}") from exc

    if not isinstance(payload, dict):
        raise VS3Error("translation JSON root must be an object")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise VS3Error("translation JSON must contain a segments list")

    segments: list[TtsSegment] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise VS3Error("each translation segment must be an object")
        segment_id = raw_segment.get("id")
        target_text = raw_segment.get("target_text")
        if not isinstance(segment_id, int):
            raise VS3Error("each translation segment must contain integer id")
        if not isinstance(target_text, str) or not target_text.strip():
            raise VS3Error(f"translation segment {segment_id} is missing target_text")
        segments.append(TtsSegment(id=segment_id, target_text=target_text.strip()))
    return segments


def tts_segment_output_path(tts_dir: Path, segment_id: int) -> Path:
    return tts_dir / f"{segment_id:04d}.wav"


def build_speech_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/audio/speech"):
        return normalized
    return f"{normalized}/audio/speech"


def build_speech_payload(model: str, text: str) -> dict[str, object]:
    return {
        "model": model,
        "input": text,
        "voice": DEFAULT_TTS_VOICE,
        "response_format": "wav",
    }


def synthesize_nbwcode_speech(
    base_url: str,
    api_key: str,
    model: str,
    text: str,
) -> bytes:
    url = build_speech_url(base_url)
    payload = build_speech_payload(model=model, text=text)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TTS_HTTP_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise VS3Error(f"TTS request failed: HTTP {exc.code}: {body}") from exc
    except OSError as exc:
        raise VS3Error(f"TTS request failed: {exc}") from exc


def validate_wav_audio(audio: bytes, segment_id: int) -> None:
    if len(audio) < 12 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise VS3Error(f"TTS segment {segment_id} did not return WAV audio")


def write_tts_error_log(tts_dir: Path, failures: list[TtsFailure]) -> None:
    if not failures:
        return
    payload = {
        "version": 1,
        "failures": [
            {
                "id": failure.id,
                "target_text": failure.target_text,
                "error": failure.error,
            }
            for failure in failures
        ],
    }
    path = tts_dir / "errors.json"
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
