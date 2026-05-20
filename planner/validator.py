"""Semantic validation of a `Project` against a `Registry`, plus the retry loop
that wraps `planner.llm_client.generate_timeline` and feeds validation errors
back to the model.

Schema-level validation (required fields, types, enums, end>start) is enforced
by Pydantic in `planner.schema`. This module catches the layer above that:
"does this scene actually have that spawn point? does this action reference a
character we declared? do two body actions on the same character overlap?"
"""

from collections import defaultdict
from collections.abc import Sequence

from pydantic import ValidationError

from planner.llm_client import LLMConfig, generate_timeline
from planner.registry import Registry
from planner.schema import Project

# Channels used to detect overlap conflicts between actions on the same character.
# Two actions in the same channel on the same character may not have overlapping
# time windows. Endpoints touching (a.end == b.start) is not an overlap.
_PER_CHARACTER_CHANNELS: list[tuple[str, frozenset[str]]] = [
    ("body", frozenset({"walk_to", "idle", "turn_to", "sit", "stand"})),
    ("face_expression", frozenset({"smile", "frown"})),
    ("talk", frozenset({"talk"})),
    ("look_at", frozenset({"look_at"})),
    ("point_at", frozenset({"point_at"})),
]
_GLOBAL_CHANNELS: list[tuple[str, frozenset[str]]] = [
    ("camera", frozenset({"camera_cut", "camera_dolly"})),
    ("lighting", frozenset({"set_lighting"})),
]


class TimelineGenerationError(RuntimeError):
    """Raised by `generate_validated_timeline` when retries are exhausted."""

    def __init__(self, attempts: int, last_feedback: list[str]) -> None:
        self.attempts = attempts
        self.last_feedback = list(last_feedback)
        joined = "\n".join(f"- {m}" for m in last_feedback)
        super().__init__(f"giving up after {attempts} attempt(s). Last errors:\n{joined}")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate(project: Project, registry: Registry) -> list[str]:
    """Return human-readable error messages, empty list = valid."""
    errors: list[str] = []

    scene = registry.scenes.get(project.scene)
    if scene is None:
        available = ", ".join(sorted(registry.scenes)) or "(none)"
        errors.append(
            f"scene '{project.scene}' is not in the registry. Available scenes: {available}"
        )
        return errors

    character_ids: set[str] = set()
    for character in project.characters:
        character_ids.add(character.id)
        if character.preset not in registry.characters:
            available = ", ".join(sorted(registry.characters)) or "(none)"
            errors.append(
                f"character '{character.id}' uses preset '{character.preset}' which is not in the registry. "
                f"Available presets: {available}"
            )
        if character.spawn not in scene.spawn_points:
            errors.append(
                f"character '{character.id}' spawns at '{character.spawn}' which is not a spawn point in scene "
                f"'{project.scene}'. Valid spawn points: {', '.join(scene.spawn_points)}"
            )

    for shot in project.shots:
        if shot.camera not in scene.camera_presets:
            errors.append(
                f"shot '{shot.id}' uses camera '{shot.camera}' which is not in scene '{project.scene}'. "
                f"Valid cameras: {', '.join(scene.camera_presets)}"
            )

        for action in shot.actions:
            if action.start < shot.start or action.end > shot.end:
                errors.append(
                    f"action '{action.id}' window {action.start}-{action.end} falls outside parent shot "
                    f"'{shot.id}' window {shot.start}-{shot.end}"
                )
            errors.extend(_validate_action_references(action, scene, character_ids))

        errors.extend(_check_channel_conflicts(shot))

    return errors


def _validate_action_references(action, scene, character_ids: set[str]) -> list[str]:
    """Per-action reference checks (character, target, camera, etc.)."""
    errors: list[str] = []
    action_type = action.type

    if hasattr(action, "character") and action.character not in character_ids:
        declared = ", ".join(sorted(character_ids)) or "(none)"
        errors.append(
            f"action '{action.id}' references character '{action.character}' which is not declared. "
            f"Declared characters: {declared}"
        )

    if action_type in {"walk_to", "turn_to", "look_at", "point_at"}:
        if not _is_valid_target(action.target, scene, character_ids):
            errors.append(_target_error(action.id, action.target, "target", scene, character_ids))

    if action_type == "talk" and action.look_at is not None:
        if not _is_valid_target(action.look_at, scene, character_ids):
            errors.append(_target_error(action.id, action.look_at, "look_at", scene, character_ids))

    if action_type == "camera_cut":
        if action.camera not in scene.camera_presets:
            errors.append(_camera_error(action.id, action.camera, "camera", scene))

    if action_type == "camera_dolly":
        if action.from_camera not in scene.camera_presets:
            errors.append(_camera_error(action.id, action.from_camera, "from_camera", scene))
        if action.to_camera not in scene.camera_presets:
            errors.append(_camera_error(action.id, action.to_camera, "to_camera", scene))

    if action_type == "set_lighting":
        if action.preset not in scene.lighting_presets:
            presets = ", ".join(scene.lighting_presets) or "(none)"
            errors.append(
                f"action '{action.id}' sets lighting preset '{action.preset}' which is not in scene "
                f"'{scene.id}'. Valid presets: {presets}"
            )

    return errors


