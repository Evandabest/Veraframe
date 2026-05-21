"""Tests for the set_lighting action."""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_set_lighting_missing_preset_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bpy = type(
        "B",
        (),
        {
            "context": type("C", (), {"scene": type("S", (), {"objects": []})()})(),
            "data": type("D", (), {"objects": []})(),
        },
    )
    monkeypatch.setattr(action_executor, "bpy", fake_bpy)
    monkeypatch.setattr(action_executor, "_index_characters_by_handle", lambda: {})
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "set_lighting",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "required" in result["skipped"][0]["reason"]


# --- Integration --------------------------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())


@needs_blender
def test_real_set_lighting_dim_keyframes_every_light() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "set_lighting",
                        "preset": "dim",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call("execute_timeline", timeline=timeline, asset_paths={}, fps=24)

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["preset"] == "dim"
    assert placed["frame_start"] == 0
    assert placed["frame_end"] == 24
    # dark_lab ships with MainLight + KeyLight
    assert len(placed["affected_lights"]) >= 2


@needs_blender
def test_real_set_lighting_unknown_preset_is_skipped() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "set_lighting",
                        "preset": "ultraviolet",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call("execute_timeline", timeline=timeline, asset_paths={}, fps=24)

    assert result["executed"] == []
    assert "unknown preset" in result["skipped"][0]["reason"]
