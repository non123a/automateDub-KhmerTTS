from __future__ import annotations

from automatedub.vertical_slice.paths import (
    audio_output_path,
    transcript_output_path,
    translation_output_path,
    translation_prompt_output_path,
    tts_error_log_output_path,
    tts_output_dir_path,
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


def test_tts_output_dir_path_uses_vs3_directory(tmp_path):
    assert tts_output_dir_path(tmp_path / "output") == tmp_path / "output" / "tts"


def test_tts_error_log_output_path_uses_vs3_filename(tmp_path):
    assert (
        tts_error_log_output_path(tmp_path / "output")
        == tmp_path / "output" / "tts" / "errors.json"
    )
