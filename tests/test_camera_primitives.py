"""Tests for Step 41a — track_subject + two_shot camera primitives.

Schema + registry coverage. The actual Blender-side rendering is gated
behind BLENDER_AVAILABLE=1 (consistent with the other per-action suites).
"""

from __future__ import annotations

from pydantic import TypeAdapter

from planner.registry import DEFAULT_ACTIONS
from planner.schema import (
    Action,
    ActionType,
    TrackSubjectAction,
    TwoShotAction,
)


def test_action_type_enum_includes_new_camera_types() -> None:
    assert ActionType.TRACK_SUBJECT.value == "track_subject"
    assert ActionType.TWO_SHOT.value == "two_shot"


def test_track_subject_schema_minimal() -> None:
    a = TrackSubjectAction(id="a1", start=0, end=4.0, character="alice")
    assert a.type == "track_subject"
    assert a.character == "alice"


def test_track_subject_requires_character() -> None:
    import pytest

    with pytest.raises(Exception):
        TrackSubjectAction(id="a1", start=0, end=4.0)  # type: ignore[call-arg]


def test_two_shot_schema_minimal() -> None:
    a = TwoShotAction(id="a1", start=0, end=4.0, a="alice", b="bob")
    assert a.type == "two_shot"
    assert (a.a, a.b) == ("alice", "bob")


def test_two_shot_requires_both_characters() -> None:
    import pytest

    with pytest.raises(Exception):
        TwoShotAction(id="a1", start=0, end=4.0, a="alice")  # type: ignore[call-arg]


def test_action_union_dispatches_new_camera_types() -> None:
    adapter = TypeAdapter(Action)
    track = adapter.validate_python(
        {"id": "a1", "type": "track_subject", "character": "alice", "start": 0, "end": 4}
    )
    assert track.type == "track_subject"
    two = adapter.validate_python(
        {"id": "a2", "type": "two_shot", "a": "alice", "b": "bob", "start": 0, "end": 4}
    )
    assert two.type == "two_shot"


def test_registry_exposes_track_subject() -> None:
    spec = next((a for a in DEFAULT_ACTIONS if a.name == "track_subject"), None)
    assert spec is not None
    params = {p.name for p in spec.params}
    assert {"character", "start", "end"}.issubset(params)


def test_registry_exposes_two_shot() -> None:
    spec = next((a for a in DEFAULT_ACTIONS if a.name == "two_shot"), None)
    assert spec is not None
    params = {p.name for p in spec.params}
    assert {"a", "b", "start", "end"}.issubset(params)


def test_executor_classifies_camera_types() -> None:
    """The two-pass dispatch in execute_timeline relies on a hardcoded set
    of camera action type strings. This test sanity-checks that the set
    matches our new schema additions — guards against future drift."""
    # Re-import the module-level set by reading the source — simplest way to
    # verify without exposing it as a public symbol.
    import re
    from pathlib import Path

    src = Path("blender_daemon/action_executor.py").read_text()
    # Grab the `camera_types = {...}` block (set can be single- or multi-line).
    match = re.search(r"camera_types\s*=\s*\{([^}]*)\}", src, flags=re.DOTALL)
    assert match, "expected a `camera_types = {...}` declaration"
    block = match.group(1)
    for required in ("camera_cut", "camera_dolly", "track_subject", "two_shot", "set_lighting"):
        assert required in block, f"{required!r} missing from camera_types"
