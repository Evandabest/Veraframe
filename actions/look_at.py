"""Look-at action — make the character's head track a target during a window.

Adds a Damped Track constraint to the `mixamorig:Head` pose bone targeting
the named object (or another loaded character's armature) and keyframes the
constraint's `influence` so the head locks on at `start_frame` and releases
at `end_frame`.

Damped Track is preferred over Track To because it doesn't try to maintain a
secondary "up" axis — it just points the chosen local axis at the target,
producing a clean head-turn without surprise roll.
"""

try:
    import bpy
except ImportError:
    bpy = None


class LookAtActionError(RuntimeError):
    """Raised when the look_at action can't be placed."""


_HEAD_BONE = "mixamorig:Head"
# Empirical: the Mixamo head bone's "face forward" direction is local +Z
# (verified by checking the head bone's local axes against the rest-pose
# facing direction). TRACK_Z aims local +Z at the target, which orients the
# face correctly. If a different rig has different axis conventions, this
# is the knob to tweak.
_TRACK_AXIS = "TRACK_Z"


def execute(
    armature,
    target_obj,
    start_frame: int,
    end_frame: int,
    action_id: str = "look_at",
) -> dict:
    """Constrain the head bone of `armature` to track `target_obj` from
    `start_frame` to `end_frame`.

    `target_obj` must already exist in the scene (caller resolves it from a
    spawn-point name or another character handle).
    """
    if bpy is None:
        raise LookAtActionError("bpy unavailable")

    head = armature.pose.bones.get(_HEAD_BONE)
    if head is None:
        raise LookAtActionError(
            f"armature '{armature.name}' has no '{_HEAD_BONE}' bone — "
            f"is this a Mixamo-rigged character?"
        )

    constraint_name = f"veraframe_lookat_{action_id}"
    constraint = head.constraints.new("DAMPED_TRACK")
    constraint.name = constraint_name
    constraint.target = target_obj
    constraint.track_axis = _TRACK_AXIS
    constraint.influence = 0.0

    # Keyframe influence into a DEDICATED action that we push to NLA, not
    # the shared "tweak slot" (animation_data.action). Sharing the tweak
    # slot across actions causes downstream problems: bone channels in the
    # slot's domain get reset by REPLACE evaluation, and other actions
    # that also keyframe via `armature.keyframe_insert` end up appending
    # to this same action, producing weird frame-range overlap.
    if armature.animation_data is None:
        armature.animation_data_create()
    prev_tweak = armature.animation_data.action
    inf_action = bpy.data.actions.new(name=f"veraframe_lookat_{action_id}_a")
    armature.animation_data.action = inf_action

    data_path = f'pose.bones["{_HEAD_BONE}"].constraints["{constraint_name}"].influence'
    s, e = int(start_frame), int(end_frame)

    for frame, value in (
        (max(0, s - 1), 0.0),
        (s, 1.0),
        (e, 1.0),
        (e + 1, 0.0),
    ):
        constraint.influence = value
        armature.keyframe_insert(data_path=data_path, frame=frame)

    # Push the influence action to its own NLA track with ADD blend so bone
    # rotation channels pass through cleanly.
    inf_track = armature.animation_data.nla_tracks.new()
    inf_track.name = f"veraframe_lookat_inf_{action_id}"
    inf_strip = inf_track.strips.new(
        name=f"inf_{action_id}", start=max(0, s - 1), action=inf_action
    )
    # Blender 5.x slot-rebind workaround (see idle.py): without this the
    # constraint-influence keyframes silently evaluate as zero and the
    # head-tracking never gates on/off.
    if hasattr(inf_action, "slots") and len(inf_action.slots):
        inf_strip.action_slot = inf_action.slots[0]
        if hasattr(inf_strip, "action_slot_handle"):
            inf_strip.action_slot_handle = inf_action.slots[0].handle
    inf_strip.blend_type = "ADD"
    inf_strip.extrapolation = "NOTHING"

    # Restore any prior tweak action.
    armature.animation_data.action = prev_tweak

    return {
        "armature": armature.name,
        "bone": _HEAD_BONE,
        "constraint": constraint_name,
        "target": target_obj.name,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["LookAtActionError", "execute"]
