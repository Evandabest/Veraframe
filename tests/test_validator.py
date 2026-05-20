"""Tests for `planner.validator` — semantic checks and retry loop."""

import json
from pathlib import Path
from typing import Any

import pytest

from planner.registry import Registry
from planner.schema import Project
from planner.validator import TimelineGenerationError, generate_validated_timeline, validate


@pytest.fixture
def registry() -> Registry:
    return Registry.load(Path("assets"))


def _project(**overrides: Any) -> Project:
    """Build a baseline valid project, with per-test overrides."""
    base: dict[str, Any] = {
        "project": "test",
        "scene": "dark_lab",
        "characters": [{"id": "student", "preset": "student_v1", "spawn": "door"}],
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "center_room",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return Project.model_validate(base)


# --- Validator: positive case -------------------------------------------------


def test_valid_project_has_no_errors(registry: Registry) -> None:
    assert validate(_project(), registry) == []


# --- Validator: registry membership ------------------------------------------


def test_unknown_scene(registry: Registry) -> None:
    errors = validate(_project(scene="kitchen"), registry)
    assert any("kitchen" in e and "not in the registry" in e for e in errors)


def test_unknown_character_preset(registry: Registry) -> None:
    errors = validate(
        _project(characters=[{"id": "student", "preset": "ghost_v1", "spawn": "door"}]),
        registry,
    )
    assert any("ghost_v1" in e for e in errors)


def test_character_spawn_not_in_scene(registry: Registry) -> None:
    errors = validate(
        _project(characters=[{"id": "student", "preset": "student_v1", "spawn": "bathroom"}]),
        registry,
    )
    assert any("bathroom" in e and "spawn point" in e for e in errors)


def test_shot_camera_not_in_scene(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "drone_overhead",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("drone_overhead" in e for e in errors)


# --- Validator: action references --------------------------------------------


def test_action_character_not_declared(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "robot",  # not declared
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("robot" in e and "not declared" in e for e in errors)


def test_action_target_not_spawn_or_character(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "ceiling",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("ceiling" in e for e in errors)


def test_action_target_can_be_another_character(registry: Registry) -> None:
    project = _project(
        characters=[
            {"id": "student", "preset": "student_v1", "spawn": "door"},
            {"id": "buddy", "preset": "student_v1", "spawn": "center_room"},
        ],
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "look_at",
                        "character": "student",
                        "target": "buddy",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ],
    )
    assert validate(project, registry) == []


def test_talk_look_at_validated(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "talk",
                        "character": "student",
                        "text": "hi",
                        "look_at": "skylight",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("skylight" in e for e in errors)


def test_camera_cut_to_unknown_camera(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_cut",
                        "camera": "ceiling_cam",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("ceiling_cam" in e for e in errors)


def test_camera_dolly_validates_both_endpoints(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_dolly",
                        "from_camera": "wide",
                        "to_camera": "bad_cam",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("bad_cam" in e for e in errors)


def test_set_lighting_validates_preset(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "set_lighting",
                        "preset": "neon_disco",
                        "start": 0,
                        "end": 4,
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("neon_disco" in e for e in errors)


# --- Validator: timing --------------------------------------------------------


def test_action_outside_shot_window(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 2,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0,
                        "end": 4,  # beyond shot end
                    }
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("outside parent shot" in e for e in errors)


# --- Validator: channel conflicts --------------------------------------------


def test_body_actions_overlap_on_same_character(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "center_room",
                        "start": 0,
                        "end": 3,
                    },
                    {
                        "id": "a2",
                        "type": "idle",
                        "character": "student",
                        "start": 2,
                        "end": 5,
                    },
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("body" in e and "a1" in e and "a2" in e for e in errors)


def test_body_actions_touching_endpoints_no_conflict(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "center_room",
                        "start": 0,
                        "end": 3,
                    },
                    {
                        "id": "a2",
                        "type": "idle",
                        "character": "student",
                        "start": 3,
                        "end": 5,
                    },
                ],
            }
        ]
    )
    assert validate(project, registry) == []


def test_body_actions_on_different_characters_no_conflict(registry: Registry) -> None:
    project = _project(
        characters=[
            {"id": "student", "preset": "student_v1", "spawn": "door"},
            {"id": "buddy", "preset": "student_v1", "spawn": "center_room"},
        ],
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0,
                        "end": 5,
                    },
                    {
                        "id": "a2",
                        "type": "idle",
                        "character": "buddy",
                        "start": 0,
                        "end": 5,
                    },
                ],
            }
        ],
    )
    assert validate(project, registry) == []


