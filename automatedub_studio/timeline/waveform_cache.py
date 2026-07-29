"""Waveform peak extraction and caching for timeline clips.

Kept independent of Qt/rendering (no PySide6 imports) so it can be tested
without a QApplication. Peaks are (min, max) pairs per bucket, computed once
per (path, mtime, bucket_count, range) key and cached in memory -- callers
should reuse one WaveformCache instance across the timeline's lifetime so
edits/regenerations (which change a WAV's mtime) transparently invalidate
stale entries without an explicit invalidate() call.
"""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BUCKET_COUNT = 100

_SAMPLE_WIDTH_FORMATS = {1: "b", 2: "h", 4: "i"}  # signed int struct formats by byte width


class WaveformError(RuntimeError):
    """Raised when a WAV file cannot be read for waveform generation."""


@dataclass(frozen=True)
class WaveformPeaks:
    """Per-bucket (min, max) sample extremes, normalized to [-1.0, 1.0].

    An empty ``peaks`` tuple means "nothing to draw" (e.g. a zero-frame WAV
    or a zero-length time range) rather than an error.
    """

    peaks: tuple[tuple[float, float], ...]


def compute_waveform_peaks(
    wav_path: Path,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> WaveformPeaks:
    """Read *wav_path* and return min/max peaks for ``[start_seconds, end_seconds)``.

    ``end_seconds=None`` reads to the end of the file. Raises WaveformError if
    the file cannot be opened/decoded as a WAV. Returns an empty WaveformPeaks
    (no buckets) for a valid but empty (zero-frame) WAV or range.
    """
    wav_path = Path(wav_path)
    try:
        with wave.open(str(wav_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            total_frames = wav_file.getnframes()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()

            if frame_rate <= 0 or channels <= 0 or total_frames == 0:
                return WaveformPeaks(peaks=())

            start_frame = max(0, int(start_seconds * frame_rate))
            end_frame = (
                total_frames
                if end_seconds is None
                else min(total_frames, int(end_seconds * frame_rate))
            )
            frame_count = max(0, end_frame - start_frame)
            if frame_count == 0:
                return WaveformPeaks(peaks=())

            wav_file.setpos(start_frame)
            raw = wav_file.readframes(frame_count)
    except (wave.Error, EOFError, OSError) as exc:
        raise WaveformError(f"unable to read WAV for waveform: {wav_path}") from exc

    samples = _decode_samples(raw, sample_width, channels)
    if not samples:
        return WaveformPeaks(peaks=())
    return WaveformPeaks(peaks=_bucketize(samples, bucket_count))


def _decode_samples(raw: bytes, sample_width: int, channels: int) -> list[float]:
    fmt = _SAMPLE_WIDTH_FORMATS.get(sample_width)
    if fmt is None:
        raise WaveformError(f"unsupported WAV sample width: {sample_width} bytes")

    max_value = float(2 ** (sample_width * 8 - 1))
    count = len(raw) // (sample_width * channels)
    if count == 0:
        return []

    usable_bytes = count * channels * sample_width
    unpacked = struct.unpack(f"<{count * channels}{fmt}", raw[:usable_bytes])

    samples: list[float] = []
    for i in range(count):
        frame = unpacked[i * channels : i * channels + channels]
        samples.append((sum(frame) / len(frame)) / max_value)
    return samples


def _bucketize(samples: list[float], bucket_count: int) -> tuple[tuple[float, float], ...]:
    bucket_count = max(1, bucket_count)
    total = len(samples)
    if total == 0:
        return ()

    peaks: list[tuple[float, float]] = []
    for bucket in range(bucket_count):
        lo_index = bucket * total // bucket_count
        hi_index = max(lo_index + 1, (bucket + 1) * total // bucket_count)
        chunk = samples[lo_index:hi_index]
        peaks.append((min(chunk), max(chunk)) if chunk else (0.0, 0.0))
    return tuple(peaks)


class WaveformCache:
    """In-memory cache of computed WaveformPeaks, keyed by file identity + range.

    A cache hit returns the exact same WaveformPeaks instance that was
    stored, so callers can detect "no recompute happened" via identity.
    """

    def __init__(self) -> None:
        self._store: dict[tuple, WaveformPeaks] = {}

    def get(
        self,
        wav_path: Path,
        bucket_count: int = DEFAULT_BUCKET_COUNT,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> WaveformPeaks | None:
        return self._store.get(self._key(wav_path, bucket_count, start_seconds, end_seconds))

    def get_or_compute(
        self,
        wav_path: Path,
        bucket_count: int = DEFAULT_BUCKET_COUNT,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> WaveformPeaks:
        key = self._key(wav_path, bucket_count, start_seconds, end_seconds)
        cached = self._store.get(key)
        if cached is not None:
            return cached
        peaks = compute_waveform_peaks(wav_path, bucket_count, start_seconds, end_seconds)
        self._store[key] = peaks
        return peaks

    def invalidate(self, wav_path: Path) -> None:
        target = str(Path(wav_path))
        self._store = {key: value for key, value in self._store.items() if key[0] != target}

    @staticmethod
    def _key(
        wav_path: Path,
        bucket_count: int,
        start_seconds: float,
        end_seconds: float | None,
    ) -> tuple:
        path = Path(wav_path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        return (
            str(path),
            mtime,
            bucket_count,
            round(start_seconds, 3),
            round(end_seconds, 3) if end_seconds is not None else None,
        )
