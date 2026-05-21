"""Tests for the turn_to action.

Unit tests cover dispatch error paths. The integration test verifies that
the rotation NLA strip is placed with the expected yaw values.
"""

import math
import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_turn_to_unknown_target_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "type": "turn_to",
                        "character": "student",
                        "target": "nowhere",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "not found" in result["skipped"][0]["reason"]


def test_turn_to_unknown_character_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "type": "turn_to",
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
def test_real_turn_to_places_rotation_strip() -> None:
    """Character at center_room turning to face door (door is at +Y from center).

    Mixamo character naturally faces -Y. Door is at +Y, so the character must
    rotate 180° (π radians) to face it. Expected end_yaw = atan2(0, -5) = π.
    """
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "turn_to",
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
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="center_room",
            handle="student",
        )
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "turn_to"
    assert placed["track"] == "veraframe_turnto_a1"
    assert placed["target"] == "door"
    assert placed["start_yaw"] == pytest.approx(0.0, abs=1e-6)
    # door is at world (0, 5, 0), center_room is (0, 0, 0). dx=0, dy=5.
    # target_yaw = atan2(0, -5) = π
    assert placed["end_yaw"] == pytest.approx(math.pi, abs=1e-6)


@needs_blender
def test_real_turn_to_chained_uses_stored_yaw() -> None:
    """A second turn_to should start from the first turn's end yaw, not 0."""
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "turn_to",
                        "character": "student",
                        "target": "door",
                        "start": 0,
                        "end": 1,
                    },
                    {
                        "id": "a2",
                        "type": "turn_to",
                        "character": "student",
                        "target": "robot_station",
                        "start": 1,
                        "end": 2,
                    },
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="center_room",
            handle="student",
        )
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    by_id = {entry["id"]: entry for entry in result["executed"]}
    assert by_id["a1"]["end_yaw"] == pytest.approx(math.pi, abs=1e-6)
    assert by_id["a2"]["start_yaw"] == pytest.approx(math.pi, abs=1e-6)
