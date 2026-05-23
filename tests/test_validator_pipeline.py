"""Tests for the specialized-validator pipeline (Step 54)."""

from __future__ import annotations

from pathlib import Path

import pytest

from planner.registry import (
    CharacterSpec,
    Registry,
    SceneSpec,
)
from planner.schema import Character, Project, Shot, TalkAction, IdleAction
from planner.validators import default_passes, run_pipeline
from planner.validators.beat_coherence import run as beat_run
from planner.validators.dialog_companion import run as dialog_run


def _registry() -> Registry:
    scene = SceneSpec(
        id="lab",
        display_name="Lab",
        description="A lab.",
        blend_path=Path("/fake/lab.blend"),
        spawn_points=("door", "center"),
        camera_presets=("wide", "close"),
        lighting_presets=("default",),
    )
    alice = CharacterSpec(
        id="student_v1",
        display_name="Student",
        description="A student.",
        mesh_path=Path("/fake/alice.fbx"),
        rig_type="mixamo",
        face_blendshapes=(),
    )
    bob = CharacterSpec(
        id="robot_v1",
        display_name="Robot",
        description="A robot.",
        mesh_path=Path("/fake/bob.fbx"),
        rig_type="mixamo",
        face_blendshapes=(),
    )
    return Registry(
        scenes={"lab": scene},
        characters={"student_v1": alice, "robot_v1": bob},
        animations={},
    )


def _project(actions: list, second_character: bool = False) -> Project:
    characters = [Character(id="alice", preset="student_v1", spawn="door")]
    if second_character:
        characters.append(Character(id="bob", preset="robot_v1", spawn="center"))
    return Project(
        project="demo",
        scene="lab",
        characters=characters,
        shots=[
            Shot(id="s1", start=0, end=10, camera="wide", actions=actions),
        ],
    )


# --- dialog_companion ---------------------------------------------------------


def test_dialog_companion_auto_fills_look_at_when_one_other_character() -> None:
    talk = TalkAction(id="t1", start=0, end=3, character="alice", text="hi bob")
    project = _project([talk, IdleAction(id="i1", start=0, end=3, character="bob")], second_character=True)
    result = dialog_run(project, _registry())
    assert result.issues == []
    assert len(result.fixes) == 1
    assert "defaulting to 'bob'" in result.fixes[0]
    talk_after = result.project.shots[0].actions[0]
    assert isinstance(talk_after, TalkAction)
    assert talk_after.look_at == "bob"


def test_dialog_companion_skips_short_talks() -> None:
    talk = TalkAction(id="t1", start=0, end=0.8, character="alice", text="hi")
    project = _project([talk, IdleAction(id="i1", start=0, end=1, character="bob")], second_character=True)
    result = dialog_run(project, _registry())
    assert result.fixes == []
    assert result.project.shots[0].actions[0].look_at is None


def test_dialog_companion_preserves_explicit_look_at() -> None:
    talk = TalkAction(id="t1", start=0, end=3, character="alice", text="hi", look_at="door")
    project = _project([talk, IdleAction(id="i1", start=0, end=3, character="bob")], second_character=True)
    result = dialog_run(project, _registry())
    assert result.fixes == []
    assert result.project.shots[0].actions[0].look_at == "door"


def test_dialog_companion_skips_when_speaker_is_alone() -> None:
    talk = TalkAction(id="t1", start=0, end=3, character="alice", text="hi")
    project = _project([talk])
    result = dialog_run(project, _registry())
    assert result.fixes == []
    assert result.project.shots[0].actions[0].look_at is None


def test_dialog_companion_skips_when_multiple_listeners() -> None:
    talk = TalkAction(id="t1", start=0, end=3, character="alice", text="hi")
    # Two other characters in the same shot -> ambiguous, skip.
    extra = IdleAction(id="i1", start=0, end=3, character="bob")
    project = _project([talk, extra], second_character=True)
    # Add a third character via a sneaky action that references "carol".
    project.shots[0].actions.append(IdleAction(id="i2", start=0, end=3, character="carol"))
    result = dialog_run(project, _registry())
    assert result.fixes == []
    assert result.project.shots[0].actions[0].look_at is None


# --- beat_coherence ----------------------------------------------------------


def test_beat_coherence_flags_empty_shots() -> None:
    project = _project([])  # shot with zero actions
    result = beat_run(project, _registry())
    assert len(result.issues) == 1
    assert "no body actions" in result.issues[0]


def test_beat_coherence_accepts_a_shot_with_just_an_idle() -> None:
    project = _project([IdleAction(id="i1", start=0, end=5, character="alice")])
    result = beat_run(project, _registry())
    assert result.issues == []


def test_beat_coherence_does_not_count_camera_or_lighting_as_body() -> None:
    from planner.schema import CameraCutAction, SetLightingAction

    project = _project([
        CameraCutAction(id="c1", start=0, end=0.5, camera="wide"),
        SetLightingAction(id="l1", start=0, end=0.5, preset="default"),
    ])
    result = beat_run(project, _registry())
    assert len(result.issues) == 1


# --- pipeline integration ----------------------------------------------------


def test_pipeline_namespaces_fixes_and_issues_per_pass() -> None:
    project = _project([])  # empty shot triggers beat_coherence
    out = run_pipeline(project, _registry(), default_passes())
    # Every issue is prefixed with [pass_name].
    assert all(i.startswith("[") for i in out.issues), out.issues
    assert any(i.startswith("[beat_coherence]") for i in out.issues)
    assert "beat_coherence" in out.per_pass


def test_pipeline_applies_dialog_fix_then_clean_issues() -> None:
    """End-to-end: a long talk with no look_at + a second character in the
    shot should leave the project clean (no issues) with the look_at
    auto-attached."""
    talk = TalkAction(id="t1", start=0, end=3, character="alice", text="hi")
    project = _project(
        [
            talk,
            IdleAction(id="i_alice", start=3, end=5, character="alice"),
            IdleAction(id="i_bob", start=0, end=5, character="bob"),
        ],
        second_character=True,
    )
    out = run_pipeline(project, _registry(), default_passes())
    assert out.issues == [], out.issues
    assert any("defaulting to 'bob'" in f for f in out.fixes)
    fixed_talk = out.project.shots[0].actions[0]
    assert fixed_talk.look_at == "bob"
