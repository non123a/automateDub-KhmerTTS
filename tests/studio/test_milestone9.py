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
from PySide6.QtCore import QCoreApplication, QEventLoop, QSize

from automatedub.config import ToolConfig
from automatedub.vertical_slice.mix import MixSpeechTrack, build_mix_filter_complex
from automatedub_studio.backend.export_service import (
    ExportEncoderCapabilities,
    ExportError,
    ExportOptions,
    ExportResult,
    ExportStage,
    ExportStreamSummary,
    FFmpegProgress,
    _run_ffmpeg_with_progress,
    build_export_speech_tracks,
    build_export_timeline_speech_tracks,
    build_mux_command,
    build_tts_only_mix_command,
    choose_export_video_encoder,
    export_project,
    probe_export_system_capabilities,
    probe_output_streams,
    probe_stream_copy_capability,
)
from automatedub_studio.backend.export_worker import ExportJob, ExportRunner
from automatedub_studio.project.editable_project import EditableSegment
from automatedub_studio.project.models import Project, Segment
from automatedub_studio.timeline.timeline_clip import (
    KHMER_TTS_TRACK_ID,
    ORIGINAL_AUDIO_TRACK_ID,
    Timeline,
    TimelineClip,
)
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


def test_build_export_timeline_speech_tracks_excludes_reference_only_clips(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    tts_path = project.tts_directory / "0000.wav"
    timeline = Timeline.default()
    reference = timeline.track_by_id(ORIGINAL_AUDIO_TRACK_ID)
    tts = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    assert reference is not None and tts is not None
    reference.clips.append(
        TimelineClip(
            id="original:0",
            track_id=ORIGINAL_AUDIO_TRACK_ID,
            start_time=0.0,
            end_time=1.0,
            source_path=project.extracted_audio_path,
        )
    )
    tts.clips.extend(
        [
            TimelineClip(
                id="khmer:0",
                track_id=KHMER_TTS_TRACK_ID,
                start_time=0.0,
                end_time=1.0,
                source_path=tts_path,
            ),
            TimelineClip(
                id="khmer:0:copy:1",
                track_id=KHMER_TTS_TRACK_ID,
                start_time=0.5,
                end_time=1.5,
                source_path=tts_path,
            ),
        ]
    )

    tracks = build_export_timeline_speech_tracks(timeline, _default_tool_config())

    assert [track.tts_path for track in tracks] == [tts_path, tts_path]
    assert [track.delay_ms for track in tracks] == [0, 500]


def test_build_export_timeline_speech_tracks_skips_muted_clip(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    timeline = Timeline.default()
    tts = timeline.track_by_id(KHMER_TTS_TRACK_ID)
    assert tts is not None
    tts.clips.append(
        TimelineClip(
            id="khmer:0",
            track_id=KHMER_TTS_TRACK_ID,
            start_time=0.0,
            end_time=1.0,
            source_path=project.tts_directory / "0000.wav",
            muted=True,
        )
    )

    assert build_export_timeline_speech_tracks(timeline, _default_tool_config()) == []


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


def test_build_mux_command_can_reencode_video_to_h264(tmp_path):
    cmd = build_mux_command(
        "ffmpeg",
        tmp_path / "v.mp4",
        tmp_path / "a.wav",
        tmp_path / "o.mp4",
        video_encoder="libx264",
        video_quality="High",
    )

    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-crf") + 1] == "18"


def test_av1_source_selects_h264_export_encoder():
    summary = ExportStreamSummary(
        video_streams=1,
        audio_streams=1,
        raw_streams=[{"codec_type": "video", "codec_name": "av1"}],
    )

    encoder, reason = choose_export_video_encoder(summary, "h264")

    assert encoder == "libx264"
    assert "av1" in reason


def test_h264_source_can_be_stream_copied():
    summary = ExportStreamSummary(
        video_streams=1,
        audio_streams=1,
        raw_streams=[{"codec_type": "video", "codec_name": "h264"}],
    )

    encoder, _reason = choose_export_video_encoder(
        summary,
        "copy",
        video_preset="fastest",
    )

    assert encoder == "copy"


def test_h265_preset_requires_a_supported_encoder():
    summary = ExportStreamSummary(video_streams=1, audio_streams=1, raw_streams=[])

    with pytest.raises(ExportError, match="no supported H.265 encoder"):
        choose_export_video_encoder(
            summary,
            "h265",
            video_preset="high_compression_h265",
            encoder_capabilities=ExportEncoderCapabilities("libx264", None),
        )


def test_export_system_capabilities_detects_encoders_and_mp4_muxer():
    def fake_run(command, **_kwargs):
        if "-version" in command:
            return MagicMock(stdout="ffmpeg version test-build\n")
        if "-encoders" in command:
            return MagicMock(
                stdout=" V..... libx264 H.264\n V..... hevc_videotoolbox HEVC\n"
            )
        return MagicMock(stdout="  E  mp4 MP4\n  E  mov MOV\n")

    with patch("subprocess.run", side_effect=fake_run):
        capabilities = probe_export_system_capabilities("ffmpeg")

    assert capabilities.ffmpeg_version == "ffmpeg version test-build"
    assert capabilities.h264_encoder == "libx264"
    assert capabilities.h265_encoder == "hevc_videotoolbox"
    assert capabilities.supports_mp4_muxing


def test_tts_only_mix_does_not_use_pipeline_audio(tmp_path):
    project = _make_project(tmp_path, segment_count=1)
    tracks = build_export_speech_tracks(
        project.segments, {}, project.tts_directory, _default_tool_config()
    )

    command = build_tts_only_mix_command("ffmpeg", tracks, tmp_path / "mixed.wav")

    assert str(project.audio_path) not in command
    assert "anullsrc=channel_layout=mono:sample_rate=16000" in command


def test_compatible_preset_reencodes_h264_source_to_h264():
    summary = ExportStreamSummary(
        video_streams=1,
        audio_streams=1,
        raw_streams=[{"codec_type": "video", "codec_name": "h264"}],
    )

    encoder, reason = choose_export_video_encoder(
        summary,
        "h264",
        video_preset="compatible_h264",
    )

    assert encoder == "libx264"
    assert "Compatible" in reason


def test_high_compression_preset_uses_h265_encoder():
    summary = ExportStreamSummary(
        video_streams=1,
        audio_streams=1,
        raw_streams=[{"codec_type": "video", "codec_name": "h264"}],
    )

    encoder, reason = choose_export_video_encoder(
        summary,
        "h265",
        video_preset="high_compression_h265",
    )

    assert encoder == "libx265"
    assert "H.265" in reason


def test_build_mux_command_can_reencode_video_to_h265(tmp_path):
    cmd = build_mux_command(
        "ffmpeg",
        tmp_path / "v.mp4",
        tmp_path / "a.wav",
        tmp_path / "o.mp4",
        video_encoder="libx265",
        video_quality="Small File",
    )

    assert cmd[cmd.index("-c:v") + 1] == "libx265"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-crf") + 1] == "30"
    if "-allow_sw" in cmd:
        assert cmd[cmd.index("-allow_sw") + 1] == "1"


def test_hardware_h264_balanced_uses_source_relative_bitrate(tmp_path):
    balanced = build_mux_command(
        "ffmpeg",
        tmp_path / "v.mp4",
        tmp_path / "a.wav",
        tmp_path / "o.mp4",
        video_encoder="h264_videotoolbox",
        video_quality="Balanced",
        source_video_bitrate=1_400_000,
    )

    small = build_mux_command(
        "ffmpeg",
        tmp_path / "v.mp4",
        tmp_path / "a.wav",
        tmp_path / "small.mp4",
        video_encoder="h264_videotoolbox",
        video_quality="Small File",
        source_video_bitrate=1_400_000,
    )

    assert balanced[balanced.index("-b:v") + 1] == "1400000"
    assert small[small.index("-b:v") + 1] == "980000"
    assert "5M" not in balanced


def test_hevc_videotoolbox_allows_software_fallback(tmp_path):
    cmd = build_mux_command(
        "ffmpeg",
        tmp_path / "v.mp4",
        tmp_path / "a.wav",
        tmp_path / "o.mp4",
        video_encoder="hevc_videotoolbox",
        video_quality="Balanced",
    )

    assert cmd[cmd.index("-allow_sw") + 1] == "1"


def test_stream_copy_capability_uses_ffmpeg_result(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    supported, reason = probe_stream_copy_capability("ffmpeg", source)

    assert supported
    assert "verified" in reason


def test_ffmpeg_progress_reports_frame_rate_time_size_and_speed(tmp_path):
    output = tmp_path / "progress.mp4"
    progress: list[FFmpegProgress] = []

    _run_ffmpeg_with_progress(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-t",
            "0.2",
            "-i",
            "testsrc=size=64x64:rate=5",
            "-c:v",
            "libx264",
            "-f",
            "mp4",
            str(output),
        ],
        0.2,
        progress.append,
    )

    assert output.is_file()
    assert progress[-1].percent == 100
    assert progress[-1].frame is not None
    assert progress[-1].elapsed_seconds is not None
    assert progress[-1].output_size_bytes and progress[-1].output_size_bytes > 0


def test_probe_output_streams_counts_video_and_audio(monkeypatch, tmp_path):
    output = tmp_path / "out.mp4"

    def fake_run(command, check, capture_output, text):
        assert "-show_entries" in command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "streams": [
                        {"index": 0, "codec_type": "video", "codec_name": "h264"},
                        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = probe_output_streams("ffprobe", output)

    assert summary.video_streams == 1
    assert summary.audio_streams == 1


def test_probe_output_streams_detects_audio_only_output(monkeypatch, tmp_path):
    output = tmp_path / "out.mp4"

    def fake_run(command, check, capture_output, text):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac"}]}
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    summary = probe_output_streams("ffprobe", output)

    assert summary.video_streams == 0
    assert summary.audio_streams == 1


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


def test_export_project_places_mix_wav_in_supplied_short_workspace(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "very" / "long" / "destination" / "out.mp4"
    workspace = tmp_path / "w"
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        target = Path(command[-1])
        if "-c:v" in command:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            target.write_bytes(make_valid_wav_bytes())
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=output_path),
            intermediate_directory=workspace,
        )

    mix_command = next(command for command in commands if "-filter_complex" in command)
    assert Path(mix_command[-1]).parent == workspace
    assert not list(workspace.glob("*.wav"))


def test_export_project_rejects_audio_only_mux_output(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "-show_entries" in cmd:
            result.stdout = json.dumps(
                {"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac"}]}
            )
            result.stderr = ""
            return result
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ExportError, match="missing required stream.*video"):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=output_path),
            )

    debug = json.loads(
        (project.project_path / "exports" / "last_export_debug.json").read_text(
            encoding="utf-8"
        )
    )
    assert debug["input_video"] == str(project.export_video_path)
    assert debug["mapped_streams"] == ["0:v:0", "1:a:0"]
    assert debug["output_streams"]["video"] == 0
    assert debug["output_streams"]["audio"] == 1


