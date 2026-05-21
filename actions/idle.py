"""Idle action — places a Mixamo idle NLA strip on a character's armature.

Runs inside Blender (via the daemon's `execute_timeline` dispatch). Imports
the idle animation FBX once per session, caches the resulting `Action`, and
places it as a Non-Linear Animation strip on the target armature for the
requested frame range.
"""

from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class IdleActionError(RuntimeError):
    """Raised when the idle action can't be placed."""


# Cached `bpy.types.Action` per animation FBX path. The first call for a given
# path imports the FBX, extracts the action, and discards the duplicate
# armature/mesh; subsequent calls reuse the cached action.
_LOADED_ACTIONS: dict[str, object] = {}


def execute(
    armature,
    animation_fbx_path: str,
    start_frame: int,
    end_frame: int,
    action_id: str = "idle",
) -> dict:
    """Place an idle NLA strip on `armature` for `[start_frame, end_frame]`."""
    if bpy is None:
        raise IdleActionError("bpy unavailable")

    action = _load_action(animation_fbx_path)

    if armature.animation_data is None:
        armature.animation_data_create()

    # Note: the FBX T-pose was cleared once in `character_loader.load_character`.
    # Do NOT clear `animation_data.action` here — earlier actions (e.g.
    # walk_to) may have stored location keyframes there and clearing would
    # orphan them.

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_idle_{action_id}"

    strip = track.strips.new(name=action_id, start=int(start_frame), action=action)

    # Blender 5.x slotted actions: explicitly bind the strip to the action's
    # first slot AND update the slot handle. `strips.new()` auto-binds but
    # often picks up a stale handle from the most-recently-created slot in
    # `bpy.data`, which makes the strip silently evaluate as a no-op even
    # though the action and `action_slot` look right. Force-rebind below.
    if hasattr(action, "slots") and len(action.slots):
        strip.action_slot = action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = action.slots[0].handle

    strip.frame_end = int(end_frame)
    # Keep body strips confined to their action window. HOLD extrapolates the
    # first pose backward before the strip start, so a later idle can mask an
    # earlier walk and make the character slide in a frozen stance.
    strip.extrapolation = "NOTHING"

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": int(strip.frame_start),
        "frame_end": int(strip.frame_end),
        "extrapolation": strip.extrapolation,
        "action_name": action.name,
    }


def _load_action(fbx_path: str):
    """Import the animation FBX (once) and return its embedded Action."""
    resolved = str(Path(fbx_path).expanduser().resolve())
    cached = _LOADED_ACTIONS.get(resolved)
    if cached is not None and cached.name in bpy.data.actions:
        return cached

    path = Path(resolved)
    if not path.is_file():
        raise IdleActionError(f"animation file not found: {path}")

    before_actions = set(bpy.data.actions.keys())
    before_objects = set(bpy.data.objects.keys())

    bpy.ops.import_scene.fbx(filepath=str(path))

    new_actions = sorted(set(bpy.data.actions.keys()) - before_actions)
    new_objects = set(bpy.data.objects.keys()) - before_objects

    # Discard the imported armature + mesh; we only want the Action datablock.
    for name in new_objects:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

    if not new_actions:
        raise IdleActionError(f"no action found in {path}")

    action = bpy.data.actions[new_actions[0]]
    _LOADED_ACTIONS[resolved] = action
    return action


__all__ = ["IdleActionError", "execute"]
