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

    # Keyframe influence: 0 just before start, 1 at start..end, 0 just after.
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

    return {
        "armature": armature.name,
        "bone": _HEAD_BONE,
        "constraint": constraint_name,
        "target": target_obj.name,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["LookAtActionError", "execute"]
