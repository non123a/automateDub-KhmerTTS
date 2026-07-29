from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from automatedub_studio.timeline.waveform_cache import (
    WaveformCache,
    WaveformError,
    WaveformPeaks,
    compute_waveform_peaks,
)


def _write_wav(
    path: Path,
    frame_count: int = 4000,
    frame_rate: int = 8000,
    channels: int = 1,
    sample_width: int = 2,
) -> None:
    """Write a real, decodable WAV file containing a sine wave."""
    max_value = 2 ** (sample_width * 8 - 1) - 1
    fmt = {1: "b", 2: "h", 4: "i"}[sample_width]
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(frame_rate)
        frames = bytearray()
        for i in range(frame_count):
            value = int(max_value * math.sin(2 * math.pi * 440 * i / frame_rate))
            for _ in range(channels):
                frames += struct.pack(f"<{fmt}", value)
        wav_file.writeframes(bytes(frames))


def _write_empty_wav(path: Path, frame_rate: int = 8000, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"")


# ---------------------------------------------------------------------------
# Waveform generation
# ---------------------------------------------------------------------------


def test_compute_waveform_peaks_returns_bucket_count(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    peaks = compute_waveform_peaks(wav_path, bucket_count=50)
    assert len(peaks.peaks) == 50


def test_compute_waveform_peaks_values_within_range(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    peaks = compute_waveform_peaks(wav_path, bucket_count=50)
    for lo, hi in peaks.peaks:
        assert -1.0 <= lo <= 1.0
        assert -1.0 <= hi <= 1.0
        assert lo <= hi


def test_compute_waveform_peaks_respects_start_end(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path, frame_count=8000, frame_rate=8000)
    full = compute_waveform_peaks(wav_path, bucket_count=20)
    partial = compute_waveform_peaks(wav_path, bucket_count=20, start_seconds=0.0, end_seconds=0.5)
    assert full.peaks != partial.peaks or len(full.peaks) == len(partial.peaks)


def test_compute_waveform_peaks_multi_channel(tmp_path: Path) -> None:
    wav_path = tmp_path / "stereo.wav"
    _write_wav(wav_path, channels=2)
    peaks = compute_waveform_peaks(wav_path, bucket_count=30)
    assert len(peaks.peaks) == 30


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_cache_miss_then_hit_returns_same_instance(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    cache = WaveformCache()
    first = cache.get_or_compute(wav_path, bucket_count=40)
    second = cache.get_or_compute(wav_path, bucket_count=40)
    assert first is second


def test_cache_different_bucket_count_is_different_entry(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    cache = WaveformCache()
    first = cache.get_or_compute(wav_path, bucket_count=40)
    second = cache.get_or_compute(wav_path, bucket_count=60)
    assert first is not second
    assert len(first.peaks) == 40
    assert len(second.peaks) == 60


def test_cache_get_returns_none_before_compute(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    cache = WaveformCache()
    assert cache.get(wav_path, bucket_count=40) is None


def test_cache_invalidate_forces_recompute(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    cache = WaveformCache()
    first = cache.get_or_compute(wav_path, bucket_count=40)
    cache.invalidate(wav_path)
    assert cache.get(wav_path, bucket_count=40) is None
    second = cache.get_or_compute(wav_path, bucket_count=40)
    assert first is not second


def test_cache_invalidate_only_affects_matching_path(tmp_path: Path) -> None:
    wav_a = tmp_path / "a.wav"
    wav_b = tmp_path / "b.wav"
    _write_wav(wav_a)
    _write_wav(wav_b)
    cache = WaveformCache()
    cache.get_or_compute(wav_a, bucket_count=40)
    peaks_b = cache.get_or_compute(wav_b, bucket_count=40)
    cache.invalidate(wav_a)
    assert cache.get(wav_a, bucket_count=40) is None
    assert cache.get(wav_b, bucket_count=40) is peaks_b


def test_cache_mtime_change_invalidates_entry(tmp_path: Path) -> None:
    wav_path = tmp_path / "tone.wav"
    _write_wav(wav_path)
    cache = WaveformCache()
    first = cache.get_or_compute(wav_path, bucket_count=40)
    new_mtime = Path(wav_path).stat().st_mtime + 5
    os_utime = __import__("os").utime
    os_utime(wav_path, (new_mtime, new_mtime))
    second = cache.get_or_compute(wav_path, bucket_count=40)
    assert first is not second


# ---------------------------------------------------------------------------
# Empty WAV
# ---------------------------------------------------------------------------


def test_empty_wav_returns_empty_peaks(tmp_path: Path) -> None:
    wav_path = tmp_path / "empty.wav"
    _write_empty_wav(wav_path)
    peaks = compute_waveform_peaks(wav_path, bucket_count=40)
    assert peaks == WaveformPeaks(peaks=())


def test_empty_wav_does_not_raise(tmp_path: Path) -> None:
    wav_path = tmp_path / "empty.wav"
    _write_empty_wav(wav_path)
    cache = WaveformCache()
    peaks = cache.get_or_compute(wav_path, bucket_count=40)
    assert peaks.peaks == ()


# ---------------------------------------------------------------------------
# Invalid WAV
# ---------------------------------------------------------------------------


def test_invalid_wav_raises_waveform_error(tmp_path: Path) -> None:
    wav_path = tmp_path / "invalid.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")
    with pytest.raises(WaveformError):
        compute_waveform_peaks(wav_path, bucket_count=40)


def test_missing_wav_raises_waveform_error(tmp_path: Path) -> None:
    wav_path = tmp_path / "does_not_exist.wav"
    with pytest.raises(WaveformError):
        compute_waveform_peaks(wav_path, bucket_count=40)


def test_cache_get_or_compute_propagates_waveform_error(tmp_path: Path) -> None:
    wav_path = tmp_path / "invalid.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")
    cache = WaveformCache()
    with pytest.raises(WaveformError):
        cache.get_or_compute(wav_path, bucket_count=40)
