"""Tests for `blender_daemon.character_loader`.

Unit tests run without Blender via the `bpy is None` guard. Integration tests
load the real X Bot character into the dark_lab scene; gated behind
`BLENDER_AVAILABLE=1`.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import character_loader
from blender_daemon.character_loader import CharacterLoadError, load_character

# --- Unit (bpy unavailable) ---------------------------------------------------


def test_load_character_raises_without_bpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(character_loader, "bpy", None)
    with pytest.raises(CharacterLoadError, match="bpy is not available"):
        load_character("/anything", "door")


# --- Integration (real Blender) ----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())


@needs_blender
def test_real_load_character_returns_mixamo_inventory() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door")

    assert result["bone_count"] == 65
    assert result["mixamo_bone_count"] == 65
    assert result["spawn_location"] == [0.0, 5.0, 0.0]  # door
    assert result["mesh_names"] == ["Beta_Joints", "Beta_Surface"]
    assert result["handle"]
    # X Bot has no blendshapes — warning should surface, but the load succeeds.
    assert result["blendshapes"] == []
    assert any("no shape keys" in w for w in result["warnings"])


@needs_blender
def test_real_load_character_custom_handle() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="center_room",
            handle="student",
        )

    assert result["handle"] == "student"
    assert result["spawn_location"] == [0.0, 0.0, 0.0]


@needs_blender
def test_real_load_character_unknown_spawn_point_errors() -> None:
    from planner import daemon_runner
    from planner.daemon_runner import DaemonError

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        with pytest.raises(DaemonError, match="spawn point 'rooftop' not in active scene"):
            h.call("load_character", fbx_path=CHAR_PATH, spawn_point="rooftop")


@needs_blender
def test_real_load_character_missing_file_errors() -> None:
    from planner import daemon_runner
    from planner.daemon_runner import DaemonError

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        with pytest.raises(DaemonError, match="character file not found"):
            h.call("load_character", fbx_path="/tmp/nope.fbx", spawn_point="door")


@needs_blender
def test_real_load_two_characters_get_unique_handles() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        first = h.call("load_character", fbx_path=CHAR_PATH, spawn_point="door")
        second = h.call("load_character", fbx_path=CHAR_PATH, spawn_point="robot_station")

    assert first["handle"] != second["handle"]
