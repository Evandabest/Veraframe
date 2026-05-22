"""Tests for the registry filter used when the UI constrains the LLM to a
selected scene + character pool."""

from planner.registry import (
    AnimationSpec,
    CharacterSpec,
    Registry,
    SceneSpec,
)


def _make_registry() -> Registry:
    scenes = {
        "lab": SceneSpec(
            id="lab",
            display_name="Lab",
            description="d",
            blend_path="/x/lab.blend",
            spawn_points=("door",),
            camera_presets=("wide",),
            lighting_presets=(),
        ),
        "school": SceneSpec(
            id="school",
            display_name="School",
            description="d",
            blend_path="/x/school.blend",
            spawn_points=("door",),
            camera_presets=("wide",),
            lighting_presets=(),
        ),
    }
    characters = {
        "alice": CharacterSpec(
            id="alice",
            display_name="Alice",
            description="d",
            mesh_path="/x/alice.fbx",
            rig_type="mixamo",
            face_blendshapes=(),
        ),
        "bob": CharacterSpec(
            id="bob",
            display_name="Bob",
            description="d",
            mesh_path="/x/bob.fbx",
            rig_type="mixamo",
            face_blendshapes=(),
        ),
        "charlie": CharacterSpec(
            id="charlie",
            display_name="Charlie",
            description="d",
            mesh_path="/x/charlie.fbx",
            rig_type="mixamo",
            face_blendshapes=(),
        ),
    }
    animations = {
        "idle": AnimationSpec(
            id="idle",
            display_name="Idle",
            fbx_path="/x/idle.fbx",
            loop=True,
            applies_to_rig="mixamo",
        )
    }
    return Registry(scenes=scenes, characters=characters, animations=animations)


def test_filtered_keeps_only_requested_scenes() -> None:
    reg = _make_registry()
    filtered = reg.filtered(scene_ids={"lab"})
    assert set(filtered.scenes.keys()) == {"lab"}
    # Characters and animations untouched
    assert set(filtered.characters.keys()) == {"alice", "bob", "charlie"}
    assert set(filtered.animations.keys()) == {"idle"}


def test_filtered_keeps_only_requested_characters() -> None:
    reg = _make_registry()
    filtered = reg.filtered(character_ids={"alice", "bob"})
    assert set(filtered.characters.keys()) == {"alice", "bob"}
    assert set(filtered.scenes.keys()) == {"lab", "school"}


def test_filtered_with_none_keeps_everything() -> None:
    reg = _make_registry()
    filtered = reg.filtered()
    assert filtered.scenes == reg.scenes
    assert filtered.characters == reg.characters


def test_filtered_with_empty_set_treated_as_no_filter() -> None:
    # Empty set is "no selection" — UI default is everything checked, so an
    # empty list shouldn't blank out the catalog.
    reg = _make_registry()
    filtered = reg.filtered(scene_ids=set(), character_ids=set())
    assert filtered.scenes == reg.scenes
    assert filtered.characters == reg.characters


def test_filtered_unknown_ids_silently_dropped() -> None:
    reg = _make_registry()
    filtered = reg.filtered(scene_ids={"lab", "nonexistent"})
    assert set(filtered.scenes.keys()) == {"lab"}


def test_system_prompt_only_lists_filtered_scenes() -> None:
    reg = _make_registry()
    filtered = reg.filtered(scene_ids={"lab"}, character_ids={"alice"})
    prompt = filtered.to_system_prompt_section()
    assert "`lab`" in prompt
    assert "`school`" not in prompt
    assert "`alice`" in prompt
    assert "`bob`" not in prompt
    assert "`charlie`" not in prompt
