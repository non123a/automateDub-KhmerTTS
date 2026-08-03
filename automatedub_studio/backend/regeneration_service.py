"""Selective TTS regeneration: calls TTSProvider.generate() only for requested segments.

Never touches translation.json, never regenerates a segment that was not
explicitly requested, and never overwrites tts/####.wav for a segment that
fails (the previous WAV is left untouched until a new one validates).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from automatedub.config import ToolConfig
from automatedub.vertical_slice.duration_report import probe_wav_duration_seconds
from automatedub.vertical_slice.tts import (
    TTSProvider,
    create_tts_provider,
    tts_segment_output_path,
    validate_wav_audio,
)
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Segment
from automatedub_studio.timeline.timeline_clip import TimelineClip

ProviderFactory = Callable[[ToolConfig], TTSProvider]


@dataclass(frozen=True)
class RegenerationOutcome:
    segment_id: int
    success: bool
    error: str | None = None
    duration_seconds: float | None = None
    wav_path: Path | None = None
    provider_id: str | None = None
    provider_class: str | None = None
    voice_id: str | None = None
    model: str | None = None
    speaking_rate: float | None = None
    request_started: bool = False
    request_started_at: str | None = None
    request_finished_at: str | None = None
    http_status: int | None = None
    response_body: str | None = None
    validation_result: str = "not_run"
    file_exists: bool = False
    file_size: int = 0


@dataclass(frozen=True)
class ClipRegenerationOutcome:
    clip_id: str
    success: bool
    error: str | None = None
    duration_seconds: float | None = None
    wav_path: Path | None = None
    provider_id: str | None = None
    provider_class: str | None = None
    voice_id: str | None = None
    model: str | None = None
    speaking_rate: float | None = None
    request_started: bool = False
    request_started_at: str | None = None
    request_finished_at: str | None = None
    http_status: int | None = None
    response_body: str | None = None
    validation_result: str = "not_run"
    file_exists: bool = False
    file_size: int = 0


def resolve_text(segment: Segment, editable: EditableSegment | None) -> str:
    if editable is not None and editable.edited_text:
        return editable.edited_text
    return segment.target_text


def resolve_tool_config(tool_config: ToolConfig, editable: EditableSegment | None) -> ToolConfig:
    if editable is not None and editable.voice_id:
        return dataclasses.replace(tool_config, camb_voice_id=editable.voice_id)
    return tool_config


def regenerate_segment(
    segment: Segment,
    editable: EditableSegment | None,
    tts_dir: Path,
    tool_config: ToolConfig,
    provider_factory: ProviderFactory = create_tts_provider,
) -> RegenerationOutcome:
    """Regenerate exactly one segment's WAV. Leaves the existing file untouched on failure."""
    text = resolve_text(segment, editable)
    effective_config = resolve_tool_config(tool_config, editable)
    output_path = tts_segment_output_path(tts_dir, segment.id)
    request_started_at = datetime.now(UTC).isoformat()
    provider_id = effective_config.tts_provider
    provider_class: str | None = None
    validation_result = "not_run"
    request_started = False
    try:
        provider = provider_factory(effective_config)
        provider_class = type(provider).__name__
        request_started = True
        speech = provider.generate(text)
        validate_wav_audio(speech.audio, segment.id)
        validation_result = "passed"
        output_path.write_bytes(speech.audio)
        duration = probe_wav_duration_seconds(output_path)
        request_finished_at = datetime.now(UTC).isoformat()
        return RegenerationOutcome(
            segment_id=segment.id,
            success=True,
            duration_seconds=duration,
            wav_path=output_path,
            provider_id=provider_id,
            provider_class=provider_class,
            voice_id=effective_config.camb_voice_id,
            model=effective_config.tts_model,
            speaking_rate=effective_config.tts_speed,
            request_started=request_started,
            request_started_at=request_started_at,
            request_finished_at=request_finished_at,
            validation_result=validation_result,
            file_exists=output_path.is_file(),
            file_size=output_path.stat().st_size if output_path.is_file() else 0,
        )
    except Exception as exc:  # noqa: BLE001 — any provider/validation failure is a per-segment failure
        if "did not return WAV" in str(exc):
            validation_result = "failed"
        return RegenerationOutcome(
            segment_id=segment.id,
            success=False,
            error=str(exc),
            wav_path=output_path,
            provider_id=provider_id,
            provider_class=provider_class,
            voice_id=effective_config.camb_voice_id,
            model=effective_config.tts_model,
            speaking_rate=effective_config.tts_speed,
            request_started=request_started,
            request_started_at=request_started_at,
            request_finished_at=datetime.now(UTC).isoformat(),
            http_status=_http_status_from_error(exc),
            response_body=_response_body_from_error(exc),
            validation_result=validation_result,
            file_exists=output_path.is_file(),
            file_size=output_path.stat().st_size if output_path.is_file() else 0,
        )


def clip_tts_output_path(tts_dir: Path, clip_id: str) -> Path:
    safe_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in clip_id)
    return tts_dir / "clips" / f"{safe_id}.wav"


