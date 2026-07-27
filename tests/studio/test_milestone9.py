"""Milestone 9 — Export Video tests.

Tests for:
- export_service.py: build_export_speech_tracks, build_mux_command, export_project
- export_worker.py: ExportJob, ExportRunner
- ExportProgressDialog: stage/progress/error handling
- mix.py: per-segment volume/fade in filter graph
"""

from __future__ import annotations

import json
import os
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop

from automatedub.config import ToolConfig
from automatedub.vertical_slice.mix import MixSpeechTrack, build_mix_filter_complex
from automatedub_studio.backend.export_service import (
    ExportError,
    ExportOptions,
    ExportResult,
    ExportStage,
    build_export_speech_tracks,
    build_mux_command,
    export_project,
)
from automatedub_studio.backend.export_worker import ExportJob, ExportRunner
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project, Segment
from automatedub_studio.ui.export_dialog import ExportProgressDialog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_valid_wav_bytes(seconds: float = 0.5, frame_rate: int = 16000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * int(frame_rate * seconds))
    return buf.getvalue()


def _make_project(tmp_path: Path, segment_count: int = 2, with_video: bool = True) -> Project:
    project_dir = tmp_path / "output"
    project_dir.mkdir()
    audio_path = project_dir / "audio.wav"
    audio_path.write_bytes(make_valid_wav_bytes(10.0))

    tts_dir = project_dir / "tts"
    tts_dir.mkdir()

    segments: list[Segment] = []
    for i in range(segment_count):
        wav_path = tts_dir / f"{i:04d}.wav"
        wav_path.write_bytes(make_valid_wav_bytes(0.5))
        segments.append(Segment(id=i, start=float(i), end=float(i) + 1.0,
                                source_text=f"src {i}", target_text=f"tgt {i}"))

    video_path = None
    if with_video:
        video_path = project_dir / "video.mp4"
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    translation_payload = {
        "version": 1,
        "source_transcript": "transcript.json",
        "prompt_artifact": "translation_prompt.json",
        "engine": {"provider": "test", "model": "test"},
        "segments": [
            {
                "id": s.id, "start": s.start, "end": s.end,
                "source_language": "zh", "target_language": "km",
                "source_text": s.source_text, "target_text": s.target_text,
                "notes": None,
            }
            for s in segments
        ],
    }
    (project_dir / "translation.json").write_text(
        json.dumps(translation_payload), encoding="utf-8"
    )

    return Project(
        project_path=project_dir,
        audio_path=audio_path,
        translation_path=project_dir / "translation.json",
        tts_directory=tts_dir,
        video_path=video_path,
        segments=segments,
        tts_file_count=segment_count,
    )


def _default_tool_config() -> ToolConfig:
    return ToolConfig(
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        tts_sync_offset_ms=0,
        duck_volume=0.0,
        tts_speed=1.0,
    )


# ---------------------------------------------------------------------------
# build_export_speech_tracks
# ---------------------------------------------------------------------------


def test_build_export_speech_tracks_includes_existing_wavs(tmp_path):
    project = _make_project(tmp_path, segment_count=2)
    tracks = build_export_speech_tracks(
        project.segments, {}, project.tts_directory, _default_tool_config()
    )
    assert len(tracks) == 2
    assert all(t.tts_path.exists() for t in tracks)


def test_build_export_speech_tracks_skips_missing_wav(tmp_path):
    project = _make_project(tmp_path, segment_count=2)
    (project.tts_directory / "0001.wav").unlink()
    tracks = build_export_speech_tracks(
        project.segments, {}, project.tts_directory, _default_tool_config()
    )
    assert len(tracks) == 1
    assert tracks[0].id == 0


