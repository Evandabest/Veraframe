"""Schema tests for the play_clip action."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from planner.schema import Action, ActionType, BodyPart, PlayClipAction, effective_bone_mask


def test_action_type_includes_play_clip() -> None:
    assert ActionType.PLAY_CLIP.value == "play_clip"


def test_play_clip_minimal_construction() -> None:
    a = PlayClipAction(id="a1", start=0, end=2.0, character="alice", clip="kick")
    assert a.type == "play_clip"
    assert a.character == "alice"
    assert a.clip == "kick"
    assert a.speed == 1.0
    assert a.loop is False


def test_play_clip_accepts_speed_and_loop() -> None:
    a = PlayClipAction(
        id="a1",
        start=0,
        end=2.0,
        character="alice",
        clip="kick",
        speed=1.5,
        loop=True,
    )
    assert a.speed == 1.5
    assert a.loop is True


def test_play_clip_rejects_zero_or_negative_speed() -> None:
    with pytest.raises(ValidationError):
        PlayClipAction(id="a1", start=0, end=2.0, character="alice", clip="kick", speed=0.0)
    with pytest.raises(ValidationError):
        PlayClipAction(id="a1", start=0, end=2.0, character="alice", clip="kick", speed=-0.5)


def test_play_clip_requires_character_and_clip() -> None:
    with pytest.raises(ValidationError):
        PlayClipAction(id="a1", start=0, end=2.0)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        PlayClipAction(id="a1", start=0, end=2.0, character="alice")  # type: ignore[call-arg]


def test_play_clip_dispatches_through_action_union() -> None:
    adapter = TypeAdapter(Action)
    parsed = adapter.validate_python(
        {
            "id": "a1",
            "type": "play_clip",
            "character": "alice",
            "clip": "kick",
            "start": 0,
            "end": 2,
        }
    )
    assert parsed.type == "play_clip"


def test_play_clip_default_bone_mask_is_whole_body() -> None:
    a = PlayClipAction(id="a1", start=0, end=2.0, character="alice", clip="kick")
    parts = set(effective_bone_mask(a))
    assert BodyPart.LEFT_LEG in parts
    assert BodyPart.RIGHT_LEG in parts
    assert BodyPart.LEFT_ARM in parts
    assert BodyPart.RIGHT_ARM in parts