def regenerate_timeline_clip(
    clip: TimelineClip,
    tts_dir: Path,
    tool_config: ToolConfig,
    provider_factory: ProviderFactory = create_tts_provider,
) -> ClipRegenerationOutcome:
    """Regenerate one TimelineClip WAV without touching sibling segment audio."""
    output_path = clip_tts_output_path(tts_dir, clip.id)
    request_started_at = datetime.now(UTC).isoformat()
    provider_id = tool_config.tts_provider
    provider_class: str | None = None
    validation_result = "not_run"
    request_started = False
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        effective_config = tool_config
        if clip.voice_model:
            effective_config = dataclasses.replace(tool_config, camb_voice_id=clip.voice_model)
        if abs(clip.speaking_rate - tool_config.tts_speed) > 1e-9:
            effective_config = dataclasses.replace(
                effective_config, tts_speed=clip.speaking_rate
            )
        provider = provider_factory(effective_config)
        provider_class = type(provider).__name__
        request_started = True
        speech = provider.generate(clip.khmer_text)
        validate_wav_audio(speech.audio, clip.segment_id if clip.segment_id is not None else 0)
        validation_result = "passed"
        output_path.write_bytes(speech.audio)
        duration = probe_wav_duration_seconds(output_path)
        request_finished_at = datetime.now(UTC).isoformat()
        return ClipRegenerationOutcome(
            clip_id=clip.id,
            success=True,
            duration_seconds=duration,
            wav_path=output_path,
            provider_id=provider_id,
            provider_class=provider_class,
            voice_id=effective_config.camb_voice_id,
            model=effective_config.tts_model,
            speaking_rate=effective_config.tts_speed,
            request_started=request_started,
            request_started_at=request_started_at,
            request_finished_at=request_finished_at,
            validation_result=validation_result,
            file_exists=output_path.is_file(),
            file_size=output_path.stat().st_size if output_path.is_file() else 0,
        )
    except Exception as exc:  # noqa: BLE001
        if "did not return WAV" in str(exc):
            validation_result = "failed"
        return ClipRegenerationOutcome(
            clip_id=clip.id,
            success=False,
            error=str(exc),
            wav_path=output_path,
            provider_id=provider_id,
            provider_class=provider_class,
            voice_id=effective_config.camb_voice_id,
            model=effective_config.tts_model,
            speaking_rate=effective_config.tts_speed,
            request_started=request_started,
            request_started_at=request_started_at,
            request_finished_at=datetime.now(UTC).isoformat(),
            http_status=_http_status_from_error(exc),
            response_body=_response_body_from_error(exc),
            validation_result=validation_result,
            file_exists=output_path.is_file(),
            file_size=output_path.stat().st_size if output_path.is_file() else 0,
        )


def regenerate_segments(
    segments: Iterable[Segment],
    editables: dict[int, EditableSegment],
    tts_dir: Path,
    tool_config: ToolConfig,
    segment_ids: Iterable[int],
    on_result: Callable[[RegenerationOutcome], None] | None = None,
    on_start: Callable[[int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    provider_factory: ProviderFactory = create_tts_provider,
) -> list[RegenerationOutcome]:
    """Regenerate only the segments whose id is in ``segment_ids``, in that order.

    Never calls the provider for a segment outside ``segment_ids``. Continues
    past individual failures. Stops early (without marking remaining segments
    as failed) if ``is_cancelled`` starts returning True.
    """
    by_id = {s.id: s for s in segments}
    outcomes: list[RegenerationOutcome] = []
    for segment_id in segment_ids:
        if is_cancelled is not None and is_cancelled():
            break
        segment = by_id.get(segment_id)
        if segment is None:
            continue
        if on_start is not None:
            on_start(segment_id)
        outcome = regenerate_segment(
            segment, editables.get(segment_id), tts_dir, tool_config, provider_factory
        )
        outcomes.append(outcome)
        if on_result is not None:
            on_result(outcome)
    return outcomes


def select_selected_ids(
    segment_ids: Iterable[int], editables: dict[int, EditableSegment]
) -> list[int]:
    return [sid for sid in segment_ids if not _is_locked(sid, editables)]


def select_changed_ids(
    segments: Iterable[Segment], editables: dict[int, EditableSegment]
) -> list[int]:
    return [
        s.id
        for s in segments
        if (es := editables.get(s.id)) is not None
        and es.needs_regeneration
        and not es.locked
    ]


def select_failed_ids(
    segments: Iterable[Segment], editables: dict[int, EditableSegment]
) -> list[int]:
    return [
        s.id
        for s in segments
        if (es := editables.get(s.id)) is not None
        and es.last_error is not None
        and not es.locked
    ]


def select_all_ids(segments: Iterable[Segment], editables: dict[int, EditableSegment]) -> list[int]:
    return [s.id for s in segments if not _is_locked(s.id, editables)]


def _is_locked(segment_id: int, editables: dict[int, EditableSegment]) -> bool:
    es = editables.get(segment_id)
    return es is not None and es.locked


def _http_status_from_error(error: Exception) -> int | None:
    match = re.search(r"\bHTTP\s+(\d{3})\b", str(error), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _response_body_from_error(error: Exception) -> str | None:
    message = str(error)
    marker = re.search(r"\bHTTP\s+\d{3}:\s*(.*)", message, flags=re.IGNORECASE | re.DOTALL)
    return marker.group(1).strip() if marker else None
