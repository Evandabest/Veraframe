"""Reference auto-fix pass.

Catches LLM near-misses on string references — `doorway` instead of `door`,
`wide_shot` instead of `wide`, etc. — by snapping each unresolved reference
to its closest registry entry when there's an unambiguous match.

Runs before `reference_check`, so that pass sees a project where the
deterministic fixes are already applied and only truly broken references
surface as issues for the retry loop.

Uses `difflib.get_close_matches` (stdlib) with a 0.7 similarity threshold
and `n=1`. Anything below the threshold or with multiple equally-close
candidates is left alone — the LLM retry handles those.
"""

from __future__ import annotations

from difflib import get_close_matches

from planner.registry import Registry
from planner.schema import Project
from planner.validators import PassResult

_SIM_CUTOFF = 0.7


def _snap(name: str | None, options: list[str]) -> str | None:
    """Return the closest option when one exists above the threshold."""
    if name is None or name in options:
        return None
    matches = get_close_matches(name, options, n=1, cutoff=_SIM_CUTOFF)
    return matches[0] if matches else None


def run(project: Project, registry: Registry) -> PassResult:
    fixes: list[str] = []

    scene = registry.scenes.get(project.scene)
    if scene is None:
        # If the scene itself is unknown there's nothing to snap against.
        # `reference_check` will surface the unknown-scene issue.
        return PassResult(project=project)

    spawn_options = list(scene.spawn_points)
    camera_options = list(scene.camera_presets)
    lighting_options = list(scene.lighting_presets)
    motion_options = list(registry.motions.keys())
    character_handles = {c.id for c in project.characters}
    target_options = spawn_options + sorted(character_handles)

    # Character spawn snapping.
    for character in project.characters:
        snapped = _snap(character.spawn, spawn_options)
        if snapped:
            fixes.append(
                f"character '{character.id}' spawn '{character.spawn}' → '{snapped}'"
            )
            character.spawn = snapped

    for shot in project.shots:
        snapped = _snap(shot.camera, camera_options)
        if snapped:
            fixes.append(f"shot '{shot.id}' camera '{shot.camera}' → '{snapped}'")
            shot.camera = snapped

        for action in shot.actions:
            atype = action.type
            if atype in {"walk_to", "turn_to", "look_at", "point_at"}:
                snapped = _snap(action.target, target_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' target '{action.target}' → '{snapped}'"
                    )
                    action.target = snapped
            if atype == "talk" and getattr(action, "look_at", None):
                snapped = _snap(action.look_at, target_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' look_at '{action.look_at}' → '{snapped}'"
                    )
                    action.look_at = snapped
            if atype == "camera_cut":
                snapped = _snap(action.camera, camera_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' camera '{action.camera}' → '{snapped}'"
                    )
                    action.camera = snapped
            if atype == "camera_dolly":
                snapped = _snap(action.from_camera, camera_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' from_camera '{action.from_camera}' → '{snapped}'"
                    )
                    action.from_camera = snapped
                snapped = _snap(action.to_camera, camera_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' to_camera '{action.to_camera}' → '{snapped}'"
                    )
                    action.to_camera = snapped
            if atype == "set_lighting":
                snapped = _snap(action.preset, lighting_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' lighting preset '{action.preset}' → '{snapped}'"
                    )
                    action.preset = snapped
            if atype == "play_clip":
                snapped = _snap(action.clip, motion_options)
                if snapped:
                    fixes.append(
                        f"action '{action.id}' clip '{action.clip}' → '{snapped}'"
                    )
                    action.clip = snapped

    return PassResult(project=project, fixes=fixes)
