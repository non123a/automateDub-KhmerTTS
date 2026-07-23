from __future__ import annotations

from automatedub.vertical_slice.paths import audio_output_path, transcript_output_path


def test_audio_output_path_uses_vs0_filename(tmp_path):
    assert audio_output_path(tmp_path / "output") == tmp_path / "output" / "audio.wav"


def test_transcript_output_path_uses_vs1_filename(tmp_path):
    assert transcript_output_path(tmp_path / "output") == tmp_path / "output" / "transcript.json"
