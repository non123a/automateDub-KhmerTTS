"""Plain data model for a Studio project (an existing AutomateDub output/ directory).

Intentionally Qt-free so it can be constructed and tested without a
QApplication. The Studio should eventually read a project.json manifest
instead of re-deriving these paths on every open, but that manifest does
not exist yet -- this model only reflects what VS0-VS4 actually produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Segment:
    id: int
    start: float
    end: float
    source_text: str
    target_text: str
    offset_ms: int = 0


@dataclass
class MediaAsset:
    source_video: Path | None = None
    proxy_video: Path | None = None
    extracted_audio: Path | None = None

    @property
    def preview_video(self) -> Path | None:
        return self.proxy_video or self.source_video

    @property
    def export_video(self) -> Path | None:
        return self.source_video


@dataclass
class Project:
    project_path: Path
    audio_path: Path
    translation_path: Path
    tts_directory: Path
    video_path: Path | None = None
    editor_video_path: Path | None = None
    source_codec: str | None = None
    editor_codec: str | None = None
    mixed_audio_path: Path | None = None
    tts_combined_path: Path | None = None
    media: MediaAsset = field(default_factory=MediaAsset)
    segments: list[Segment] = field(default_factory=list)
    tts_file_count: int = 0
    video_candidates: list[Path] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def has_video(self) -> bool:
        return self.preview_video_path is not None

    @property
    def source_video_path(self) -> Path | None:
        return self.media.source_video or self.video_path

    @property
    def proxy_video_path(self) -> Path | None:
        return self.media.proxy_video or self.editor_video_path

    @property
    def preview_video_path(self) -> Path | None:
        return self.media.preview_video or self.editor_video_path or self.video_path

    @property
    def export_video_path(self) -> Path | None:
        return self.media.export_video or self.video_path

    @property
    def extracted_audio_path(self) -> Path:
        return self.media.extracted_audio or self.audio_path
