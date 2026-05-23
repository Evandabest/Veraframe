"""Tests for the reference_autofix pass (Step 54)."""

from __future__ import annotations

from pathlib import Path

from planner.registry import CharacterSpec, Registry, SceneSpec
from planner.schema import (
    CameraCutAction,
    Character,
    IdleAction,
    Project,
    SetLightingAction,
    Shot,
    TalkAction,
    WalkToAction,
)
from planner.validators import default_passes, run_pipeline
from planner.validators.reference_autofix import run as autofix_run


def _registry() -> Registry:
    scene = SceneSpec(
        id="lab",
        display_name="Lab",
        description="A lab.",
        blend_path=Path("/fake/lab.blend"),
        spawn_points=("door", "center_room", "robot_station"),
        camera_presets=("wide", "close_student"),
        lighting_presets=("default", "emergency"),
    )
    alice = CharacterSpec(
        id="student_v1",
        display_name="Student",
        description=".",
        mesh_path=Path("/fake/alice.fbx"),
        rig_type="mixamo",
        face_blendshapes=(),
    )
    return Registry(scenes={"lab": scene}, characters={"student_v1": alice}, animations={})


def _project(actions: list, characters: list | None = None) -> Project:
    return Project(
        project="demo",
        scene="lab",
        characters=characters or [Character(id="alice", preset="student_v1", spawn="door")],
        shots=[Shot(id="s1", start=0, end=10, camera="wide", actions=actions)],
    )


def test_autofix_snaps_walk_target_typo() -> None:
    walk = WalkToAction(id="w1", start=0, end=3, character="alice", target="doorway")
    out = autofix_run(_project([walk]), _registry())
    assert out.project.shots[0].actions[0].target == "door"
    assert any("'doorway' → 'door'" in f for f in out.fixes)


def test_autofix_snaps_shot_camera_typo() -> None:
    # `close_studnet` is a clear typo of `close_student` — should snap.
    shot = Shot(id="s1", start=0, end=5, camera="close_studnet", actions=[])
    project = Project(
        project="demo",
        scene="lab",
        characters=[Character(id="alice", preset="student_v1", spawn="door")],
        shots=[shot],
    )
    out = autofix_run(project, _registry())
    assert out.project.shots[0].camera == "close_student"


def test_autofix_snaps_lighting_preset_typo() -> None:
    lighting = SetLightingAction(id="l1", start=0, end=1, preset="emergency_mode")
    out = autofix_run(_project([lighting]), _registry())
    assert out.project.shots[0].actions[0].preset == "emergency"


def test_autofix_snaps_talk_look_at() -> None:
    talk = TalkAction(
        id="t1", start=0, end=3, character="alice", text="hi", look_at="center_rom"
    )
    out = autofix_run(_project([talk]), _registry())
    assert out.project.shots[0].actions[0].look_at == "center_room"


def test_autofix_snaps_character_spawn() -> None:
    proj = _project(
        [IdleAction(id="i1", start=0, end=1, character="alice")],
        characters=[Character(id="alice", preset="student_v1", spawn="doorr")],
    )
    out = autofix_run(proj, _registry())
    assert out.project.characters[0].spawn == "door"


def test_autofix_leaves_exact_matches_alone() -> None:
    walk = WalkToAction(id="w1", start=0, end=3, character="alice", target="door")
    out = autofix_run(_project([walk]), _registry())
    assert out.fixes == []


def test_autofix_skips_far_off_strings() -> None:
    # "rooftop" is too far from any spawn point ("door", "center_room",
    # "robot_station") to snap. Stays as-is for reference_check to flag.
    walk = WalkToAction(id="w1", start=0, end=3, character="alice", target="rooftop")
    out = autofix_run(_project([walk]), _registry())
    assert out.project.shots[0].actions[0].target == "rooftop"
    assert out.fixes == []


def test_autofix_camera_cut_action() -> None:
    # Typo, not a plausibility fallback — autofix is conservative.
    cut = CameraCutAction(id="c1", start=0, end=0.5, camera="close_studnet")
    out = autofix_run(_project([cut]), _registry())
    assert out.project.shots[0].actions[0].camera == "close_student"


def test_autofix_does_not_snap_a_different_concept() -> None:
    # "close" might be what the LLM meant, but it's a distinct name —
    # autofix lets it fall through to reference_check + the retry loop
    # so the model can pick deliberately, not via similarity guess.
    cut = CameraCutAction(id="c1", start=0, end=0.5, camera="close")
    out = autofix_run(_project([cut]), _registry())
    assert out.fixes == []
    assert out.project.shots[0].actions[0].camera == "close"


def test_pipeline_autofix_then_clean_no_issues() -> None:
    """End-to-end: a typo in a walk target gets snapped, then
    reference_check sees the clean project and reports no issues."""
    walk = WalkToAction(id="w1", start=0, end=3, character="alice", target="doorway")
    out = run_pipeline(_project([walk]), _registry(), default_passes())
    # The autofix prefix and the resolved value are both present.
    assert any("[reference_autofix]" in f for f in out.fixes)
    # No unresolved reference issues — autofix handled it before
    # reference_check saw it.
    assert not any("[reference_check]" in i for i in out.issues), out.issues
