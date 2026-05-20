"""Tests for `planner.registry` — manifest loading and prompt-section rendering."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from planner.registry import (
    DEFAULT_ACTIONS,
    AnimationManifest,
    CharacterManifest,
    Registry,
    SceneManifest,
)

# --- Manifest validation ------------------------------------------------------


def test_scene_manifest_requires_spawn_points_and_cameras() -> None:
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(
            {
                "id": "x",
                "display_name": "X",
                "description": "x",
                "blend_file": "x.blend",
                "spawn_points": [],
                "camera_presets": ["wide"],
            }
        )
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(
            {
                "id": "x",
                "display_name": "X",
                "description": "x",
                "blend_file": "x.blend",
                "spawn_points": ["door"],
                "camera_presets": [],
            }
        )


def test_character_manifest_defaults_to_mixamo_rig() -> None:
    m = CharacterManifest.model_validate(
        {
            "id": "c",
            "display_name": "C",
            "description": "c",
            "mesh_file": "c.fbx",
        }
    )
    assert m.rig_type == "mixamo"
    assert m.face_blendshapes == []


def test_animation_manifest_defaults() -> None:
    m = AnimationManifest.model_validate({"id": "a", "display_name": "A", "fbx_file": "a.fbx"})
    assert m.loop is False
    assert m.applies_to_rig == "mixamo"


# --- Registry loading ---------------------------------------------------------


def test_load_real_assets_directory() -> None:
    r = Registry.load(Path("assets"))
    assert "dark_lab" in r.scenes
    assert "student_v1" in r.characters
    assert "walk_in_place" in r.animations
    assert r.scenes["dark_lab"].spawn_points == ("door", "center_room", "robot_station")
    assert r.characters["student_v1"].rig_type == "mixamo"
    assert "Joy" in r.characters["student_v1"].face_blendshapes


def test_load_nonexistent_directory_returns_empty(tmp_path: Path) -> None:
    r = Registry.load(tmp_path / "does_not_exist")
    assert r.scenes == {}
    assert r.characters == {}
    assert r.animations == {}
    assert r.actions == DEFAULT_ACTIONS


def test_load_empty_subdirs(tmp_path: Path) -> None:
    (tmp_path / "scenes").mkdir()
    (tmp_path / "characters").mkdir()
    (tmp_path / "animations").mkdir()
    r = Registry.load(tmp_path)
    assert r.scenes == {}
    assert r.characters == {}
    assert r.animations == {}


def test_load_skips_directories_without_manifest(tmp_path: Path) -> None:
    scene_dir = tmp_path / "scenes" / "orphan"
    scene_dir.mkdir(parents=True)
    (scene_dir / "notes.txt").write_text("no manifest here")
    r = Registry.load(tmp_path)
    assert r.scenes == {}


def test_load_resolves_paths_relative_to_manifest(tmp_path: Path) -> None:
    scene_dir = tmp_path / "scenes" / "demo"
    scene_dir.mkdir(parents=True)
    manifest = {
        "id": "demo",
        "display_name": "Demo",
        "description": "x",
        "blend_file": "demo.blend",
        "spawn_points": ["a"],
        "camera_presets": ["main"],
    }
    (scene_dir / "scene.json").write_text(json.dumps(manifest))
    r = Registry.load(tmp_path)
    assert r.scenes["demo"].blend_path == scene_dir / "demo.blend"


def test_load_raises_on_malformed_manifest(tmp_path: Path) -> None:
    scene_dir = tmp_path / "scenes" / "broken"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene.json").write_text('{"id": "broken"}')  # missing required fields
    with pytest.raises(ValidationError):
        Registry.load(tmp_path)


# --- Action vocabulary --------------------------------------------------------


def test_default_actions_cover_all_action_types() -> None:
    from planner.schema import ActionType

    action_names = {a.name for a in DEFAULT_ACTIONS}
    schema_types = {t.value for t in ActionType}
    assert action_names == schema_types


def test_default_actions_include_timing_params() -> None:
    for action in DEFAULT_ACTIONS:
        names = {p.name for p in action.params}
        assert "start" in names, f"{action.name} missing 'start'"
        assert "end" in names, f"{action.name} missing 'end'"


def test_emotion_params_carry_enum_values() -> None:
    walk_to = next(a for a in DEFAULT_ACTIONS if a.name == "walk_to")
    emotion_param = next(p for p in walk_to.params if p.name == "emotion")
    assert emotion_param.required is False
    assert emotion_param.enum is not None
    assert set(emotion_param.enum) == {"neutral", "joy", "angry", "sorrow", "fun"}


# --- Prompt rendering ---------------------------------------------------------


def test_prompt_section_includes_all_three_blocks() -> None:
    r = Registry.load(Path("assets"))
    section = r.to_system_prompt_section()
    assert "# Available scenes" in section
    assert "# Available characters" in section
    assert "# Available actions" in section


def test_prompt_section_lists_scene_details() -> None:
    r = Registry.load(Path("assets"))
    section = r.to_system_prompt_section()
    assert "dark_lab" in section
    assert "door, center_room, robot_station" in section
    assert "wide, close_student, close_robot" in section


def test_prompt_section_marks_optional_params() -> None:
    r = Registry.load(Path("assets"))
    section = r.to_system_prompt_section()
    # `emotion` on walk_to is optional with an enum.
    assert "(optional — one of: neutral, joy, angry, sorrow, fun)" in section


def test_prompt_section_handles_empty_registry(tmp_path: Path) -> None:
    r = Registry.load(tmp_path)
    section = r.to_system_prompt_section()
    assert "(none)" in section
    # Actions are static, so they're still present.
    assert "walk_to" in section
