from __future__ import annotations

from automatedub.vertical_slice.paths import (
    audio_output_path,
    transcript_output_path,
    translation_output_path,
    translation_prompt_output_path,
)


def test_audio_output_path_uses_vs0_filename(tmp_path):
    assert audio_output_path(tmp_path / "output") == tmp_path / "output" / "audio.wav"


def test_transcript_output_path_uses_vs1_filename(tmp_path):
    assert transcript_output_path(tmp_path / "output") == tmp_path / "output" / "transcript.json"


def test_translation_output_path_uses_vs2_filename(tmp_path):
    assert translation_output_path(tmp_path / "output") == tmp_path / "output" / "translation.json"


def test_translation_prompt_output_path_uses_vs2_filename(tmp_path):
    assert (
        translation_prompt_output_path(tmp_path / "output")
        == tmp_path / "output" / "translation_prompt.json"
    )
