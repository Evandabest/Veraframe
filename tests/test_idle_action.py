"""Tests for the idle action and `execute_timeline` dispatch.

Unit tests cover dispatch branches (unknown action type, missing character,
missing asset path) using bpy stubs. Integration tests run the real flow
against Blender 5.1.2.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit (bpy unavailable) ---------------------------------------------------


def test_execute_timeline_raises_without_bpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(action_executor, "bpy", None)
    with pytest.raises(action_executor.ExecutorError, match="bpy unavailable"):
        action_executor.execute_timeline(timeline={"shots": []}, asset_paths={})


def test_unknown_action_type_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub bpy.data.objects to be empty so the character index is empty.
    fake_bpy = type("FakeBpy", (), {"data": type("D", (), {"objects": []})()})
    monkeypatch.setattr(action_executor, "bpy", fake_bpy)
    timeline = {
        "shots": [
            {
                "id": "s1",
                "actions": [{"id": "a1", "type": "teleport"}],
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert len(result["skipped"]) == 1
    assert "not yet implemented" in result["skipped"][0]["reason"]


# --- Integration (real Blender) ----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())
IDLE_PATH = str(Path("assets/animations/idle/animation.fbx").resolve())


def _idle_timeline(start: float = 0.0, end: float = 2.0) -> dict:
    return {
        "project": "test",
        "scene": "dark_lab",
        "characters": [{"id": "student", "preset": "student_v1", "spawn": "door"}],
        "shots": [
            {
                "id": "s1",
                "start": start,
                "end": end,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": start,
                        "end": end,
                    }
                ],
            }
        ],
    }


@needs_blender
def test_real_idle_places_nla_strip() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="door",
            handle="student",
        )
        result = h.call(
            "execute_timeline",
            timeline=_idle_timeline(0, 2),
            asset_paths={"idle": IDLE_PATH},
        )

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "idle"
    assert placed["track"] == "veraframe_idle_a1"
    assert placed["frame_start"] == 0
    assert placed["frame_end"] == 48  # 2s × 24fps
    assert result["skipped"] == []


@needs_blender
def test_real_idle_missing_character_skips_gracefully() -> None:
    from planner import daemon_runner

    timeline = _idle_timeline(0, 1)
    # Don't load any character.
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call(
            "execute_timeline",
            timeline=timeline,
            asset_paths={"idle": IDLE_PATH},
        )

    assert result["executed"] == []
    assert len(result["skipped"]) == 1
    assert "not loaded" in result["skipped"][0]["reason"]


@needs_blender
def test_real_idle_missing_asset_path_skips_gracefully() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="door",
            handle="student",
        )
        result = h.call(
            "execute_timeline",
            timeline=_idle_timeline(0, 1),
            asset_paths={},  # no idle path
        )

    assert result["executed"] == []
    assert "no idle animation path" in result["skipped"][0]["reason"]


@needs_blender
def test_real_other_actions_in_timeline_are_skipped() -> None:
    from planner import daemon_runner

    timeline = _idle_timeline(0, 2)
    # Add a not-yet-implemented action alongside the idle.
    timeline["shots"][0]["actions"].append(
        {
            "id": "a2",
            "type": "turn_to",
            "character": "student",
            "target": "center_room",
            "start": 0,
            "end": 2,
        }
    )

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="door",
            handle="student",
        )
        result = h.call(
            "execute_timeline",
            timeline=timeline,
            asset_paths={"idle": IDLE_PATH},
        )

    assert len(result["executed"]) == 1
    assert result["executed"][0]["id"] == "a1"
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["type"] == "turn_to"
