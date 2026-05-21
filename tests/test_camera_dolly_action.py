"""Tests for the camera_dolly action."""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_camera_dolly_missing_cameras_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bpy = type(
        "B",
        (),
        {
            "context": type("C", (), {"scene": type("S", (), {"objects": {}})()})(),
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
                        "type": "camera_dolly",
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
def test_real_camera_dolly_places_dolly_camera_and_markers() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_dolly",
                        "from_camera": "wide",
                        "to_camera": "close_student",
                        "start": 0,
                        "end": 2,
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
    assert placed["type"] == "camera_dolly"
    assert placed["from_camera"] == "wide"
    assert placed["to_camera"] == "close_student"
    assert placed["dolly_camera"] == "veraframe_dolly_a1"
    assert placed["start_marker"] == "veraframe_dolly_start_a1"
    assert placed["end_marker"] == "veraframe_dolly_end_a1"
    assert placed["frame_start"] == 0
    assert placed["frame_end"] == 48


@needs_blender
def test_real_camera_dolly_unknown_camera_is_skipped() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_dolly",
                        "from_camera": "wide",
                        "to_camera": "ghost_camera",
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
    assert "not a camera" in result["skipped"][0]["reason"]
