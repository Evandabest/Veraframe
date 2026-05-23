"""Point-at action — extend the character's right arm toward a target.

Attaches a Damped Track constraint to `mixamorig:RightForeArm` that aims the
bone's local `+Y` axis (its length axis) at the target, and keyframes the
constraint's `influence` so the arm raises at `start_frame` and drops at
`end_frame`. Same temporal envelope and NLA wiring as `look_at`.

Pointing the FOREARM (not the shoulder) gives a recognizable directional cue
without requiring IK setup with a pole target. The upper arm stays roughly in
rest pose; the forearm rotates to aim the wrist at the target. This reads
clearly as "pointing" from typical camera angles.
"""

try:
    import bpy
except ImportError:
    bpy = None


class PointAtActionError(RuntimeError):
    """Raised when the point_at action can't be placed."""


_ARM_BONE = "mixamorig:RightForeArm"
# Mixamo bones use local +Y as the bone's length axis (elbow → wrist on the
# forearm). TRACK_Y aims that axis at the target — the wrist points at it.
_TRACK_AXIS = "TRACK_Y"


def execute(
    armature,
    target_obj,
    start_frame: int,
    end_frame: int,
    action_id: str = "point_at",
) -> dict:
    """Aim `armature`'s right forearm at `target_obj` over the action window."""
    if bpy is None:
        raise PointAtActionError("bpy unavailable")

    forearm = armature.pose.bones.get(_ARM_BONE)
    if forearm is None:
        raise PointAtActionError(
            f"armature '{armature.name}' has no '{_ARM_BONE}' bone — "
            f"is this a Mixamo-rigged character?"
        )

    constraint_name = f"veraframe_pointat_{action_id}"
    constraint = forearm.constraints.new("DAMPED_TRACK")
    constraint.name = constraint_name
    constraint.target = target_obj
    constraint.track_axis = _TRACK_AXIS
    constraint.influence = 0.0

    if armature.animation_data is None:
        armature.animation_data_create()
    prev_tweak = armature.animation_data.action
    inf_action = bpy.data.actions.new(name=f"veraframe_pointat_{action_id}_a")
    armature.animation_data.action = inf_action

    data_path = f'pose.bones["{_ARM_BONE}"].constraints["{constraint_name}"].influence'
    s, e = int(start_frame), int(end_frame)

    for frame, value in (
        (max(0, s - 1), 0.0),
        (s, 1.0),
        (e, 1.0),
        (e + 1, 0.0),
    ):
        constraint.influence = value
        armature.keyframe_insert(data_path=data_path, frame=frame)

    inf_track = armature.animation_data.nla_tracks.new()
    inf_track.name = f"veraframe_pointat_inf_{action_id}"
    inf_strip = inf_track.strips.new(
        name=f"inf_{action_id}", start=max(0, s - 1), action=inf_action
    )
    # Blender 5.x slot-rebind workaround (see idle.py): without this the
    # constraint-influence keyframes silently evaluate as zero and the
    # arm-pointing IK never gates on/off.
    if hasattr(inf_action, "slots") and len(inf_action.slots):
        inf_strip.action_slot = inf_action.slots[0]
        if hasattr(inf_strip, "action_slot_handle"):
            inf_strip.action_slot_handle = inf_action.slots[0].handle
    inf_strip.blend_type = "ADD"
    inf_strip.extrapolation = "NOTHING"

    armature.animation_data.action = prev_tweak

    return {
        "armature": armature.name,
        "bone": _ARM_BONE,
        "constraint": constraint_name,
        "target": target_obj.name,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["PointAtActionError", "execute"]