def test_export_project_reencodes_av1_source_to_h264(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    mux_commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "-show_entries" in cmd:
            if Path(cmd[-1]) == project.export_video_path:
                result.stdout = json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "video",
                                "codec_name": "av1",
                                "width": 1920,
                                "height": 1080,
                            },
                            {"index": 1, "codec_type": "audio", "codec_name": "opus"},
                        ]
                    }
                )
            else:
                result.stdout = json.dumps(
                    {
                        "streams": [
                            {
                                "index": 0,
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                            },
                            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
                        ]
                    }
                )
            result.stderr = ""
            return result
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            mux_commands.append(list(cmd))
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return result

    with patch("subprocess.run", side_effect=fake_run):
        export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(output_path=output_path, video_codec="h264"),
        )

    assert mux_commands
    mux = mux_commands[0]
    assert mux[mux.index("-c:v") + 1] == "libx264"
    assert mux[mux.index("-pix_fmt") + 1] == "yuv420p"
    debug = json.loads(
        (project.project_path / "exports" / "last_export_debug.json").read_text(
            encoding="utf-8"
        )
    )
    assert debug["video_encoder"] == "libx264"
    assert debug["source_streams"]["raw"][0]["codec_name"] == "av1"
    assert debug["output_streams"]["raw"][0]["codec_name"] == "h264"