def test_build_export_speech_tracks_applies_offset(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    editables = {0: EditableSegment(id=0, offset_ms=500)}
    tracks = build_export_speech_tracks(
        project.segments, editables, project.tts_directory, _default_tool_config()
    )
    # segment.start=0, offset_extra=500, tts_sync_offset_ms=0 → delay_ms=500
    assert tracks[0].delay_ms == 500


def test_build_export_speech_tracks_applies_volume(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    editables = {0: EditableSegment(id=0, volume=0.5)}
    tracks = build_export_speech_tracks(
        project.segments, editables, project.tts_directory, _default_tool_config()
    )
    assert tracks[0].volume == 0.5


def test_build_export_speech_tracks_applies_fades(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    editables = {0: EditableSegment(id=0, fade_in_ms=50, fade_out_ms=80)}
    tracks = build_export_speech_tracks(
        project.segments, editables, project.tts_directory, _default_tool_config()
    )
    assert tracks[0].fade_in_ms == 50
    assert tracks[0].fade_out_ms == 80


def test_build_export_speech_tracks_default_volume_is_one(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    tracks = build_export_speech_tracks(
        project.segments, {}, project.tts_directory, _default_tool_config()
    )
    assert tracks[0].volume == 1.0
    assert tracks[0].fade_in_ms == 0
    assert tracks[0].fade_out_ms == 0


# ---------------------------------------------------------------------------
# build_mux_command
# ---------------------------------------------------------------------------


def test_build_mux_command_includes_video_and_audio(tmp_path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "mixed.wav"
    output = tmp_path / "out.mp4"
    cmd = build_mux_command("ffmpeg", video, audio, output)
    assert str(video) in cmd
    assert str(audio) in cmd
    assert str(output) in cmd
    assert "copy" in cmd  # c:v copy
    assert "aac" in cmd   # c:a aac


def test_build_mux_command_overwrite_flag(tmp_path):
    cmd = build_mux_command(
        "ffmpeg", tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    )
    assert "-y" in cmd


def test_build_mux_command_maps_streams(tmp_path):
    cmd = build_mux_command(
        "ffmpeg", tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4"
    )
    assert "0:v:0" in cmd
    assert "1:a:0" in cmd


# ---------------------------------------------------------------------------
# mix.py — per-segment volume/fade in filter graph
# ---------------------------------------------------------------------------


def _make_track(
    seg_id: int = 0,
    delay_ms: int = 1000,
    atempo: float = 1.0,
    duration: float = 0.5,
    volume: float = 1.0,
    fade_in_ms: int = 0,
    fade_out_ms: int = 0,
) -> MixSpeechTrack:
    return MixSpeechTrack(
        id=seg_id,
        start=1.0,
        end=2.0,
        delay_ms=delay_ms,
        atempo=atempo,
        generated_duration=duration,
        tts_path=Path(f"/fake/{seg_id:04d}.wav"),
        volume=volume,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
    )


def test_mix_filter_no_extras_matches_baseline():
    track = _make_track()
    result = build_mix_filter_complex([track], [], 0.0)
    assert "volume=" not in result
    assert "afade=" not in result


def test_mix_filter_applies_volume():
    track = _make_track(volume=0.75)
    result = build_mix_filter_complex([track], [], 0.0)
    assert "volume=0.7500" in result


def test_mix_filter_no_volume_when_default():
    track = _make_track(volume=1.0)
    result = build_mix_filter_complex([track], [], 0.0)
    assert "volume=" not in result


def test_mix_filter_applies_fade_in():
    track = _make_track(delay_ms=1000, fade_in_ms=50)
    result = build_mix_filter_complex([track], [], 0.0)
    assert "afade=t=in:st=1.0000:d=0.0500" in result


def test_mix_filter_applies_fade_out():
    track = _make_track(delay_ms=1000, atempo=1.0, duration=0.5, fade_out_ms=100)
    result = build_mix_filter_complex([track], [], 0.0)
    # playback_dur=0.5, fade_out_start = 1.0 + max(0, 0.5-0.1) = 1.4
    assert "afade=t=out:st=1.4000:d=0.1000" in result


def test_mix_filter_no_fades_when_zero():
    track = _make_track(fade_in_ms=0, fade_out_ms=0)
    result = build_mix_filter_complex([track], [], 0.0)
    assert "afade=" not in result


# ---------------------------------------------------------------------------
# export_project — success path (mocked subprocess)
# ---------------------------------------------------------------------------


def test_export_project_success(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"

    stages: list[str] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        # Simulate the mix command writing a wav and the mux command writing an mp4
        if str(output_path).endswith(".mp4") and "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            # mix command — write a temp wav (find the output path from cmd)
            out = Path(cmd[-1])
            out.write_bytes(make_valid_wav_bytes())
        return result

    with patch("subprocess.run", side_effect=fake_run):
        result = export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=output_path),
            on_stage=lambda s: stages.append(s.value),
        )

    assert result.output_path == output_path
    assert ExportStage.PREPARING.value in stages
    assert ExportStage.MIXING_AUDIO.value in stages
    assert ExportStage.RENDERING_VIDEO.value in stages
    assert ExportStage.FINALIZING.value in stages
    assert ExportStage.COMPLETED.value in stages


def test_export_project_cleans_up_temp_wav_on_success(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    temp_files_created: list[Path] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
            temp_files_created.append(out)
        return result

    with patch("subprocess.run", side_effect=fake_run):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=output_path),
        )

    for tmp_wav in temp_files_created:
        assert not tmp_wav.exists(), f"temp wav not cleaned up: {tmp_wav}"


def test_export_project_missing_video_raises(tmp_path):
    project = _make_project(tmp_path, with_video=False)
    with pytest.raises(ExportError, match="source video"):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=tmp_path / "out.mp4"),
        )


def test_export_project_missing_audio_raises(tmp_path):
    project = _make_project(tmp_path)
    project.audio_path.unlink()
    with pytest.raises(ExportError, match="source audio"):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=tmp_path / "out.mp4"),
        )


