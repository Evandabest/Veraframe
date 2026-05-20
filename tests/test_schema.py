"""Tests for `planner.schema` — round-trip parsing and validation errors."""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from planner.schema import (
    Action,
    BlinkAction,
    CameraCutAction,
    CameraDollyAction,
    Emotion,
    FrownAction,
    IdleAction,
    LookAtAction,
    PointAtAction,
    Project,
    SetLightingAction,
    Shot,
    SitAction,
    SmileAction,
    StandAction,
    TalkAction,
    TurnToAction,
    WalkToAction,
)

# Used to parse a single action against the discriminated union.
ActionAdapter: TypeAdapter[Action] = TypeAdapter(Action)


# --- Positive parsing ---------------------------------------------------------


def _base(action_type: str, **extras: Any) -> dict[str, Any]:
    return {"id": "a1", "type": action_type, "start": 0.0, "end": 1.0, **extras}


VALID_ACTIONS: list[tuple[dict[str, Any], type]] = [
    (_base("walk_to", character="student", target="door"), WalkToAction),
    (_base("walk_to", character="student", target="door", emotion="joy"), WalkToAction),
    (_base("idle", character="student"), IdleAction),
    (_base("turn_to", character="student", target="robot"), TurnToAction),
    (_base("look_at", character="student", target="robot"), LookAtAction),
    (_base("point_at", character="student", target="robot"), PointAtAction),
    (_base("sit", character="student"), SitAction),
    (_base("stand", character="student"), StandAction),
    (_base("smile", character="student"), SmileAction),
    (_base("frown", character="student"), FrownAction),
    (_base("blink", character="student"), BlinkAction),
    (_base("talk", character="student", text="hello"), TalkAction),
    (
        _base(
            "talk",
            character="student",
            text="hello",
            emotion="sorrow",
            look_at="robot",
            gesture="small_step_back",
        ),
        TalkAction,
    ),
    (_base("camera_cut", camera="wide"), CameraCutAction),
    (_base("camera_dolly", from_camera="wide", to_camera="close_student"), CameraDollyAction),
    (_base("set_lighting", preset="dim"), SetLightingAction),
]


@pytest.mark.parametrize(
    "payload,expected_cls",
    VALID_ACTIONS,
    ids=lambda x: getattr(x, "__name__", x.get("type") if isinstance(x, dict) else str(x)),
)
def test_action_parses_to_expected_subclass(payload: dict[str, Any], expected_cls: type) -> None:
    action = ActionAdapter.validate_python(payload)
    assert isinstance(action, expected_cls)
    assert action.type == payload["type"]


def test_full_project_parses() -> None:
    Project.model_validate(
        {
            "project": "dark_lab_intro",
            "scene": "dark_lab",
            "characters": [
                {"id": "student", "preset": "student_v1", "spawn": "door"},
                {"id": "robot", "preset": "robot_v1", "spawn": "robot_station"},
            ],
            "shots": [
                {
                    "id": "shot_001",
                    "start": 0,
                    "end": 4,
                    "camera": "wide",
                    "actions": [
                        {
                            "id": "action_001",
                            "type": "walk_to",
                            "character": "student",
                            "target": "center_room",
                            "emotion": "sorrow",
                            "start": 0,
                            "end": 4,
                        }
                    ],
                },
                {
                    "id": "shot_002",
                    "start": 4,
                    "end": 8,
                    "camera": "close_student",
                    "actions": [
                        {
                            "id": "action_002",
                            "type": "look_at",
                            "character": "student",
                            "target": "robot",
                            "start": 4,
                            "end": 5,
                        },
                        {
                            "id": "action_003",
                            "type": "talk",
                            "character": "student",
                            "text": "I don't think we should touch that.",
                            "emotion": "sorrow",
                            "look_at": "robot",
                            "start": 5,
                            "end": 8,
                        },
                    ],
                },
            ],
        }
    )


def test_roundtrip_json_preserves_action_subtype() -> None:
    raw = _base("talk", character="student", text="hi", emotion="joy")
    parsed = ActionAdapter.validate_python(raw)
    again = ActionAdapter.validate_python(parsed.model_dump())
    assert isinstance(again, TalkAction)
    assert again.text == "hi"
    assert again.emotion == Emotion.JOY


# --- Negative parsing: discriminator + missing fields -------------------------


def test_unknown_action_type_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ActionAdapter.validate_python(_base("teleport", character="student"))
    assert "teleport" in str(exc.value) or "discriminator" in str(exc.value).lower()


MISSING_FIELD_CASES: list[tuple[str, dict[str, Any], str]] = [
    # action_type, payload (with required field stripped), expected missing field
    ("walk_to", _base("walk_to", character="student"), "target"),
    ("walk_to", _base("walk_to", target="door"), "character"),
    ("turn_to", _base("turn_to", character="student"), "target"),
    ("look_at", _base("look_at", character="student"), "target"),
    ("point_at", _base("point_at", character="student"), "target"),
    ("idle", _base("idle"), "character"),
    ("sit", _base("sit"), "character"),
    ("stand", _base("stand"), "character"),
    ("smile", _base("smile"), "character"),
    ("frown", _base("frown"), "character"),
    ("blink", _base("blink"), "character"),
    ("talk", _base("talk", character="student"), "text"),
    ("talk", _base("talk", text="hi"), "character"),
    ("camera_cut", _base("camera_cut"), "camera"),
    ("camera_dolly", _base("camera_dolly", from_camera="wide"), "to_camera"),
    ("camera_dolly", _base("camera_dolly", to_camera="wide"), "from_camera"),
    ("set_lighting", _base("set_lighting"), "preset"),
]


@pytest.mark.parametrize("action_type,payload,missing_field", MISSING_FIELD_CASES)
def test_missing_required_field_rejected(
    action_type: str, payload: dict[str, Any], missing_field: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        ActionAdapter.validate_python(payload)
    assert missing_field in str(exc.value), (
        f"{action_type}: missing field {missing_field!r} not surfaced in error"
    )


# --- Negative parsing: timing + values ----------------------------------------


def test_action_end_must_be_after_start() -> None:
    with pytest.raises(ValidationError, match="end.*must be > start"):
        ActionAdapter.validate_python(
            {"id": "a1", "type": "idle", "character": "student", "start": 5.0, "end": 5.0}
        )


def test_action_end_before_start_rejected() -> None:
    with pytest.raises(ValidationError, match="end.*must be > start"):
        ActionAdapter.validate_python(
            {"id": "a1", "type": "idle", "character": "student", "start": 5.0, "end": 4.0}
        )


def test_shot_end_must_be_after_start() -> None:
    with pytest.raises(ValidationError, match="end.*must be > start"):
        Shot.model_validate({"id": "s1", "start": 4.0, "end": 4.0, "camera": "wide", "actions": []})


def test_negative_start_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionAdapter.validate_python(
            {"id": "a1", "type": "idle", "character": "student", "start": -1.0, "end": 1.0}
        )


def test_invalid_emotion_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionAdapter.validate_python(
            _base("walk_to", character="student", target="door", emotion="nervous")
        )


def test_empty_required_string_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionAdapter.validate_python(_base("walk_to", character="student", target=""))


def test_empty_talk_text_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionAdapter.validate_python(_base("talk", character="student", text=""))
