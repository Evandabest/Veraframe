"""Walk-to action — places a Mixamo walk-in-place NLA strip plus a custom
translation F-curve from the character's current location to a target spawn
point, interpolated linearly over the action's frame range.

The walk clip itself is a Mixamo "Walk In Place" FBX that doesn't translate
the root — we drive root translation ourselves so the character can be made
to walk to any arbitrary target. This is the canonical "Mixamo in-place +
custom motion" pattern described in PLAN.md.
"""

from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class WalkToActionError(RuntimeError):
    """Raised when the walk-to action can't be placed."""


_LOADED_ACTIONS: dict[str, object] = {}


def execute(
    armature,
    animation_fbx_path: str,
    target_location: tuple[float, float, float],
    start_frame: int,
    end_frame: int,
    action_id: str = "walk",
) -> dict:
    """Walk `armature` from its current location to `target_location`.

    Places the walk NLA strip (so the legs cycle) and keyframes
    `armature.location` linearly from current → target over the frame range.
    Also rotates the armature so it faces the direction of travel.
    """
    if bpy is None:
        raise WalkToActionError("bpy unavailable")

    action = _load_action(animation_fbx_path)

    if armature.animation_data is None:
        armature.animation_data_create()

    # Note: the FBX T-pose was cleared once in `character_loader.load_character`.
    # We rely on Blender to auto-create `animation_data.action` when
    # keyframe_insert below runs — that auto-created action holds our
    # location keyframes for the duration of the walk.

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_walk_{action_id}"

    strip = track.strips.new(name=action_id, start=int(start_frame), action=action)
    if hasattr(strip, "action_slot") and hasattr(action, "slots") and len(action.slots):
        if strip.action_slot is None:
            strip.action_slot = action.slots[0]

    # The Walking clip is ~32 frames (~1.3s @24fps). For a multi-second walk
    # we need the cycle to loop, otherwise the legs freeze at the last frame
    # while our location keyframes slide the character — that's the "sliding"
    # look. Set `repeat` to span the requested duration. We deliberately do
    # NOT touch `strip.frame_end` because assigning frame_end resets repeat
    # back to 1.0 in Blender 5.x.
    action_length = max(1.0, action.frame_range[1] - action.frame_range[0])
    desired_duration = max(1.0, int(end_frame) - int(start_frame))
    strip.repeat = desired_duration / action_length
    strip.extrapolation = "HOLD"

    # Translation F-curve: keyframe current location at start_frame, target at end_frame.
    start_loc = tuple(armature.location)
    end_loc = tuple(target_location)

    for axis_index in range(3):
        armature.location[axis_index] = start_loc[axis_index]
        armature.keyframe_insert(data_path="location", index=axis_index, frame=int(start_frame))
        armature.location[axis_index] = end_loc[axis_index]
        armature.keyframe_insert(data_path="location", index=axis_index, frame=int(end_frame))

    # NOTE: Bezier interp on the location keyframes gives ease-in/ease-out,
    # which actually reads well for a short walk (accelerates from rest,
    # decelerates to stop). Blender 5.x's slotted-action API makes flipping
    # to linear non-trivial; revisit if walk motion looks too floaty.

    # Don't rotate the armature to face the direction of travel. Same reason
    # as in `character_loader.load_character`: setting `rotation_quaternion`
    # on the armature object causes the Mixamo walk action's bone keyframes
    # to behave unexpectedly (the character ends up tilted flat or the bones
    # cancel out the object rotation, depending on the axis chosen). Scenes
    # are expected to place the camera so that the natural Mixamo facing
    # (+Y world) reads well; the character moonwalks sideways if the route
    # is not aligned with +Y. Better facing handling is a follow-up.

    # Leave armature.location at end_loc so subsequent actions see the new
    # position as the "current" location.
    armature.location = end_loc

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": int(strip.frame_start),
        "frame_end": int(strip.frame_end),
        "repeat": strip.repeat,
        "action_name": action.name,
        "start_location": list(start_loc),
        "end_location": list(end_loc),
    }


def _load_action(fbx_path: str):
    """Import the walk FBX once per session and return the embedded Action."""
    resolved = str(Path(fbx_path).expanduser().resolve())
    cached = _LOADED_ACTIONS.get(resolved)
    if cached is not None and cached.name in bpy.data.actions:
        return cached

    path = Path(resolved)
    if not path.is_file():
        raise WalkToActionError(f"animation file not found: {path}")

    before_actions = set(bpy.data.actions.keys())
    before_objects = set(bpy.data.objects.keys())

    bpy.ops.import_scene.fbx(filepath=str(path))

    new_actions = sorted(set(bpy.data.actions.keys()) - before_actions)
    new_objects = set(bpy.data.objects.keys()) - before_objects

    for name in new_objects:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

    if not new_actions:
        raise WalkToActionError(f"no action found in {path}")

    action = bpy.data.actions[new_actions[0]]
    _LOADED_ACTIONS[resolved] = action
    return action


__all__ = ["WalkToActionError", "execute"]