def test_export_project_ffmpeg_mix_failure_raises(tmp_path):
    project = _make_project(tmp_path)

    def fake_run(cmd, **kwargs):
        if "-c:v" not in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="mix error")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ExportError, match="audio mix failed"):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=tmp_path / "out.mp4"),
            )


def test_export_project_ffmpeg_mux_failure_raises(tmp_path):
    project = _make_project(tmp_path)

    def fake_run(cmd, **kwargs):
        if "-c:v" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="mux error")
        out = Path(cmd[-1])
        out.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ExportError, match="video render failed"):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=tmp_path / "out.mp4"),
            )


def test_export_project_cancel_before_mix_raises(tmp_path):
    project = _make_project(tmp_path)
    with pytest.raises(ExportError, match="cancelled"):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=tmp_path / "out.mp4"),
            is_cancelled=lambda: True,
        )


def test_export_project_cancel_removes_partial_output(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    def is_cancelled():
        # Cancel only after both ffmpeg calls (during FINALIZING)
        return call_count >= 2

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ExportError, match="cancelled"):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=output_path),
                is_cancelled=is_cancelled,
            )

    assert not output_path.exists(), "partial output should be removed on cancel"


def test_export_project_no_tts_files_raises(tmp_path):
    project = _make_project(tmp_path)
    for wav in project.tts_directory.glob("*.wav"):
        wav.unlink()
    with pytest.raises(ExportError, match="no synthesized speech"):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=tmp_path / "out.mp4"),
        )


def test_export_project_creates_output_dir(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "exports" / "subdir" / "out.mp4"

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            out.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        result = export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=output_path),
        )
    assert result.output_path == output_path


# ---------------------------------------------------------------------------
# ExportJob / ExportRunner (background worker)
# ---------------------------------------------------------------------------


