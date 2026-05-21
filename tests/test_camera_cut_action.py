"""Tests for the camera_cut action."""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_camera_cut_without_camera_name_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scene = type("S", (), {"objects": {}, "name": "fake"})()
    fake_bpy = type(
        "B",
        (),
        {
            "context": type("C", (), {"scene": fake_scene})(),
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
                        "type": "camera_cut",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "no camera name" in result["skipped"][0]["reason"]


# --- Integration --------------------------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())


@needs_blender
def test_real_camera_cut_places_timeline_marker() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_cut",
                        "camera": "close_student",
                        "start": 2,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "camera_cut"
    assert placed["camera"] == "close_student"
    assert placed["marker"] == "veraframe_cut_a1"
    assert placed["frame"] == 48  # 2s * 24fps


@needs_blender
def test_real_camera_cut_to_unknown_camera_skips() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_cut",
                        "camera": "ceiling_cam",
                        "start": 0,
                        "end": 0,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert result["executed"] == []
    assert "ceiling_cam" in result["skipped"][0]["reason"]
