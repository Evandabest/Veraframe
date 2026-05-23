"""Tests for the per-limb `bone_mask` field and the conflict checker."""

from __future__ import annotations

from pydantic import TypeAdapter

from planner.schema import (
    Action,
    BodyPart,
    NodAction,
    PointAtAction,
    ShakeHeadAction,
    WalkToAction,
    WaveAction,
    actions_conflict,
    effective_bone_mask,
)


def test_bodypart_enum_values() -> None:
    assert BodyPart.HEAD.value == "head"
    assert BodyPart.RIGHT_ARM.value == "right_arm"
    assert BodyPart.LEFT_ARM.value == "left_arm"


def test_wave_default_mask_is_right_arm() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="alice")
    assert effective_bone_mask(a) == [BodyPart.RIGHT_ARM]


def test_nod_default_mask_is_head() -> None:
    a = NodAction(id="a1", start=0, end=1.0, character="alice")
    assert effective_bone_mask(a) == [BodyPart.HEAD]


def test_shake_head_default_mask_is_head() -> None:
    a = ShakeHeadAction(id="a1", start=0, end=1.0, character="alice")
    assert effective_bone_mask(a) == [BodyPart.HEAD]


def test_explicit_bone_mask_overrides_default() -> None:
    a = WaveAction(
        id="a1",
        start=0,
        end=2.0,
        character="alice",
        bone_mask=[BodyPart.LEFT_ARM],
    )
    assert effective_bone_mask(a) == [BodyPart.LEFT_ARM]


def test_walk_to_drives_whole_body() -> None:
    a = WalkToAction(id="a1", start=0, end=4.0, character="alice", target="door")
    parts = set(effective_bone_mask(a))
    assert BodyPart.LEFT_LEG in parts
    assert BodyPart.RIGHT_LEG in parts
    assert BodyPart.SPINE in parts


def test_walk_to_and_wave_do_not_conflict() -> None:
    """A wave (right arm only) layers over a walk_to. The default walk_to
    mask DOES include right_arm because the FBX cycle drives the arm, but
    pose-keyframe overrides at the right-arm bones make this safe — the
    declarative conflict check still flags it, and Step 46's contract is
    that the LLM should put the wave on a *separate* lane (or accept the
    flag). For now `actions_conflict` returns True; future work can mark
    pose-level overrides as "additive" so this returns False.
    """
    walk = WalkToAction(id="a1", start=0, end=4.0, character="alice", target="door")
    wave = WaveAction(id="a2", start=1.0, end=3.0, character="alice")
    # Yes — they share right_arm. The signal is that the LLM/UI should
    # acknowledge the overlap; the executor handles it via pose-keyframes
    # taking precedence over FBX strip channels.
    assert actions_conflict(walk, wave) is True


def test_two_waves_on_same_arm_conflict() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="alice")
    b = WaveAction(id="a2", start=1.0, end=3.0, character="alice")
    assert actions_conflict(a, b) is True


def test_two_waves_on_different_arms_do_not_conflict() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="alice")
    b = WaveAction(
        id="a2",
        start=1.0,
        end=3.0,
        character="alice",
        bone_mask=[BodyPart.LEFT_ARM],
    )
    assert actions_conflict(a, b) is False


def test_actions_on_different_characters_never_conflict() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="alice")
    b = WaveAction(id="a2", start=0, end=2.0, character="bob")
    assert actions_conflict(a, b) is False


def test_non_overlapping_times_do_not_conflict() -> None:
    a = WaveAction(id="a1", start=0, end=1.0, character="alice")
    b = WaveAction(id="a2", start=2.0, end=3.0, character="alice")
    assert actions_conflict(a, b) is False


def test_wave_and_nod_layer_cleanly() -> None:
    """Right-arm wave and head nod touch disjoint parts — clean layering."""
    wave = WaveAction(id="a1", start=0, end=2.0, character="alice")
    nod = NodAction(id="a2", start=0, end=1.5, character="alice")
    assert actions_conflict(wave, nod) is False


def test_bone_mask_parses_via_action_union() -> None:
    adapter = TypeAdapter(Action)
    parsed = adapter.validate_python(
        {
            "id": "a1",
            "type": "wave",
            "character": "alice",
            "start": 0,
            "end": 2,
            "bone_mask": ["left_arm"],
        }
    )
    assert parsed.type == "wave"
    assert parsed.bone_mask == [BodyPart.LEFT_ARM]


def test_point_at_default_mask_is_right_arm() -> None:
    a = PointAtAction(id="a1", start=0, end=1.0, character="alice", target="door")
    assert effective_bone_mask(a) == [BodyPart.RIGHT_ARM]


def test_point_at_accepts_left_arm_override() -> None:
    a = PointAtAction(
        id="a1",
        start=0,
        end=1.0,
        character="alice",
        target="door",
        bone_mask=[BodyPart.LEFT_ARM],
    )
    assert effective_bone_mask(a) == [BodyPart.LEFT_ARM]