def test_small_file_preset_exports_playable_h265_mp4(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    mux_commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "-show_entries" in cmd:
            codec = "h264" if Path(cmd[-1]) == project.export_video_path else "hevc"
            result.stdout = json.dumps(
                {
                    "streams": [
                        {"index": 0, "codec_type": "video", "codec_name": codec},
                        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
                    ]
                }
            )
            result.stderr = ""
            return result
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            mux_commands.append(list(cmd))
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        else:
            out.write_bytes(make_valid_wav_bytes())
        return result

    with patch("subprocess.run", side_effect=fake_run):
        result = export_project(
            project=project,
            editables={},
            tool_config=_default_tool_config(),
            options=ExportOptions(
                output_path=output_path,
                video_codec="h265",
                video_quality="Small File",
                video_preset="high_compression_h265",
            ),
        )

    assert result.output_path == output_path
    assert mux_commands[0][mux_commands[0].index("-c:v") + 1] == "libx265"
    assert mux_commands[0][mux_commands[0].index("-crf") + 1] == "30"
    debug = json.loads(
        (project.project_path / "exports" / "last_export_debug.json").read_text(
            encoding="utf-8"
        )
    )
    assert debug["output_streams"]["video"] == 1
    assert debug["output_streams"]["audio"] == 1


def test_export_project_cleans_up_temp_wav_on_success(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    temp_files_created: list[Path] = []

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if cmd[-1] == "-encoders":
            return result
        if "-show_entries" in cmd:
            return result
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
            options=ExportOptions(
                output_path=tmp_path / "out.mp4",
                include_original_movie_audio=True,
            ),
        )


def test_export_project_ffmpeg_mix_failure_raises(tmp_path):
    project = _make_project(tmp_path)

    def fake_run(cmd, **kwargs):
        if cmd[-1] == "-encoders":
            return MagicMock(returncode=0)
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


def test_export_project_enospc_reports_diagnostics_and_cleans_temp_wav(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    temp_paths: list[Path] = []

    def fake_run(cmd, **kwargs):
        if cmd[-1] == "-encoders":
            return MagicMock(returncode=0)
        if "-filter_complex" in cmd:
            temporary = Path(cmd[-1])
            temporary.write_bytes(b"partial wav")
            temp_paths.append(temporary)
            raise subprocess.CalledProcessError(
                1, cmd, stderr="Error submitting a packet to the muxer: No space left on device"
            )
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ExportError, match="not enough disk space"):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=output_path),
            )

    assert temp_paths and all(not path.exists() for path in temp_paths)
    debug = json.loads(
        (project.project_path / "exports" / "last_export_debug.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostics = debug["diagnostics"]
    assert diagnostics["phase"] == "audio_mix"
    assert diagnostics["tts_input_count"] == len(project.segments)
    assert diagnostics["audio_input_count"] == len(project.segments)
    assert diagnostics["temporary_directory"] == str(tmp_path)
    assert diagnostics["free_space_bytes"] >= 0
    assert diagnostics["estimated_temp_bytes"] > 0
    assert diagnostics["temporary_file_size_before_cleanup_bytes"] == len(b"partial wav")
    assert diagnostics["temporary_file_cleaned"] is True


def test_export_project_repeated_exports_leave_no_mix_wavs(tmp_path):
    project = _make_project(tmp_path)
    output_path = tmp_path / "out.mp4"
    temporary_paths: list[Path] = []

    def fake_run(cmd, **kwargs):
        if "-filter_complex" not in cmd and "-c:v" not in cmd:
            return MagicMock(returncode=0)
        out = Path(cmd[-1])
        if "-c:v" in cmd:
            out.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        elif "-filter_complex" in cmd:
            out.write_bytes(make_valid_wav_bytes())
            temporary_paths.append(out)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        for _ in range(2):
            export_project(
                project=project,
                editables={},
                tool_config=_default_tool_config(),
                options=ExportOptions(output_path=output_path),
            )

    assert len(temporary_paths) == 2
    assert all(not path.exists() for path in temporary_paths)


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


@pytest.mark.parametrize("size", [QSize(420, 220), QSize(520, 280), QSize(900, 620)])
def test_export_progress_dialog_reflows_with_visible_cancel(qapp, size):
    dialog = ExportProgressDialog()
    dialog.resize(size)
    dialog.show()
    QCoreApplication.processEvents()

    assert dialog._cancel_button.geometry().bottom() <= dialog.contentsRect().bottom()
    assert dialog.content_scroll.geometry().bottom() < dialog._cancel_button.geometry().top()
    assert dialog._progress_bar.width() > 0
