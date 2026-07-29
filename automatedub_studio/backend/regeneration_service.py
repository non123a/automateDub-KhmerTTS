"""Selective TTS regeneration: calls TTSProvider.generate() only for requested segments.

Never touches translation.json, never regenerates a segment that was not
explicitly requested, and never overwrites tts/####.wav for a segment that
fails (the previous WAV is left untouched until a new one validates).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ClipRegenerationOutcome:
    clip_id: str
    success: bool
    error: str | None = None
    duration_seconds: float | None = None
    wav_path: Path | None = None


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
    try:
        provider = provider_factory(effective_config)
        speech = provider.generate(text)
        validate_wav_audio(speech.audio, segment.id)
        output_path.write_bytes(speech.audio)
        duration = probe_wav_duration_seconds(output_path)
        return RegenerationOutcome(
            segment_id=segment.id,
            success=True,
            duration_seconds=duration,
            wav_path=output_path,
        )
    except Exception as exc:  # noqa: BLE001 — any provider/validation failure is a per-segment failure
        return RegenerationOutcome(segment_id=segment.id, success=False, error=str(exc))


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
        speech = provider.generate(clip.khmer_text)
        validate_wav_audio(speech.audio, clip.segment_id if clip.segment_id is not None else 0)
        output_path.write_bytes(speech.audio)
        duration = probe_wav_duration_seconds(output_path)
        return ClipRegenerationOutcome(
            clip_id=clip.id,
            success=True,
            duration_seconds=duration,
            wav_path=output_path,
        )
    except Exception as exc:  # noqa: BLE001
        return ClipRegenerationOutcome(clip_id=clip.id, success=False, error=str(exc))


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