def test_export_job_emits_finished_on_success(qapp, tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    results: list[ExportResult] = []
    loop = QEventLoop()

    job = ExportJob(
        project=project,
        editables={},
        tool_config=_default_tool_config(),
        options=ExportOptions(output_path=output_path),
    )

    def on_finished(result):
        results.append(result)
        loop.quit()

    def on_error(msg):
        loop.quit()

    job.signals.finished.connect(on_finished)
    job.signals.errorOccurred.connect(on_error)

    with patch("subprocess.run", side_effect=fake_run):
        runner = ExportRunner()
        runner.submit(job)
        loop.exec()

    assert len(results) == 1
    assert results[0].output_path == output_path


def test_export_job_emits_error_on_missing_video(qapp, tmp_path):
    project = _make_project(tmp_path, with_video=False)

    errors: list[str] = []
    loop = QEventLoop()

    job = ExportJob(
        project=project,
        editables={},
        tool_config=_default_tool_config(),
        options=ExportOptions(output_path=tmp_path / "out.mp4"),
    )
    job.signals.finished.connect(lambda _: loop.quit())
    job.signals.errorOccurred.connect(lambda msg: (errors.append(msg), loop.quit()))

    runner = ExportRunner()
    runner.submit(job)
    loop.exec()

    assert len(errors) == 1
    assert "source video" in errors[0]


def test_export_runner_is_running_while_active(qapp, tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"

    loop = QEventLoop()

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    job = ExportJob(
        project=project,
        editables={},
        tool_config=_default_tool_config(),
        options=ExportOptions(output_path=output_path),
    )
    job.signals.finished.connect(lambda _: loop.quit())
    job.signals.errorOccurred.connect(lambda _: loop.quit())

    runner = ExportRunner()
    with patch("subprocess.run", side_effect=fake_run):
        runner.submit(job)
        assert runner.is_running is True
        loop.exec()

    assert runner.is_running is False


def test_export_job_cancel_propagates(qapp, tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"

    errors: list[str] = []
    loop = QEventLoop()

    job = ExportJob(
        project=project,
        editables={},
        tool_config=_default_tool_config(),
        options=ExportOptions(output_path=output_path),
    )
    job.signals.errorOccurred.connect(lambda msg: (errors.append(msg), loop.quit()))
    job.signals.finished.connect(lambda _: loop.quit())

    job.cancel()

    runner = ExportRunner()
    runner.submit(job)
    loop.exec()

    assert any("cancel" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# ExportProgressDialog
# ---------------------------------------------------------------------------


def test_export_progress_dialog_stage_updates_label(qapp):
    dialog = ExportProgressDialog()
    dialog.on_stage_changed(ExportStage.MIXING_AUDIO.value)
    assert "Mixing audio" in dialog._stage_label.text()


def test_export_progress_dialog_stage_advances_progress_bar(qapp):
    dialog = ExportProgressDialog()
    dialog.on_stage_changed(ExportStage.RENDERING_VIDEO.value)
    assert dialog._progress_bar.value() > 0


def test_export_progress_dialog_on_finished_shows_success(qapp, tmp_path):
    dialog = ExportProgressDialog()
    result = ExportResult(output_path=tmp_path / "out.mp4")
    dialog.on_finished(result)
    assert "Complete" in dialog.windowTitle()
    assert not dialog._open_file_button.isHidden()
    assert not dialog._open_folder_button.isHidden()
    assert not dialog._close_button.isHidden()
    assert dialog._cancel_button.isHidden()


def test_export_progress_dialog_on_error_shows_error(qapp):
    dialog = ExportProgressDialog()
    dialog.on_error("ffmpeg crashed")
    assert "Failed" in dialog.windowTitle()
    assert "ffmpeg crashed" in dialog._stage_label.text()
    assert not dialog._close_button.isHidden()
    assert dialog._cancel_button.isHidden()


def test_export_progress_dialog_cancel_sets_flag(qapp):
    dialog = ExportProgressDialog()
    assert not dialog.is_cancelled()
    dialog._on_cancel()
    assert dialog.is_cancelled()
