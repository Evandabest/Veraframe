"""Action dispatch — walk a timeline JSON and apply each action.

Called by the daemon as the `execute_timeline` RPC. Looks up target
characters by their `veraframe_handle` custom property (set by
`character_loader.load_character`) and dispatches each action to its
implementation in `actions/`.

Step 9 implements only `idle`; other action types are surfaced in the
response's `skipped` list with a `not yet implemented` reason so the caller
can verify dispatch without failing.
"""

try:
    import bpy
except ImportError:
    bpy = None

from actions import idle as idle_action
from actions import walk_to as walk_to_action


class ExecutorError(RuntimeError):
    """Raised when the executor cannot run at all (e.g. bpy unavailable)."""


_HANDLE_PROP = "veraframe_handle"


def execute_timeline(timeline: dict, asset_paths: dict, fps: int = 24) -> dict:
    """Apply the timeline to currently-loaded characters.

    `asset_paths` maps animation IDs (matching `animation.json` `id` fields)
    to absolute FBX paths so the daemon doesn't have to know the asset layout.

    Returns `{executed: [...], skipped: [...], fps: <n>}` — every action in
    the timeline appears in exactly one of those lists.
    """
    if bpy is None:
        raise ExecutorError("bpy unavailable")

    characters = _index_characters_by_handle()

    executed: list[dict] = []
    skipped: list[dict] = []

    for shot in timeline.get("shots", []):
        for action in shot.get("actions", []):
            atype = action.get("type")
            action_id = action.get("id", "?")

            if atype == "idle":
                _dispatch_idle(action, characters, asset_paths, fps, executed, skipped)
                continue

            if atype == "walk_to":
                _dispatch_walk_to(action, characters, asset_paths, fps, executed, skipped)
                continue

            skipped.append(
                {
                    "id": action_id,
                    "type": atype,
                    "reason": f"action type '{atype}' not yet implemented",
                }
            )

    return {"executed": executed, "skipped": skipped, "fps": fps}


def _dispatch_idle(
    action: dict,
    characters: dict,
    asset_paths: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "idle",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    fbx_path = asset_paths.get("idle")
    if not fbx_path:
        skipped.append(
            {
                "id": action_id,
                "type": "idle",
                "reason": "no idle animation path in asset_paths",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = idle_action.execute(
            armature,
            fbx_path,
            start_frame,
            end_frame,
            action_id=action_id,
        )
    except idle_action.IdleActionError as e:
        skipped.append({"id": action_id, "type": "idle", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "idle", **result})


def _dispatch_walk_to(
    action: dict,
    characters: dict,
    asset_paths: dict,
    fps: int,
    executed: list[dict],
    skipped: list[dict],
) -> None:
    action_id = action.get("id", "?")
    char_id = action.get("character")
    armature = characters.get(char_id)
    if armature is None:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": f"character '{char_id}' not loaded (no armature with that handle)",
            }
        )
        return

    target_name = action.get("target")
    scene = bpy.context.scene
    target_obj = scene.objects.get(target_name) if target_name else None
    if target_obj is None and target_name in characters:
        target_obj = characters[target_name]
    if target_obj is None:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": f"target '{target_name}' not found as spawn point or character",
            }
        )
        return
    target_location = (target_obj.location.x, target_obj.location.y, target_obj.location.z)

    fbx_path = asset_paths.get("walk_in_place")
    if not fbx_path:
        skipped.append(
            {
                "id": action_id,
                "type": "walk_to",
                "reason": "no walk_in_place animation path in asset_paths",
            }
        )
        return

    start_frame = int(action["start"] * fps)
    end_frame = int(action["end"] * fps)

    try:
        result = walk_to_action.execute(
            armature,
            fbx_path,
            target_location,
            start_frame,
            end_frame,
            action_id=action_id,
        )
    except walk_to_action.WalkToActionError as e:
        skipped.append({"id": action_id, "type": "walk_to", "reason": str(e)})
        return

    executed.append({"id": action_id, "type": "walk_to", **result})


def _index_characters_by_handle() -> dict:
    """Map `veraframe_handle` -> armature object for every loaded character."""
    out: dict[str, object] = {}
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        handle = obj.get(_HANDLE_PROP)
        if handle:
            out[handle] = obj
    return out


__all__ = ["ExecutorError", "execute_timeline"]