def _is_valid_target(name: str, scene, character_ids: set[str]) -> bool:
    return name in scene.spawn_points or name in character_ids


def _target_error(action_id: str, name: str, field: str, scene, character_ids: set[str]) -> str:
    spawns = ", ".join(scene.spawn_points)
    chars = ", ".join(sorted(character_ids)) or "(none)"
    return (
        f"action '{action_id}' {field} '{name}' is neither a spawn point in scene '{scene.id}' "
        f"nor a declared character. Spawn points: {spawns}. Characters: {chars}"
    )


def _camera_error(action_id: str, name: str, field: str, scene) -> str:
    cams = ", ".join(scene.camera_presets)
    return (
        f"action '{action_id}' {field} '{name}' is not a camera preset in scene '{scene.id}'. "
        f"Valid cameras: {cams}"
    )


def _check_channel_conflicts(shot) -> list[str]:
    """Detect overlapping actions on the same channel."""
    errors: list[str] = []
    buckets: dict[tuple[str, str | None], list] = defaultdict(list)

    for action in shot.actions:
        for channel_name, types in _PER_CHARACTER_CHANNELS:
            if action.type in types and hasattr(action, "character"):
                buckets[(channel_name, action.character)].append(action)
        for channel_name, types in _GLOBAL_CHANNELS:
            if action.type in types:
                buckets[(channel_name, None)].append(action)

    for (channel, owner), actions in buckets.items():
        actions.sort(key=lambda a: a.start)
        for i, a in enumerate(actions):
            for b in actions[i + 1 :]:
                if a.end <= b.start:
                    break  # sorted; no later b can overlap with a either
                where = f"character '{owner}'" if owner is not None else "scene"
                errors.append(
                    f"actions '{a.id}' ({a.start}-{a.end}) and '{b.id}' ({b.start}-{b.end}) both occupy "
                    f"the '{channel}' channel for {where} during shot '{shot.id}'"
                )

    return errors


# ---------------------------------------------------------------------------
# Retry loop
# ---------------------------------------------------------------------------


def generate_validated_timeline(
    prompt: str,
    registry: Registry,
    config: LLMConfig | None = None,
    *,
    max_attempts: int = 3,
    mock_responses: Sequence[str] | None = None,
) -> Project:
    """Generate a `Project`, feeding validation errors back to the model on failure.

    Each attempt re-prompts the model with the prior attempt's errors. Returns
    the first `Project` that passes both Pydantic and semantic validation.

    Raises `TimelineGenerationError` when `max_attempts` is exhausted without
    success. `mock_responses` is for offline tests: a list of canned model
    outputs, one per attempt.
    """
    last_feedback: list[str] = []

    for attempt in range(max_attempts):
        mock = (
            mock_responses[attempt]
            if mock_responses is not None and attempt < len(mock_responses)
            else None
        )

        attempt_prompt = prompt
        if last_feedback:
            joined = "\n".join(f"- {m}" for m in last_feedback)
            attempt_prompt = (
                f"{prompt}\n\n"
                f"# Errors from your previous attempt — fix all of these and try again:\n{joined}"
            )

        try:
            project = generate_timeline(attempt_prompt, registry, config=config, mock_response=mock)
        except ValidationError as e:
            last_feedback = [
                f"output did not match schema: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}"
            ]
            continue
        except ValueError as e:
            last_feedback = [f"output was not valid JSON: {e}"]
            continue

        semantic_errors = validate(project, registry)
        if not semantic_errors:
            return project
        last_feedback = semantic_errors

    raise TimelineGenerationError(attempts=max_attempts, last_feedback=last_feedback)


__all__ = [
    "TimelineGenerationError",
    "generate_validated_timeline",
    "validate",
]
