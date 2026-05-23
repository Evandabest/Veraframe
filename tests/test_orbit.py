"""Schema + registry tests for the orbit camera primitive."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from planner.registry import DEFAULT_ACTIONS
from planner.schema import Action, ActionType, OrbitAction


def test_action_type_includes_orbit() -> None:
    assert ActionType.ORBIT.value == "orbit"


def test_orbit_schema_minimal() -> None:
    a = OrbitAction(id="a1", start=0, end=4.0, target="alice")
    assert a.type == "orbit"
    assert a.target == "alice"
    assert a.degrees == 90.0  # default


def test_orbit_accepts_custom_degrees() -> None:
    a = OrbitAction(id="a1", start=0, end=4.0, target="alice", degrees=45.0)
    assert a.degrees == 45.0


def test_orbit_accepts_negative_degrees_for_cw() -> None:
    # No positivity constraint — negative just means clockwise.
    a = OrbitAction(id="a1", start=0, end=4.0, target="alice", degrees=-180.0)
    assert a.degrees == -180.0


def test_orbit_requires_target() -> None:
    with pytest.raises(Exception):
        OrbitAction(id="a1", start=0, end=4.0)  # type: ignore[call-arg]


def test_action_union_dispatches_orbit() -> None:
    adapter = TypeAdapter(Action)
    parsed = adapter.validate_python(
        {"id": "a1", "type": "orbit", "target": "alice", "degrees": 60, "start": 0, "end": 4}
    )
    assert parsed.type == "orbit"


def test_registry_exposes_orbit_with_optional_degrees() -> None:
    spec = next((a for a in DEFAULT_ACTIONS if a.name == "orbit"), None)
    assert spec is not None
    params = {p.name: p for p in spec.params}
    assert "target" in params and params["target"].required
    assert "degrees" in params and not params["degrees"].required


def test_executor_camera_types_includes_orbit() -> None:
    from pathlib import Path

    src = Path("blender_daemon/action_executor.py").read_text()
    assert '"orbit"' in src
