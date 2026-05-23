"""Reference resolution pass.

Verifies every cross-reference in the timeline points at something that
actually exists in the registry: scene id, character preset, spawn
point, camera preset, lighting preset, motion clip id. Shot windows
contain their actions.

This pass does NOT auto-fix references — typos in spawn points / cameras
go to the LLM via the retry loop with a "here are valid options"
message. (A future closest-name auto-fix can be added; today the
LLM-driven correction is the only path.)
"""

from __future__ import annotations

from planner.registry import Registry
from planner.schema import Project
from planner.validators import PassResult


def run(project: Project, registry: Registry) -> PassResult:
    issues: list[str] = []

    scene = registry.scenes.get(project.scene)
    if scene is None:
        available = ", ".join(sorted(registry.scenes)) or "(none)"
        issues.append(
            f"scene '{project.scene}' is not in the registry. Available scenes: {available}"
        )
        return PassResult(project=project, issues=issues)

    character_ids: set[str] = set()
    for character in project.characters:
        character_ids.add(character.id)
        if character.preset not in registry.characters:
            available = ", ".join(sorted(registry.characters)) or "(none)"
            issues.append(
                f"character '{character.id}' uses preset '{character.preset}' which is not in the registry. "
                f"Available presets: {available}"
            )
        if character.spawn not in scene.spawn_points:
            issues.append(
                f"character '{character.id}' spawns at '{character.spawn}' which is not a spawn point in scene "
                f"'{project.scene}'. Valid spawn points: {', '.join(scene.spawn_points)}"
            )

    for shot in project.shots:
        if shot.camera not in scene.camera_presets:
            issues.append(
                f"shot '{shot.id}' uses camera '{shot.camera}' which is not in scene '{project.scene}'. "
                f"Valid cameras: {', '.join(scene.camera_presets)}"
            )

        for action in shot.actions:
            if action.start < shot.start or action.end > shot.end:
                issues.append(
                    f"action '{action.id}' window {action.start}-{action.end} falls outside parent shot "
                    f"'{shot.id}' window {shot.start}-{shot.end}"
                )
            issues.extend(_check_action_references(action, scene, character_ids, registry))

    return PassResult(project=project, issues=issues)


def _check_action_references(
    action, scene, character_ids: set[str], registry: Registry
) -> list[str]:
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
            errors.append(
                _target_error(action.id, action.target, "target", scene, character_ids)
            )

    if action_type == "talk" and getattr(action, "look_at", None) is not None:
        if not _is_valid_target(action.look_at, scene, character_ids):
            errors.append(
                _target_error(action.id, action.look_at, "look_at", scene, character_ids)
            )

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

    if action_type == "play_clip":
        if action.clip not in registry.motions:
            available = ", ".join(sorted(registry.motions)) or "(none)"
            errors.append(
                f"action '{action.id}' play_clip references motion '{action.clip}' which is not in the "
                f"registry. Available motion clips: {available}"
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
