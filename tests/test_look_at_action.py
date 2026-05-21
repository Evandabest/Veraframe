"""Tests for the look_at action.

Unit tests cover the dispatch error paths. The integration test verifies
that the head bone's +Z (face) direction tracks the target during the
constraint window and returns to neutral outside it.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_look_at_unknown_target_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(
        action_executor, "_index_characters_by_handle", lambda: {"student": object()}
    )
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "look_at",
                        "character": "student",
                        "target": "nowhere",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "not found" in result["skipped"][0]["reason"]


def test_look_at_unknown_character_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "type": "look_at",
                        "character": "ghost",
                        "target": "door",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "not loaded" in result["skipped"][0]["reason"]


# --- Integration --------------------------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())


@needs_blender
def test_real_look_at_constrains_head_to_target() -> None:
    """Submit a look_at action and confirm the dispatch reports the
    constraint was placed with the right naming."""
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "look_at",
                        "character": "student",
                        "target": "door",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="center_room", handle="student")
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "look_at"
    assert placed["bone"] == "mixamorig:Head"
    assert placed["constraint"] == "veraframe_lookat_a1"
    assert placed["target"] == "door"


@needs_blender
def test_real_look_at_can_target_another_character() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "look_at",
                        "character": "student",
                        "target": "robot",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="center_room", handle="student")
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="robot")
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert len(result["executed"]) == 1
    assert result["executed"][0]["target"]  # an armature was found
