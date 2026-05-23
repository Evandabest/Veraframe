"""Schema + registry tests for the over_shoulder camera primitive.

The Blender-side keyframe behavior is exercised via BLENDER_AVAILABLE=1
integration suites; this file covers the pure-Python surface.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from planner.registry import DEFAULT_ACTIONS
from planner.schema import Action, ActionType, OverShoulderAction


def test_action_type_includes_over_shoulder() -> None:
    assert ActionType.OVER_SHOULDER.value == "over_shoulder"


def test_over_shoulder_schema_minimal() -> None:
    a = OverShoulderAction(id="a1", start=0, end=4.0, a="alice", b="bob")
    assert a.type == "over_shoulder"
    assert (a.a, a.b) == ("alice", "bob")


def test_over_shoulder_requires_both_handles() -> None:
    with pytest.raises(Exception):
        OverShoulderAction(id="a1", start=0, end=4.0, a="alice")  # type: ignore[call-arg]


def test_action_union_dispatches_over_shoulder() -> None:
    adapter = TypeAdapter(Action)
    parsed = adapter.validate_python(
        {"id": "a1", "type": "over_shoulder", "a": "alice", "b": "bob", "start": 0, "end": 4}
    )
    assert parsed.type == "over_shoulder"


def test_registry_exposes_over_shoulder() -> None:
    spec = next((a for a in DEFAULT_ACTIONS if a.name == "over_shoulder"), None)
    assert spec is not None
    params = {p.name for p in spec.params}
    assert {"a", "b", "start", "end"}.issubset(params)


def test_executor_camera_types_includes_over_shoulder() -> None:
    """Source-level sanity check that the two-pass dispatch routes
    over_shoulder into pass-2 (camera/scene) rather than pass-1 (body)."""
    from pathlib import Path

    src = Path("blender_daemon/action_executor.py").read_text()
    assert '"over_shoulder"' in src
