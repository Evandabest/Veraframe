"""Tests for the walk_to action and its dispatch.

Unit tests cover the dispatch error paths (missing character, missing target,
missing asset path). Integration tests run against real Blender 5.1.2.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit (no Blender) --------------------------------------------------------


def test_walk_to_unknown_target_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the target name resolves to no object, walk_to is skipped cleanly."""
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
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "nowhere",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    # Stub the _index_characters_by_handle helper to return a fake character.
    monkeypatch.setattr(
        action_executor, "_index_characters_by_handle", lambda: {"student": object()}
    )
    result = action_executor.execute_timeline(
        timeline=timeline, asset_paths={"walk_in_place": "/x"}
    )
    assert result["executed"] == []
    # Filter to just walk_to skips — the camera suggester may inject a
    # track_subject for the walker which fails for unrelated reasons (no
    # real bpy in this test), and that's not what we're testing here.
    walk_skips = [s for s in result["skipped"] if s["type"] == "walk_to"]
    assert len(walk_skips) == 1
    assert "not found" in walk_skips[0]["reason"]


def test_walk_to_no_asset_path_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """If `walk_in_place` isn't in asset_paths, walk_to is skipped."""
    # Build a fake scene with a `door` empty object.
    target = type("O", (), {"location": type("L", (), {"x": 0.0, "y": 0.0, "z": 0.0})()})()
    fake_scene = type("S", (), {"objects": {"door": target}, "name": "fake"})()
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
                        "type": "walk_to",
                        "character": "student",
                        "target": "door",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "no walk_in_place" in result["skipped"][0]["reason"]


# --- Integration (real Blender) -----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())
WALK_PATH = str(Path("assets/animations/walk_in_place/walk_in_place.fbx").resolve())
IDLE_PATH = str(Path("assets/animations/idle/animation.fbx").resolve())


def _walk_timeline(target: str, start: float = 0.0, end: float = 2.0) -> dict:
    return {
        "shots": [
            {
                "id": "s1",
                "start": start,
                "end": end,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": target,
                        "start": start,
                        "end": end,
                    }
                ],
            }
        ]
    }


@needs_blender
def test_real_walk_to_places_strip_and_translation() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        result = h.call(
            "execute_timeline",
            timeline=_walk_timeline("robot_station", 0, 4),
            asset_paths={"walk_in_place": WALK_PATH},
        )

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "walk_to"
    assert placed["start_location"] == [0.0, 5.0, 0.0]  # door
    assert placed["end_location"] == [0.0, -3.0, 0.0]  # robot_station
    assert placed["track"] == "veraframe_walk_a1"
    assert placed["frame_start"] == 0
    assert placed["extrapolation"] == "NOTHING"
    # The walk cycle must repeat enough times to span the requested duration,
    # otherwise the leg animation freezes and the character slides. Walking
    # is ~32 frames; a 4-second (96-frame) walk needs ~3 cycles.
    assert placed["repeat"] >= 2.5, f"walk did not loop enough times: repeat={placed['repeat']}"


@needs_blender
def test_real_walk_to_unknown_target_skips() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        result = h.call(
            "execute_timeline",
            timeline=_walk_timeline("rooftop", 0, 2),
            asset_paths={"walk_in_place": WALK_PATH},
        )

    assert result["executed"] == []
    assert "not found" in result["skipped"][0]["reason"]


@needs_blender
def test_real_walk_then_idle_body_strips_do_not_hold_backwards() -> None:
    """A later idle must not hold its first pose backward over a walk."""
    from planner import daemon_runner

    timeline = _walk_timeline("center_room", 0, 4)
    timeline["shots"][0]["end"] = 6
    timeline["shots"][0]["actions"].append(
        {
            "id": "a2",
            "type": "idle",
            "character": "student",
            "start": 4,
            "end": 6,
        }
    )

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        result = h.call(
            "execute_timeline",
            timeline=timeline,
            asset_paths={"walk_in_place": WALK_PATH, "idle": IDLE_PATH},
        )

    assert result["skipped"] == []
    by_id = {entry["id"]: entry for entry in result["executed"]}
    assert by_id["a1"]["type"] == "walk_to"
    assert by_id["a1"]["extrapolation"] == "NOTHING"
    assert by_id["a2"]["type"] == "idle"
    assert by_id["a2"]["extrapolation"] == "NOTHING"


@needs_blender
def test_real_sequential_walks_start_from_previous_target() -> None:
    from planner import daemon_runner

    timeline = _walk_timeline("robot_station", 0, 4)
    timeline["shots"][0]["end"] = 8
    timeline["shots"][0]["actions"].append(
        {
            "id": "a2",
            "type": "walk_to",
            "character": "student",
            "target": "center_room",
            "start": 4,
            "end": 8,
        }
    )

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        result = h.call(
            "execute_timeline",
            timeline=timeline,
            asset_paths={"walk_in_place": WALK_PATH},
        )

    assert result["skipped"] == []
    by_id = {entry["id"]: entry for entry in result["executed"]}
    assert by_id["a1"]["start_location"] == [0.0, 5.0, 0.0]
    assert by_id["a1"]["end_location"] == [0.0, -3.0, 0.0]
    assert by_id["a2"]["start_location"] == [0.0, -3.0, 0.0]
    assert by_id["a2"]["end_location"] == [0.0, 0.0, 0.0]


@needs_blender
def test_real_reset_then_walk_does_not_crash_on_cached_action() -> None:
    """Regression: a `reset` must invalidate the action cache so the next
    walk_to dispatch re-imports the FBX instead of dereferencing a freed
    Action ("StructRNA of type Action has been removed")."""
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        first = h.call(
            "execute_timeline",
            timeline=_walk_timeline("center_room", 0, 2),
            asset_paths={"walk_in_place": WALK_PATH},
        )
        assert first["executed"][0]["type"] == "walk_to"

        h.call("reset")
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door", handle="student")
        second = h.call(
            "execute_timeline",
            timeline=_walk_timeline("center_room", 0, 2),
            asset_paths={"walk_in_place": WALK_PATH},
        )

    assert second["skipped"] == []
    assert second["executed"][0]["type"] == "walk_to"
