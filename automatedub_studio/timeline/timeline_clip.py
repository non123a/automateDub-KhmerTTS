"""Independent timeline clip model for Studio editing and playback."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_TRACK_ID = "video"
ORIGINAL_MOVIE_AUDIO_TRACK_ID = "original_movie_audio"
ORIGINAL_AUDIO_TRACK_ID = "original_audio"
KHMER_TTS_TRACK_ID = "khmer_tts"
DRAFT_REGENERATION_TRACK_ID = "draft_regeneration"
AUDIO_TRACK_3_ID = "audio_track_3"
AUDIO_TRACK_4_ID = "audio_track_4"

AUDIO_TRACK_IDS = (
    ORIGINAL_AUDIO_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    DRAFT_REGENERATION_TRACK_ID,
    AUDIO_TRACK_3_ID,
    AUDIO_TRACK_4_ID,
    ORIGINAL_MOVIE_AUDIO_TRACK_ID,
)
REFERENCE_TRACK_IDS = (
    ORIGINAL_AUDIO_TRACK_ID,
)


@dataclass
class TimelineMarker:
    id: str
    time_ms: int
    comment: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time_ms": self.time_ms,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TimelineMarker:
        return cls(
            id=str(data["id"]),
            time_ms=int(data["time_ms"]),
            comment=str(data.get("comment", "")),
        )


@dataclass
class TimelineClip:
    """A true timeline clip with state owned independently from transcript data."""

    id: str
    track_id: str
    start_time: float
    end_time: float
    source_path: Path | None
    source_offset: float = 0.0
    volume: float = 1.0
    muted: bool = False
    selected: bool = False
    locked: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    segment_id: int | None = None
    source_text: str = ""
    target_text: str = ""
    chinese_text: str = ""
    khmer_text: str = ""
    voice_model: str = ""
    speaking_rate: float = 1.0
    pitch: float = 0.0
    gain: float = 1.0
    is_background: bool = False

    def __post_init__(self) -> None:
        if not self.chinese_text:
            self.chinese_text = self.source_text
        if not self.khmer_text:
            self.khmer_text = self.target_text
        if not self.source_text:
            self.source_text = self.chinese_text
        if not self.target_text:
            self.target_text = self.khmer_text

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def contains(self, position_seconds: float) -> bool:
        return self.start_time <= position_seconds < self.end_time

    def source_position_ms(self, position_ms: int) -> int:
        elapsed_seconds = max(0.0, position_ms / 1000.0 - self.start_time)
        return round((self.source_offset + elapsed_seconds) * 1000)

    def volume_at(self, position_ms: int) -> float:
        if self.muted:
            return 0.0
        position_seconds = position_ms / 1000.0
        elapsed = position_seconds - self.start_time
        remaining = self.end_time - position_seconds
        volume = self.volume
        if self.fade_in > 0 and elapsed < self.fade_in:
            volume *= max(0.0, elapsed / self.fade_in)
        if self.fade_out > 0 and remaining < self.fade_out:
            volume *= max(0.0, remaining / self.fade_out)
        return max(0.0, min(1.0, volume))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "track_id": self.track_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source_path": str(self.source_path) if self.source_path is not None else None,
            "source_offset": self.source_offset,
            "volume": self.volume,
            "muted": self.muted,
            "selected": self.selected,
            "locked": self.locked,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "segment_id": self.segment_id,
            "source_text": self.source_text,
            "target_text": self.target_text,
            "chinese_text": self.chinese_text,
            "khmer_text": self.khmer_text,
            "voice_model": self.voice_model,
            "speaking_rate": self.speaking_rate,
            "pitch": self.pitch,
            "gain": self.gain,
            "is_background": self.is_background,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TimelineClip:
        source_path = data.get("source_path")
        return cls(
            id=str(data["id"]),
            track_id=str(data["track_id"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            source_path=Path(source_path) if source_path else None,
            source_offset=float(data.get("source_offset", 0.0)),
            volume=float(data.get("volume", 1.0)),
            muted=bool(data.get("muted", False)),
            selected=bool(data.get("selected", False)),
            locked=bool(data.get("locked", False)),
            fade_in=float(data.get("fade_in", 0.0)),
            fade_out=float(data.get("fade_out", 0.0)),
            segment_id=data.get("segment_id"),
            source_text=str(data.get("source_text", "")),
            target_text=str(data.get("target_text", "")),
            chinese_text=str(data.get("chinese_text", "")),
            khmer_text=str(data.get("khmer_text", "")),
            voice_model=str(data.get("voice_model", "")),
            speaking_rate=float(data.get("speaking_rate", 1.0)),
            pitch=float(data.get("pitch", 0.0)),
            gain=float(data.get("gain", 1.0)),
            is_background=bool(data.get("is_background", False)),
        )


@dataclass
class TimelineTrack:
    id: str
    name: str
    kind: str = "audio"
    muted: bool = False
    solo: bool = False
    locked: bool = False
    visible: bool = True
    reference_only: bool = False
    clips: list[TimelineClip] = field(default_factory=list)

    @property
    def is_audio(self) -> bool:
        return self.kind == "audio"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "muted": self.muted,
            "solo": self.solo,
            "locked": self.locked,
            "visible": self.visible,
            "reference_only": self.reference_only,
            "clips": [clip.to_dict() for clip in self.clips],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TimelineTrack:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            kind=str(data.get("kind", "audio")),
            muted=bool(data.get("muted", False)),
            solo=bool(data.get("solo", False)),
            locked=bool(data.get("locked", False)),
            visible=bool(data.get("visible", True)),
            reference_only=bool(data.get("reference_only", False)),
            clips=[TimelineClip.from_dict(item) for item in data.get("clips", [])],
        )


@dataclass
class Timeline:
    tracks: list[TimelineTrack] = field(default_factory=list)
    markers: list[TimelineMarker] = field(default_factory=list)

    @classmethod
    def default(cls) -> Timeline:
        return cls(
            tracks=[
                TimelineTrack(VIDEO_TRACK_ID, "Video", kind="video"),
                TimelineTrack(
                    ORIGINAL_AUDIO_TRACK_ID,
                    "Original Speech Segments",
                    locked=True,
                ),
                TimelineTrack(KHMER_TTS_TRACK_ID, "Khmer TTS"),
                TimelineTrack(DRAFT_REGENERATION_TRACK_ID, "Draft Regeneration"),
            ]
        )

    @classmethod
    def from_clips(cls, clips: list[TimelineClip]) -> Timeline:
        timeline = cls.default()
        for clip in clips:
            track = timeline.track_by_id(clip.track_id)
            if track is None:
                track = TimelineTrack(clip.track_id, clip.track_id.replace("_", " ").title())
                timeline.tracks.append(track)
            track.clips.append(clip)
        return timeline

    def all_clips(self) -> list[TimelineClip]:
        return [clip for track in self.tracks for clip in track.clips]

    def track_by_id(self, track_id: str) -> TimelineTrack | None:
        return next((track for track in self.tracks if track.id == track_id), None)

    def ensure_track(
        self,
        track_id: str,
        name: str,
        *,
        kind: str = "audio",
        locked: bool = False,
        reference_only: bool = False,
    ) -> TimelineTrack:
        track = self.track_by_id(track_id)
        if track is not None:
            return track
        track = TimelineTrack(
            track_id,
            name,
            kind=kind,
            locked=locked,
            reference_only=reference_only,
        )
        if track_id == ORIGINAL_MOVIE_AUDIO_TRACK_ID:
            self.tracks.append(track)
            return track
        if kind == "video":
            self.tracks.append(track)
            return track
        insert_at = next(
            (
                index + 1
                for index, existing in enumerate(self.tracks)
                if existing.id == KHMER_TTS_TRACK_ID
            ),
            len(self.tracks),
        )
        self.tracks.insert(insert_at, track)
        return track

    def clip_by_id(self, clip_id: str) -> TimelineClip | None:
        return next((clip for clip in self.all_clips() if clip.id == clip_id), None)

    def remove_clip(self, clip_id: str) -> TimelineClip | None:
        clip = self.clip_by_id(clip_id)
        if clip is None:
            return None
        track = self.track_by_id(clip.track_id)
        if track is None:
            return None
        try:
            track.clips.remove(clip)
        except ValueError:
            return None
        return clip

    def move_clip_to_track(self, clip_id: str, track_id: str) -> bool:
        clip = self.clip_by_id(clip_id)
        if clip is None:
            return False
        return self.move_clip(clip_id, track_id, clip.start_time)

    def move_clip(self, clip_id: str, track_id: str, start_time: float) -> bool:
        clip = self.clip_by_id(clip_id)
        if clip is None:
            return False
        source_track = next(
            (track for track in self.tracks if any(clip.id == clip_id for clip in track.clips)),
            None,
        )
        target_track = self.track_by_id(track_id)
        if source_track is None or target_track is None:
            return False
        if source_track.locked or target_track.locked:
            return False
        if clip.locked:
            return False
        if clip.track_id != source_track.id:
            return False
        source_track.clips.remove(clip)
        clip.track_id = target_track.id
        duration = clip.duration
        clip.start_time = start_time
        clip.end_time = start_time + duration
        target_track.clips.append(clip)
        target_track.clips.sort(key=lambda item: (item.start_time, item.id))
        return True

    def add_clip(self, clip: TimelineClip) -> None:
        track = self.ensure_track(
            clip.track_id,
            clip.track_id.replace("_", " ").title(),
            kind="video" if clip.track_id == VIDEO_TRACK_ID else "audio",
        )
        track.clips.append(clip)
        track.clips.sort(key=lambda item: (item.start_time, item.id))

    def active_audio_clips(self, position_ms: int) -> list[TimelineClip]:
        position_seconds = position_ms / 1000.0
        audio_tracks = [
            track for track in self.tracks if track.is_audio and not track.reference_only
        ]
        soloed_track_ids = {track.id for track in audio_tracks if track.solo and not track.muted}
        selected: list[TimelineClip] = []
        for track in audio_tracks:
            if track.muted:
                continue
            if soloed_track_ids and track.id not in soloed_track_ids:
                continue
            for clip in track.clips:
                if _clip_enabled_for_playback(track, clip, position_seconds):
                    selected.append(clip)
        return sorted(selected, key=lambda clip: (clip.start_time, clip.track_id, clip.id))

    def to_dict(self) -> dict:
        return {
            "tracks": [track.to_dict() for track in self.tracks],
            "markers": [marker.to_dict() for marker in self.markers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Timeline:
        return cls(
            tracks=[TimelineTrack.from_dict(item) for item in data.get("tracks", [])],
            markers=[TimelineMarker.from_dict(item) for item in data.get("markers", [])],
        )


class AudioClipIntervalIndex:
    """Immutable interval lookup for timeline audio clips.

    The index stores clips ordered by start time.  A cursor advances in O(k)
    for normal forward playback; seeks use a binary search and examine only
    earlier clips that can still overlap the requested point.
    """

    def __init__(self, clips: list[TimelineClip]) -> None:
        self._clips = tuple(sorted(clips, key=lambda clip: (clip.start_time, clip.id)))
        self._starts = tuple(clip.start_time for clip in self._clips)
        self._cursor_position: float | None = None
        self._cursor_active: dict[str, TimelineClip] = {}
        self._cursor_next = 0

    def active_at(self, position_ms: int) -> list[TimelineClip]:
        position = position_ms / 1000.0
        if self._cursor_position is not None and position >= self._cursor_position:
            while self._cursor_next < len(self._clips):
                clip = self._clips[self._cursor_next]
                if clip.start_time > position:
                    break
                if clip.end_time > position:
                    self._cursor_active[clip.id] = clip
                self._cursor_next += 1
            self._cursor_active = {
                clip_id: clip
                for clip_id, clip in self._cursor_active.items()
                if clip.end_time > position
            }
        else:
            upper = bisect_right(self._starts, position)
            self._cursor_active = {
                clip.id: clip for clip in self._clips[:upper] if clip.end_time > position
            }
            self._cursor_next = upper
        self._cursor_position = position
        return sorted(
            self._cursor_active.values(),
            key=lambda clip: (clip.start_time, clip.track_id, clip.id),
        )

    @property
    def maximum_overlap(self) -> int:
        events = sorted(
            [(clip.start_time, 1) for clip in self._clips]
            + [(clip.end_time, -1) for clip in self._clips],
            key=lambda event: (event[0], event[1]),
        )
        active = maximum = 0
        for _position, delta in events:
            active += delta
            maximum = max(maximum, active)
        return maximum

def active_clips(
    clips: list[TimelineClip], track_id: str, position_ms: int
) -> list[TimelineClip]:
    position_seconds = position_ms / 1000.0
    return [
        clip
        for clip in clips
        if clip.track_id == track_id and not clip.muted and clip.contains(position_seconds)
    ]


def _clip_has_playable_source(clip: TimelineClip) -> bool:
    if clip.segment_id is None:
        return True
    return bool(clip.source_path and clip.source_path.is_file())


def _clip_enabled_for_playback(
    track: TimelineTrack, clip: TimelineClip, position_seconds: float
) -> bool:
    return (
        not track.muted
        and not clip.muted
        and clip.source_path is not None
        and clip.contains(position_seconds)
        and _clip_has_playable_source(clip)
    )
