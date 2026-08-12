from __future__ import annotations

import json

from automatedub_studio.performance import EditorPerformanceDiagnostics


def test_editor_performance_diagnostics_are_opt_in(monkeypatch, tmp_path):
    diagnostics = EditorPerformanceDiagnostics(tmp_path)
    diagnostics.mark("project_loaded")
    diagnostics.write(editor_ready=True)

    assert not (tmp_path / "pipeline" / "debug" / "editor_performance.json").exists()

    monkeypatch.setenv("AUTOMATEDUB_PERF_DIAGNOSTICS", "1")
    diagnostics = EditorPerformanceDiagnostics(tmp_path)
    diagnostics.mark("project_loaded", segments=3)
    diagnostics.write(editor_ready=True, playback={"audio_players": 5})

    payload = json.loads(
        (tmp_path / "pipeline" / "debug" / "editor_performance.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["editor_ready"] is True
    assert payload["events"][0]["stage"] == "project_loaded"
    assert payload["playback"]["audio_players"] == 5
