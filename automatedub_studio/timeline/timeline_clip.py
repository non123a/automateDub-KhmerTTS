"""Independent timeline clip model for Studio editing and playback."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VIDEO_TRACK_ID = "video"
ORIGINAL_AUDIO_TRACK_ID = "original_audio"
KHMER_TTS_TRACK_ID = "khmer_tts"
AUDIO_TRACK_3_ID = "audio_track_3"
AUDIO_TRACK_4_ID = "audio_track_4"

AUDIO_TRACK_IDS = (
    ORIGINAL_AUDIO_TRACK_ID,
    KHMER_TTS_TRACK_ID,
    AUDIO_TRACK_3_ID,
    AUDIO_TRACK_4_ID,
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
        )


@dataclass
class TimelineTrack:
    id: str
    name: str
    kind: str = "audio"
    muted: bool = False
    solo: bool = False
    locked: bool = False
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
            clips=[TimelineClip.from_dict(item) for item in data.get("clips", [])],
        )


@dataclass
class Timeline:
    tracks: list[TimelineTrack] = field(default_factory=list)

    @classmethod
    def default(cls) -> Timeline:
        return cls(
            tracks=[
                TimelineTrack(VIDEO_TRACK_ID, "Video", kind="video"),
                TimelineTrack(ORIGINAL_AUDIO_TRACK_ID, "Original Audio"),
                TimelineTrack(KHMER_TTS_TRACK_ID, "Khmer TTS"),
                TimelineTrack(AUDIO_TRACK_3_ID, "Audio Track 3"),
                TimelineTrack(AUDIO_TRACK_4_ID, "Audio Track 4"),
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

    def clip_by_id(self, clip_id: str) -> TimelineClip | None:
        return next((clip for clip in self.all_clips() if clip.id == clip_id), None)

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

    def active_audio_clips(self, position_ms: int) -> list[TimelineClip]:
        position_seconds = position_ms / 1000.0
        audio_tracks = [track for track in self.tracks if track.is_audio]
        soloed_track_ids = {track.id for track in audio_tracks if track.solo}
        clips: list[TimelineClip] = []
        for track in audio_tracks:
            if track.muted:
                continue
            if soloed_track_ids and track.id not in soloed_track_ids:
                continue
            clips.extend(
                clip
                for clip in track.clips
                if not clip.muted
                and clip.source_path is not None
                and clip.contains(position_seconds)
            )
        return sorted(clips, key=lambda clip: (clip.start_time, clip.track_id, clip.id))

    def to_dict(self) -> dict:
        return {"tracks": [track.to_dict() for track in self.tracks]}

    @classmethod
    def from_dict(cls, data: dict) -> Timeline:
        return cls(tracks=[TimelineTrack.from_dict(item) for item in data.get("tracks", [])])


def active_clips(
    clips: list[TimelineClip], track_id: str, position_ms: int
) -> list[TimelineClip]:
    position_seconds = position_ms / 1000.0
    return [
        clip
        for clip in clips
        if clip.track_id == track_id and not clip.muted and clip.contains(position_seconds)
    ]
