"""Tests for Step 39 — expanded action vocabulary.

Covers:
- WalkStyle / IdleStyle enums and their use on walk_to / idle.
- Schema acceptance of nod / shake_head / wave actions.
- Registry exposure of the new actions and style enums.
- The walk_to executor honoring `style` via the speed multiplier.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from actions import walk_to as walk_to_action
from planner.registry import DEFAULT_ACTIONS
from planner.schema import (
    Action,
    IdleAction,
    IdleStyle,
    NodAction,
    ShakeHeadAction,
    WalkStyle,
    WalkToAction,
    WaveAction,
)


# --- Schema --------------------------------------------------------------


def test_walk_style_enum_complete() -> None:
    assert {s.value for s in WalkStyle} == {
        "walk", "run", "jog", "sneak", "march", "limp"
    }


def test_idle_style_enum_complete() -> None:
    assert {s.value for s in IdleStyle} == {
        "neutral", "tired", "alert", "confident", "bored", "nervous"
    }


def test_walk_to_accepts_style() -> None:
    a = WalkToAction(
        id="a1", start=0, end=4, character="x", target="door", style="run"
    )
    assert a.style is WalkStyle.RUN


def test_walk_to_style_is_optional() -> None:
    a = WalkToAction(id="a1", start=0, end=4, character="x", target="door")
    assert a.style is None


def test_walk_to_rejects_unknown_style() -> None:
    with pytest.raises(Exception):
        WalkToAction(
            id="a1", start=0, end=4, character="x", target="door", style="moonwalk"
        )


def test_idle_accepts_style() -> None:
    a = IdleAction(id="a1", start=0, end=4, character="x", style="tired")
    assert a.style is IdleStyle.TIRED


def test_nod_schema_minimal() -> None:
    a = NodAction(id="a1", start=0, end=1.0, character="x")
    assert a.type == "nod"


def test_shake_head_schema_minimal() -> None:
    a = ShakeHeadAction(id="a1", start=0, end=1.0, character="x")
    assert a.type == "shake_head"


def test_wave_schema_with_optional_target() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="x", target="bob")
    assert a.type == "wave"
    assert a.target == "bob"


def test_wave_schema_target_optional() -> None:
    a = WaveAction(id="a1", start=0, end=2.0, character="x")
    assert a.target is None


def test_action_union_dispatches_new_types() -> None:
    """Validates the Action discriminated-union actually routes to the new
    action classes by their `type` literal."""
    adapter = TypeAdapter(Action)
    for atype in ("nod", "shake_head", "wave"):
        payload = {
            "id": "a1",
            "type": atype,
            "character": "x",
            "start": 0,
            "end": 1.0,
        }
        parsed = adapter.validate_python(payload)
        assert parsed.type == atype


# --- Registry ------------------------------------------------------------


def _action_spec(name: str):
    return next((a for a in DEFAULT_ACTIONS if a.name == name), None)


def test_registry_walk_to_has_style_param() -> None:
    spec = _action_spec("walk_to")
    assert spec is not None
    style_param = next((p for p in spec.params if p.name == "style"), None)
    assert style_param is not None
    assert style_param.required is False
    assert "run" in (style_param.enum or ())


def test_registry_idle_has_style_param() -> None:
    spec = _action_spec("idle")
    assert spec is not None
    style_param = next((p for p in spec.params if p.name == "style"), None)
    assert style_param is not None
    assert "tired" in (style_param.enum or ())


def test_registry_includes_new_gestures() -> None:
    names = {a.name for a in DEFAULT_ACTIONS}
    assert {"nod", "shake_head", "wave"}.issubset(names)


def test_registry_wave_target_is_optional() -> None:
    spec = _action_spec("wave")
    assert spec is not None
    target_param = next((p for p in spec.params if p.name == "target"), None)
    assert target_param is not None
    assert target_param.required is False


# --- Executor: walk_to speed multiplier ---------------------------------


def test_walk_to_style_multipliers_cover_all_styles() -> None:
    """Every style on the enum must have a known multiplier (no silent fall-
    back to 1.0 for valid values). Unknown styles fall back to walk."""
    for style in WalkStyle:
        assert style.value in walk_to_action._STYLE_SPEED_MULTIPLIER


def test_walk_to_style_multipliers_ordered_correctly() -> None:
    m = walk_to_action._STYLE_SPEED_MULTIPLIER
    assert m["sneak"] < m["walk"] < m["jog"] < m["run"]
    assert m["limp"] < m["walk"]


def test_walk_to_unknown_style_falls_back_to_walk() -> None:
    # Doesn't raise, returns the same multiplier as walk.
    assert (
        walk_to_action._STYLE_SPEED_MULTIPLIER.get("moonwalk", 1.0)
        == walk_to_action._STYLE_SPEED_MULTIPLIER["walk"]
    )
