"""VS3 Khmer speech generation from localized dialogue segments."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from automatedub.config import ToolConfig
from automatedub.vertical_slice.paths import tts_usage_output_path

TTS_HTTP_TIMEOUT_SECONDS = 300
DEFAULT_TTS_VOICE = "alloy"


class VS3Error(RuntimeError):
    """Raised when the VS3 speech generation step cannot start."""


@dataclass(frozen=True)
class TtsSegment:
    id: int
    target_text: str


@dataclass(frozen=True)
class SampleSegment:
    id: int
    start: float
    end: float
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
    usage_path: Path | None = None


@dataclass(frozen=True)
class TtsProviderInfo:
    provider: str
    model: str
    voice_id: str | None
    voice_name: str | None = None
    language: str | None = None
    speed: float | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class GeneratedSpeech:
    audio: bytes
    metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class TtsUsage:
    provider: str
    model: str
    voice_id: str | None
    segments_processed: int
    characters_processed: int
    generation_time: float
    provider_metadata: dict[str, object]


@dataclass(frozen=True)
class TtsVoice:
    id: str
    name: str
    gender: str | None
    language: str | None
    metadata: dict[str, object]


class TTSProvider(Protocol):
    def describe(self) -> TtsProviderInfo:
        """Return configured provider metadata for display and usage logs."""

    def generate(self, text: str) -> GeneratedSpeech:
        """Generate a WAV audio payload for one text segment."""


class TextToSpeechSynthesizer(Protocol):
    def synthesize_segments(self, translation_path: Path, tts_dir: Path) -> TtsResult:
        """Generate speech audio for all translated segments."""


class ProviderTextToSpeechSynthesizer:
    def __init__(self, provider: TTSProvider, output_dir: Path | None = None) -> None:
        self.provider = provider
        self.output_dir = output_dir

    def synthesize_segments(self, translation_path: Path, tts_dir: Path) -> TtsResult:
        segments = load_translation_segments(translation_path)
        tts_dir.mkdir(parents=True, exist_ok=True)

        generated: list[Path] = []
        failures: list[TtsFailure] = []
        provider_metadata: dict[str, object] = {}
        started_at = time.monotonic()
        characters_processed = 0
        for segment in segments:
            output_path = tts_segment_output_path(tts_dir, segment.id)
            characters_processed += len(segment.target_text)
            try:
                speech = self.provider.generate(segment.target_text)
                validate_wav_audio(speech.audio, segment.id)
                output_path.write_bytes(speech.audio)
                generated.append(output_path)
                if speech.metadata:
                    provider_metadata[str(segment.id)] = speech.metadata
            except Exception as exc:
                failures.append(
                    TtsFailure(id=segment.id, target_text=segment.target_text, error=str(exc))
                )

        write_tts_error_log(tts_dir, failures)
        generation_time = round(time.monotonic() - started_at, 3)
        usage_path = None
        if self.output_dir is not None:
            usage = build_tts_usage(
                provider_info=self.provider.describe(),
                segments_processed=len(segments),
                characters_processed=characters_processed,
                generation_time=generation_time,
                provider_metadata=provider_metadata,
            )
            usage_path = write_tts_usage(self.output_dir, usage)

        return TtsResult(
            tts_dir=tts_dir,
            generated=generated,
            failures=failures,
            usage_path=usage_path,
        )


class NBWCodeProvider:
    def __init__(self, tool_config: ToolConfig) -> None:
        self.tool_config = tool_config
        validate_nbwcode_tts_config(tool_config)

    def describe(self) -> TtsProviderInfo:
        return TtsProviderInfo(
            provider="nbwcode",
            model=self.tool_config.tts_model,
            voice_id=DEFAULT_TTS_VOICE,
            speed=self.tool_config.tts_speed,
        )

    def generate(self, text: str) -> GeneratedSpeech:
        audio = synthesize_nbwcode_speech(
            base_url=self.tool_config.nbw_base_url,
            api_key=self.tool_config.nbw_automatedub_api_key or "",
            model=self.tool_config.tts_model,
            text=text,
        )
        return GeneratedSpeech(audio=audio)


class CambAIProvider:
    def __init__(self, tool_config: ToolConfig, client: Any | None = None) -> None:
        validate_cambai_tts_config(tool_config)
        self.tool_config = tool_config
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from camb.client import CambAI
            except ImportError as exc:
                raise VS3Error(
                    "Camb.ai SDK is not installed. Install the camb-sdk package."
                ) from exc
            self._client = CambAI(api_key=self.tool_config.camb_api_key)
        return self._client

    def describe(self) -> TtsProviderInfo:
        return TtsProviderInfo(
            provider="cambai",
            model=self.tool_config.tts_model,
            voice_id=self.tool_config.camb_voice_id,
            language=self.tool_config.camb_language,
            speed=self.tool_config.tts_speed,
        )

    def generate(self, text: str) -> GeneratedSpeech:
        voice_id = parse_camb_voice_id(self.tool_config.camb_voice_id)
        try:
            from camb.types import StreamTtsOutputConfiguration, StreamTtsVoiceSettings
        except ImportError as exc:
            raise VS3Error(
                "Camb.ai SDK is not installed. Install the camb-sdk package."
            ) from exc
        stream = self.client.text_to_speech.tts(
            text=text,
            voice_id=voice_id,
            language=self.tool_config.camb_language,
            speech_model=self.tool_config.tts_model,
            output_configuration=StreamTtsOutputConfiguration(format="wav"),
            voice_settings=StreamTtsVoiceSettings(speaking_rate=self.tool_config.tts_speed),
        )
        return GeneratedSpeech(audio=read_audio_stream(stream))


class NBWCodeTextToSpeechSynthesizer(ProviderTextToSpeechSynthesizer):
    def __init__(self, tool_config: ToolConfig) -> None:
        super().__init__(NBWCodeProvider(tool_config))


def create_tts_provider(tool_config: ToolConfig) -> TTSProvider:
    provider_name = tool_config.tts_provider.strip().lower()
    if provider_name == "cambai":
        return CambAIProvider(tool_config)
    if provider_name == "nbwcode":
        return NBWCodeProvider(tool_config)
    raise VS3Error(f"unsupported TTS provider: {tool_config.tts_provider}")


def validate_tts_config(tool_config: ToolConfig) -> None:
    create_tts_provider(tool_config)


def validate_nbwcode_tts_config(tool_config: ToolConfig) -> None:
    if tool_config.tts_provider != "nbwcode":
        raise VS3Error("TTS_PROVIDER must be nbwcode for NBWCode speech generation")
    if not tool_config.tts_model:
        raise VS3Error("TTS_MODEL is required for NBWCode speech generation")
    if not tool_config.nbw_automatedub_api_key:
        raise VS3Error("NBW_AUTOMATEDUB_API_KEY is required for NBWCode speech generation")


def validate_cambai_tts_config(tool_config: ToolConfig) -> None:
    if tool_config.tts_provider != "cambai":
        raise VS3Error("TTS_PROVIDER must be cambai for Camb.ai speech generation")
    if not tool_config.tts_model:
        raise VS3Error("TTS_MODEL is required for Camb.ai speech generation")
    if not tool_config.camb_api_key:
        raise VS3Error("CAMB_API_KEY is required for Camb.ai speech generation")
    if not tool_config.camb_language:
        raise VS3Error("CAMB_LANGUAGE is required for Camb.ai speech generation")
    if not tool_config.camb_voice_id:
        raise VS3Error("CAMB_VOICE_ID is required for Camb.ai speech generation")


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


def select_sample_segments(
    translation_path: Path,
    start_segment: int,
    minutes: float,
) -> list[SampleSegment]:
    if start_segment < 0:
        raise VS3Error("start segment must be zero or greater")
    if minutes <= 0:
        raise VS3Error("minutes must be greater than zero")

    segments = load_timed_translation_segments(translation_path)
    start_index = next(
        (index for index, segment in enumerate(segments) if segment.id == start_segment),
        None,
    )
    if start_index is None:
        raise VS3Error(f"start segment does not exist: {start_segment}")

    selected: list[SampleSegment] = []
    sample_start = segments[start_index].start
    sample_end = sample_start + (minutes * 60)
    for segment in segments[start_index:]:
        selected.append(segment)
        if segment.end >= sample_end:
            break
    return selected


def load_timed_translation_segments(translation_path: Path) -> list[SampleSegment]:
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

    segments: list[SampleSegment] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise VS3Error("each translation segment must be an object")
        segment_id = raw_segment.get("id")
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        target_text = raw_segment.get("target_text")
        if not isinstance(segment_id, int):
            raise VS3Error("each translation segment must contain integer id")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            raise VS3Error("each translation segment must contain numeric start and end")
        if end < start:
            raise VS3Error(f"translation segment {segment_id} has end before start")
        if not isinstance(target_text, str) or not target_text.strip():
            raise VS3Error(f"translation segment {segment_id} is missing target_text")
        segments.append(
            SampleSegment(
                id=segment_id,
                start=float(start),
                end=float(end),
                target_text=target_text.strip(),
            )
        )
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


def parse_camb_voice_id(voice_id: str | None) -> int:
    if voice_id is None:
        raise VS3Error("CAMB_VOICE_ID is required for Camb.ai speech generation")
    try:
        return int(voice_id)
    except ValueError as exc:
        raise VS3Error("CAMB_VOICE_ID must be an integer voice ID") from exc


def read_audio_stream(stream: Any) -> bytes:
    if isinstance(stream, bytes):
        return stream
    if hasattr(stream, "read"):
        data = stream.read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)

    chunks: list[bytes] = []
    for chunk in stream:
        if isinstance(chunk, bytes):
            chunks.append(chunk)
        elif isinstance(chunk, str):
            chunks.append(chunk.encode("utf-8"))
        elif hasattr(chunk, "content"):
            content = chunk.content
            chunks.append(content if isinstance(content, bytes) else bytes(content))
        else:
            chunks.append(bytes(chunk))
    return b"".join(chunks)


def list_cambai_voices(tool_config: ToolConfig, client: Any | None = None) -> list[TtsVoice]:
    if not tool_config.camb_api_key:
        raise VS3Error("CAMB_API_KEY is required to list Camb.ai voices")
    provider = CambAIProvider(
        ToolConfig(
            **{
                **tool_config.__dict__,
                "tts_provider": "cambai",
                "camb_voice_id": tool_config.camb_voice_id or "0",
            }
        ),
        client=client,
    )
    raw_voices = provider.client.voice_cloning.list_voices()
    return [normalize_cambai_voice(raw_voice) for raw_voice in iter_response_items(raw_voices)]


def normalize_cambai_voice(raw_voice: Any) -> TtsVoice:
    metadata = object_to_plain_dict(raw_voice)
    voice_id = pick_first_value(metadata, "id", "voice_id", "voiceId")
    name = pick_first_value(metadata, "name", "voice_name", "voiceName")
    gender = pick_first_value(metadata, "gender")
    language = pick_first_value(metadata, "language", "language_code", "languageCode", "locale")
    return TtsVoice(
        id=str(voice_id or ""),
        name=str(name or ""),
        gender=str(gender) if gender is not None else None,
        language=str(language) if language is not None else None,
        metadata=metadata,
    )


def iter_response_items(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    for key in ("voices", "data", "items", "results"):
        value = getattr(response, key, None)
        if isinstance(value, list):
            return value
        if isinstance(response, dict) and isinstance(response.get(key), list):
            return response[key]
    return list(response) if not isinstance(response, dict) else [response]


def object_to_plain_dict(value: Any) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    return {
        name: getattr(value, name)
        for name in dir(value)
        if not name.startswith("_") and not callable(getattr(value, name))
    }


def pick_first_value(payload: dict[str, object], *names: str) -> object | None:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return value
    return None


def build_tts_usage(
    provider_info: TtsProviderInfo,
    segments_processed: int,
    characters_processed: int,
    generation_time: float,
    provider_metadata: dict[str, object] | None = None,
) -> TtsUsage:
    return TtsUsage(
        provider=provider_info.provider,
        model=provider_info.model,
        voice_id=provider_info.voice_id,
        segments_processed=segments_processed,
        characters_processed=characters_processed,
        generation_time=generation_time,
        provider_metadata={
            "voice_name": provider_info.voice_name,
            "language": provider_info.language,
            **(provider_info.metadata or {}),
            **(provider_metadata or {}),
        },
    )


def write_tts_usage(output_dir: Path, usage: TtsUsage) -> Path:
    path = tts_usage_output_path(output_dir)
    payload = {
        "version": 1,
        "provider": usage.provider,
        "model": usage.model,
        "voice_id": usage.voice_id,
        "segments_processed": usage.segments_processed,
        "characters_processed": usage.characters_processed,
        "generation_time": usage.generation_time,
        "provider_metadata": usage.provider_metadata,
    }
    write_json(path, payload)
    return path


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
    write_json(path, payload)


def write_json(path: Path, payload: dict[str, object]) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)
