"""Tests for sit + stand actions."""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_sit_unknown_character_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "type": "sit",
                        "character": "ghost",
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


def test_stand_unknown_character_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
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
                        "type": "stand",
                        "character": "ghost",
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
def test_real_sit_places_strip_with_leg_keyframes() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "sit",
                        "character": "student",
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
    assert placed["type"] == "sit"
    assert placed["track"] == "veraframe_sit_a1"
    assert "mixamorig:LeftUpLeg" in placed["bones"]
    assert "mixamorig:RightLeg" in placed["bones"]


@needs_blender
def test_real_sit_then_stand_chains() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "sit",
                        "character": "student",
                        "start": 0,
                        "end": 1,
                    },
                    {
                        "id": "a2",
                        "type": "stand",
                        "character": "student",
                        "start": 2,
                        "end": 3,
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

    types = [e["type"] for e in result["executed"]]
    assert types == ["sit", "stand"]
