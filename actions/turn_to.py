"""Turn-to action — rotate the character around its vertical axis to face a target.

Computes a target Z-yaw from the XY direction to `target_obj`, builds a dedicated
rotation action with two keyframes (start yaw → target yaw), and pushes it to its
own NLA track with ADD blend. Mirrors `walk_to`'s location-action pattern so the
rotation does not pollute the armature's tweak slot or mask other bone channels.

A Mixamo X-Bot at `rotation_euler = (0, 0, 0)` naturally faces world `-Y`. After a
Z-rotation by θ, the character's facing direction is `(sin θ, -cos θ)`. To face a
target at offset `(dx, dy)`, we solve `θ = atan2(dx, -dy)`.
"""

import math

try:
    import bpy
except ImportError:
    bpy = None


class TurnToActionError(RuntimeError):
    """Raised when the turn_to action can't be placed."""


_EFFECTIVE_YAW_PROP = "veraframe_effective_yaw"
# Mirrors walk_to's custom property. Walk_to animates location via an
# ADD-blend NLA strip and leaves the static `armature.location` at
# (0,0,0); the strip only takes effect during render. So we cannot trust
# `armature.matrix_world.translation` at dispatch time to reflect the
# character's post-walk position — walk_to writes the end position into
# this custom property and turn_to reads it back here.
_EFFECTIVE_LOCATION_PROP = "veraframe_effective_location"


def execute(
    armature,
    target_obj,
    start_frame: int,
    end_frame: int,
    action_id: str = "turn_to",
) -> dict:
    """Rotate `armature` between frames so its facing aligns with `target_obj`."""
    if bpy is None:
        raise TurnToActionError("bpy unavailable")

    if armature.animation_data is None:
        armature.animation_data_create()

    # Prefer the stored effective location (set by the most recent walk_to)
    # over the armature's static world translation — see comment on the
    # constant above.
    stored_loc = armature.get(_EFFECTIVE_LOCATION_PROP)
    if stored_loc is not None and len(stored_loc) == 3:
        arm_x, arm_y, _ = (float(v) for v in stored_loc)
    else:
        arm_world = armature.matrix_world.translation
        arm_x, arm_y = arm_world.x, arm_world.y

    target_pos = target_obj.matrix_world.translation
    dx = target_pos.x - arm_x
    dy = target_pos.y - arm_y
    if dx == 0.0 and dy == 0.0:
        raise TurnToActionError(
            f"target '{target_obj.name}' is at the same XY position as armature '{armature.name}'"
        )

    target_yaw = math.atan2(dx, -dy)

    stored_yaw = armature.get(_EFFECTIVE_YAW_PROP)
    start_yaw = (
        float(stored_yaw)
        if stored_yaw is not None
        else float(armature.rotation_euler.z)
    )

    # Keyframe DELTA, not absolute. The previous turn_to's strip is still
    # ADD+HOLD-ing at `start_yaw`; adding an absolute-keyframed new strip
    # on top would double the rotation. Mirror what walk_to does for
    # translation: keyframe (0 → delta) so the ADD blend composes
    # cleanly with the previous hold.
    delta_yaw = target_yaw - start_yaw
    rot_action = _make_rotation_action(
        action_id=action_id,
        start_yaw=0.0,
        end_yaw=delta_yaw,
        start_frame=int(start_frame),
        end_frame=int(end_frame),
    )

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_turnto_{action_id}"
    strip = track.strips.new(
        name=f"rot_{action_id}", start=int(start_frame), action=rot_action
    )
    # ADD blend over a rest rotation of (0, 0, 0) plus the previous
    # turn_to's HOLD. The strip keyframes a delta so the total yaw is
    # the sum of all previous holds + this delta. After this strip
    # HOLDs at `delta_yaw`, the cumulative ADD across all turn_to
    # strips equals `target_yaw` — which is exactly what we want.
    strip.blend_type = "ADD"
    strip.extrapolation = "HOLD"

    # Force-rebind the slot, mirroring walk_to/idle.
    if hasattr(rot_action, "slots") and len(rot_action.slots):
        strip.action_slot = rot_action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = rot_action.slots[0].handle

    # Clear live rotation so the ADD blend evaluates to the strip's absolute value.
    armature.rotation_euler[2] = 0.0

    armature[_EFFECTIVE_YAW_PROP] = target_yaw

    return {
        "armature": armature.name,
        "track": track.name,
        "target": target_obj.name,
        "frame_start": int(strip.frame_start),
        "frame_end": int(strip.frame_end),
        "start_yaw": start_yaw,
        "end_yaw": target_yaw,
    }


def _make_rotation_action(
    *,
    action_id: str,
    start_yaw: float,
    end_yaw: float,
    start_frame: int,
    end_frame: int,
):
    rot_action = bpy.data.actions.new(name=f"veraframe_turnto_{action_id}_a")
    dummy = bpy.data.objects.new(f"veraframe_turnto_source_{action_id}", None)
    bpy.context.scene.collection.objects.link(dummy)
    try:
        dummy.animation_data_create()
        dummy.animation_data.action = rot_action
        # rotation_mode defaults to "XYZ" Euler; we drive index 2 only.
        dummy.rotation_euler[2] = start_yaw
        dummy.keyframe_insert(data_path="rotation_euler", index=2, frame=start_frame)
        dummy.rotation_euler[2] = end_yaw
        dummy.keyframe_insert(data_path="rotation_euler", index=2, frame=end_frame)
    finally:
        bpy.data.objects.remove(dummy, do_unlink=True)
    return rot_action


__all__ = ["TurnToActionError", "execute"]
