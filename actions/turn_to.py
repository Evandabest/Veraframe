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

    arm_pos = armature.matrix_world.translation
    target_pos = target_obj.matrix_world.translation
    dx = target_pos.x - arm_pos.x
    dy = target_pos.y - arm_pos.y
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

    rot_action = _make_rotation_action(
        action_id=action_id,
        start_yaw=start_yaw,
        end_yaw=target_yaw,
        start_frame=int(start_frame),
        end_frame=int(end_frame),
    )

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_turnto_{action_id}"
    strip = track.strips.new(
        name=f"rot_{action_id}", start=int(start_frame), action=rot_action
    )
    # ADD blend over a rest rotation of (0, 0, 0) → the strip value IS the
    # absolute yaw during the strip window. extrapolation=HOLD keeps the final
    # yaw in place after the strip ends so subsequent actions see the new
    # facing.
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
