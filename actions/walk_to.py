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
    # Force-rebind the strip's slot (and its handle). See idle.py for context:
    # auto-binding by `strips.new` picks up a stale slot handle that silently
    # makes bone-rotation channels evaluate as no-ops.
    if hasattr(action, "slots") and len(action.slots):
        strip.action_slot = action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = action.slots[0].handle

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

    # CRITICAL: walk_to keyframes `armature.location` via `keyframe_insert`,
    # which APPENDS to whatever action is currently in `animation_data.action`
    # (the "tweak slot"). If a previous action (e.g. look_at's constraint
    # influence keyframes) already lives there, our location keyframes get
    # mixed in — and when we push that combined action to NLA, the strip's
    # frame mapping drifts (action frame range starts at the earliest
    # keyframe across BOTH actions, not at our location keyframes), AND the
    # leftover tweak slot continues to mask bone channels.
    #
    # Solution: temporarily swap in a dedicated empty action, do the
    # location keyframes there, push to its own NLA track with ADD blend
    # (so bone channels pass through), then restore the previous tweak
    # action so other channels (like look_at's constraint influence) keep
    # working.
    start_loc = tuple(armature.location)
    end_loc = tuple(target_location)

    prev_tweak = armature.animation_data.action
    loc_action = bpy.data.actions.new(name=f"veraframe_walk_loc_{action_id}_a")
    armature.animation_data.action = loc_action

    for axis_index in range(3):
        armature.location[axis_index] = start_loc[axis_index]
        armature.keyframe_insert(data_path="location", index=axis_index, frame=int(start_frame))
        armature.location[axis_index] = end_loc[axis_index]
        armature.keyframe_insert(data_path="location", index=axis_index, frame=int(end_frame))

    loc_track = armature.animation_data.nla_tracks.new()
    loc_track.name = f"veraframe_walk_loc_{action_id}"
    loc_strip = loc_track.strips.new(
        name=f"loc_{action_id}", start=int(start_frame), action=loc_action
    )
    loc_strip.blend_type = "ADD"
    loc_strip.extrapolation = "HOLD"

    # Restore the previous tweak action and clear the live static value so
    # ADD blend computes absolute location from the strip (base 0 + curve).
    armature.animation_data.action = prev_tweak
    armature.location = (0.0, 0.0, 0.0)

    # Don't rotate the armature to face the direction of travel. Same reason
    # as in `character_loader.load_character`: setting `rotation_quaternion`
    # on the armature object causes the Mixamo walk action's bone keyframes
    # to behave unexpectedly (the character ends up tilted flat or the bones
    # cancel out the object rotation, depending on the axis chosen). Scenes
    # are expected to place the camera so that the natural Mixamo facing
    # (+Y world) reads well; the character moonwalks sideways if the route
    # is not aligned with +Y. Better facing handling is a follow-up.

    # NOTE: we deliberately leave `armature.location` at (0,0,0) above so the
    # NLA ADD blend computes absolute values from the strip. The character's
    # apparent world position is driven entirely by the strip during the walk
    # and held at the strip's last value afterward (extrapolation = HOLD).
    # The "current location" for subsequent walk_to chaining is end_loc.

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
