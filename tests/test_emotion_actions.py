"""Tests for the emotion blendshape actions (`smile`, `frown`, `blink`).

X-Bot (the bundled test character) has no shape keys, so the integration
test confirms the actions execute cleanly and report `noop: True`. A future
character with VRM blendshapes will return non-empty `affected_meshes`.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


@pytest.mark.parametrize("atype", ["smile", "frown", "blink"])
def test_emotion_skips_when_character_not_loaded(
    monkeypatch: pytest.MonkeyPatch, atype: str
) -> None:
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
                        "type": atype,
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
    assert result["skipped"][0]["type"] == atype


# --- Integration --------------------------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())


def _emotion_timeline(atype: str) -> dict:
    return {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": atype,
                        "character": "student",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }


@needs_blender
@pytest.mark.parametrize(
    "atype,expected_shape_key",
    [
        ("smile", "Joy"),
        ("frown", "Sorrow"),
        ("blink", "Blink"),
    ],
)
def test_real_emotion_executes_with_xbot_as_noop(atype: str, expected_shape_key: str) -> None:
    """X-Bot has no shape keys so the action should execute but be a no-op."""
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call("load_character", fbx_path=CHAR_PATH, spawn_point="center_room", handle="student")
        result = h.call("execute_timeline", timeline=_emotion_timeline(atype), asset_paths={})

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == atype
    assert placed["shape_key"] == expected_shape_key
    assert placed["noop"] is True
    assert placed["affected_meshes"] == []