def test_smile_and_frown_overlap_conflict(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "smile",
                        "character": "student",
                        "start": 0,
                        "end": 3,
                    },
                    {
                        "id": "a2",
                        "type": "frown",
                        "character": "student",
                        "start": 1,
                        "end": 4,
                    },
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("face_expression" in e for e in errors)


def test_walk_and_talk_same_character_no_conflict(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "walk_to",
                        "character": "student",
                        "target": "center_room",
                        "start": 0,
                        "end": 4,
                    },
                    {
                        "id": "a2",
                        "type": "talk",
                        "character": "student",
                        "text": "hello",
                        "start": 1,
                        "end": 3,
                    },
                ],
            }
        ]
    )
    assert validate(project, registry) == []


def test_two_camera_cuts_overlap(registry: Registry) -> None:
    project = _project(
        shots=[
            {
                "id": "s1",
                "start": 0,
                "end": 4,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "camera_dolly",
                        "from_camera": "wide",
                        "to_camera": "close_student",
                        "start": 0,
                        "end": 3,
                    },
                    {
                        "id": "a2",
                        "type": "camera_cut",
                        "camera": "close_robot",
                        "start": 2,
                        "end": 4,
                    },
                ],
            }
        ]
    )
    errors = validate(project, registry)
    assert any("camera" in e and "a1" in e and "a2" in e for e in errors)


# --- Retry loop ---------------------------------------------------------------


def _valid_response() -> str:
    return json.dumps(
        {
            "project": "test",
            "scene": "dark_lab",
            "characters": [{"id": "student", "preset": "student_v1", "spawn": "door"}],
            "shots": [
                {
                    "id": "s1",
                    "start": 0,
                    "end": 2,
                    "camera": "wide",
                    "actions": [
                        {
                            "id": "a1",
                            "type": "idle",
                            "character": "student",
                            "start": 0,
                            "end": 2,
                        }
                    ],
                }
            ],
        }
    )


def _semantically_bad_response() -> str:
    """Schema-valid but references a nonexistent scene."""
    return json.dumps(
        {
            "project": "test",
            "scene": "ghost_dimension",
            "characters": [],
            "shots": [],
        }
    )


def _malformed_json_response() -> str:
    return "this is not json"


def test_retry_succeeds_on_first_attempt(registry: Registry) -> None:
    result = generate_validated_timeline(
        "stand in the lab",
        registry,
        mock_responses=[_valid_response()],
    )
    assert result.scene == "dark_lab"


def test_retry_recovers_from_semantic_error(registry: Registry) -> None:
    result = generate_validated_timeline(
        "stand somewhere",
        registry,
        mock_responses=[_semantically_bad_response(), _valid_response()],
    )
    assert result.scene == "dark_lab"


def test_retry_recovers_from_malformed_json(registry: Registry) -> None:
    result = generate_validated_timeline(
        "stand somewhere",
        registry,
        mock_responses=[_malformed_json_response(), _valid_response()],
    )
    assert result.scene == "dark_lab"


def test_retry_exhausted_raises(registry: Registry) -> None:
    with pytest.raises(TimelineGenerationError) as exc:
        generate_validated_timeline(
            "stand somewhere",
            registry,
            max_attempts=2,
            mock_responses=[_semantically_bad_response(), _semantically_bad_response()],
        )
    assert exc.value.attempts == 2
    assert any("ghost_dimension" in m for m in exc.value.last_feedback)


def test_retry_respects_max_attempts(registry: Registry) -> None:
    # Three bad attempts, max_attempts=3 → raises on attempt 4 never reached.
    with pytest.raises(TimelineGenerationError) as exc:
        generate_validated_timeline(
            "anything",
            registry,
            max_attempts=3,
            mock_responses=[
                _semantically_bad_response(),
                _semantically_bad_response(),
                _semantically_bad_response(),
            ],
        )
    assert exc.value.attempts == 3
