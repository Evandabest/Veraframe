"""Walk-to action — places a Mixamo walk-in-place NLA strip plus a custom
translation F-curve from the character's current location to a target spawn
point, interpolated linearly over the action's frame range.

The walk clip itself is a Mixamo "Walk In Place" FBX that doesn't translate
the root — we drive root translation ourselves so the character can be made
to walk to any arbitrary target. This is the canonical "Mixamo in-place +
custom motion" pattern described in PLAN.md.
"""

import math
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class WalkToActionError(RuntimeError):
    """Raised when the walk-to action can't be placed."""


_LOADED_ACTIONS: dict[str, object] = {}
_EFFECTIVE_LOCATION_PROP = "veraframe_effective_location"


def clear_cache() -> None:
    """Drop all cached Action references.

    Called by the daemon's `reset` handler after `bpy.data.batch_remove`
    wipes the scene — leftover entries here would be dead StructRNA
    references that crash on next access.
    """
    _LOADED_ACTIONS.clear()


_STYLE_SPEED_MULTIPLIER: dict[str, float] = {
    # Multiplier applied to the walk clip's repeat count. >1 = legs cycle
    # faster (run / jog feel); <1 = slower (sneak / limp). 'march' is barely
    # faster but accompanied by stiffer body language we don't model yet.
    "walk": 1.0,
    "run": 1.6,
    "jog": 1.3,
    "sneak": 0.65,
    "march": 1.1,
    "limp": 0.75,
}


def execute(
    armature,
    animation_fbx_path: str,
    target_location: tuple[float, float, float],
    start_frame: int,
    end_frame: int,
    action_id: str = "walk",
    style: str | None = None,
    physics_post_pass: bool = True,
) -> dict:
    """Walk `armature` from its current location to `target_location`.

    Places the walk NLA strip (so the legs cycle) and drives armature
    location linearly from current → target over the frame range. `style`
    is one of WalkStyle (walk/run/jog/sneak/march/limp); unknown values
    fall back to 'walk'. Style affects the leg-cycle speed by multiplying
    the strip's repeat count — root translation timing is unchanged so the
    character still arrives exactly at end_frame.

    When `physics_post_pass` is True (default), the strip's repeat count
    is computed from the actual travel distance so foot-plants land at
    the same world position regardless of walk duration — eliminating
    most foot-slide. Pass False to fall back to the legacy duration-only
    formula (e.g. for A/B comparisons).
    """
    if bpy is None:
        raise WalkToActionError("bpy unavailable")

    action = _load_action(animation_fbx_path)

    if armature.animation_data is None:
        armature.animation_data_create()

    # Note: the FBX T-pose was cleared once in `character_loader.load_character`.

    stored_start = armature.get(_EFFECTIVE_LOCATION_PROP)
    if stored_start is not None and len(stored_start) == 3:
        start_loc = tuple(float(v) for v in stored_start)
        loc_action_start = (0.0, 0.0, 0.0)
        loc_action_end = tuple(float(target_location[i]) - start_loc[i] for i in range(3))
    else:
        start_loc = tuple(armature.location)
        loc_action_start = start_loc
        loc_action_end = tuple(target_location)
    end_loc = tuple(target_location)

    # Build the translation action on a temporary object rather than by
    # assigning `armature.animation_data.action`. A generic object-location
    # action can be reused as an NLA strip on the armature without disturbing
    # any direct-action/tweak-slot state owned by other actions.
    loc_action = _make_location_action(
        action_id=action_id,
        start_loc=loc_action_start,
        end_loc=loc_action_end,
        start_frame=int(start_frame),
        end_frame=int(end_frame),
    )

    loc_track = armature.animation_data.nla_tracks.new()
    loc_track.name = f"veraframe_walk_loc_{action_id}"
    loc_strip = loc_track.strips.new(
        name=f"loc_{action_id}", start=int(start_frame), action=loc_action
    )
    loc_strip.blend_type = "ADD"
    loc_strip.extrapolation = "HOLD"

    # Clear the live static value so ADD blend computes absolute location
    # from the strip (base 0 + curve).
    armature.location = (0.0, 0.0, 0.0)

    # Create the imported body strip separately from the root-translation
    # strip. Root motion holds position after the walk; body motion should only
    # affect frames inside the walk window.
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
    # while our location keyframes slide the character. Set `repeat` to span
    # the requested duration. We deliberately do NOT touch `strip.frame_end`
    # because assigning frame_end resets repeat back to 1.0 in Blender 5.x.
    action_length = max(1.0, action.frame_range[1] - action.frame_range[0])
    desired_duration = max(1.0, int(end_frame) - int(start_frame))
    speed_mult = _STYLE_SPEED_MULTIPLIER.get(style or "walk", 1.0)

    if physics_post_pass:
        # Foot-aligned formula (Step 52): repeat tracks travel distance so
        # the planted-foot phase falls on a fixed world position regardless
        # of walk duration.
        from blender_daemon.physics import compute_walk_repeat

        distance_m = math.sqrt(
            (end_loc[0] - start_loc[0]) ** 2
            + (end_loc[1] - start_loc[1]) ** 2
            + (end_loc[2] - start_loc[2]) ** 2
        )
        strip.repeat = compute_walk_repeat(
            distance_m=distance_m, duration_s=desired_duration, speed_mult=speed_mult
        )
    else:
        # Legacy formula — duration-only. Kept for back-compat.
        strip.repeat = (desired_duration / action_length) * speed_mult
    # The translation strip below holds world position after the walk. The
    # body strip itself must not hold outside the walk window, or it can mask
    # subsequent body actions on overlapping NLA evaluation.
    strip.extrapolation = "NOTHING"

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
    armature[_EFFECTIVE_LOCATION_PROP] = list(end_loc)

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": int(strip.frame_start),
        "frame_end": int(strip.frame_end),
        "repeat": strip.repeat,
        "extrapolation": strip.extrapolation,
        "action_name": action.name,
        "start_location": list(start_loc),
        "end_location": list(end_loc),
    }


def _make_location_action(
    *,
    action_id: str,
    start_loc: tuple[float, float, float],
    end_loc: tuple[float, float, float],
    start_frame: int,
    end_frame: int,
):
    loc_action = bpy.data.actions.new(name=f"veraframe_walk_loc_{action_id}_a")
    dummy = bpy.data.objects.new(f"veraframe_walk_loc_source_{action_id}", None)
    bpy.context.scene.collection.objects.link(dummy)
    try:
        dummy.animation_data_create()
        dummy.animation_data.action = loc_action
        for axis_index in range(3):
            dummy.location[axis_index] = start_loc[axis_index]
            dummy.keyframe_insert(data_path="location", index=axis_index, frame=start_frame)
            dummy.location[axis_index] = end_loc[axis_index]
            dummy.keyframe_insert(data_path="location", index=axis_index, frame=end_frame)
    finally:
        bpy.data.objects.remove(dummy, do_unlink=True)
    return loc_action


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
