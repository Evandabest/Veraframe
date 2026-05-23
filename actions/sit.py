"""Sit action — ramp the leg bones into a seated pose AND drop the body
down to a seated hip height so the character isn't hovering on an
invisible chair."""

try:
    import bpy
except ImportError:
    bpy = None

from actions._seated_pose import REST, SEATED, SEATED_BONES, SEATED_HIP_DROP_M


class SitActionError(RuntimeError):
    """Raised when the sit action can't be placed."""


def execute(
    armature,
    start_frame: int,
    end_frame: int,
    action_id: str = "sit",
) -> dict:
    if bpy is None:
        raise SitActionError("bpy unavailable")

    missing = [b for b in SEATED_BONES if b not in armature.pose.bones]
    if missing:
        raise SitActionError(
            f"armature '{armature.name}' missing required bones: {missing}"
        )

    if armature.animation_data is None:
        armature.animation_data_create()

    s, e = int(start_frame), int(end_frame)

    # 1. Leg-bone seated pose on a REPLACE-blend track. HOLD makes the
    #    seated leg shape persist after the strip ends.
    sit_action = _build_sit_action(armature, action_id, s, e)
    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_sit_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=sit_action)
    if hasattr(sit_action, "slots") and len(sit_action.slots):
        strip.action_slot = sit_action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = sit_action.slots[0].handle
    strip.blend_type = "REPLACE"
    strip.extrapolation = "HOLD"

    # 2. Body drop on a separate ADD-blend track. The armature's z drops
    #    from 0 to -SEATED_HIP_DROP_M over the sit duration; HOLD keeps
    #    it lowered after the strip ends (until `stand` adds the inverse).
    #    Same ADD-blend pattern walk_to uses for travel, so the two
    #    compose cleanly (e.g. walk to a chair, then sit there).
    drop_action = _build_hip_drop_action(action_id, s, e)
    drop_track = armature.animation_data.nla_tracks.new()
    drop_track.name = f"veraframe_sit_drop_{action_id}"
    drop_strip = drop_track.strips.new(name=f"drop_{action_id}", start=s, action=drop_action)
    drop_strip.blend_type = "ADD"
    drop_strip.extrapolation = "HOLD"

    return {
        "armature": armature.name,
        "track": track.name,
        "drop_track": drop_track.name,
        "frame_start": s,
        "frame_end": e,
        "bones": list(SEATED_BONES),
        "hip_drop_m": SEATED_HIP_DROP_M,
    }


def _build_sit_action(armature, action_id: str, start_frame: int, end_frame: int):
    """Keyframe leg bones from REST → SEATED on a dedicated action.

    Uses the temporary-tweak-slot pattern: swap in a fresh action, insert
    keyframes via `armature.keyframe_insert`, swap the tweak slot back. The
    fresh action then holds only our two-frame leg-bone curves.
    """
    sit_action = bpy.data.actions.new(name=f"veraframe_sit_{action_id}_a")
    prev_tweak = armature.animation_data.action
    armature.animation_data.action = sit_action

    for bone_name in SEATED_BONES:
        bone = armature.pose.bones[bone_name]
        bone.rotation_mode = "QUATERNION"
        path = f'pose.bones["{bone_name}"].rotation_quaternion'

        for idx in range(4):
            bone.rotation_quaternion[idx] = REST[idx]
            armature.keyframe_insert(data_path=path, index=idx, frame=start_frame)
        target = SEATED[bone_name]
        for idx in range(4):
            bone.rotation_quaternion[idx] = target[idx]
            armature.keyframe_insert(data_path=path, index=idx, frame=end_frame)

    # Reset live bone state and restore tweak slot.
    for bone_name in SEATED_BONES:
        bone = armature.pose.bones[bone_name]
        for idx in range(4):
            bone.rotation_quaternion[idx] = REST[idx]
    armature.animation_data.action = prev_tweak

    return sit_action


def _build_hip_drop_action(action_id: str, start_frame: int, end_frame: int):
    """Keyframe armature.location.z from 0 down to -SEATED_HIP_DROP_M.

    Built on a temp empty object so we can keyframe the location channel
    without touching the armature's tweak slot or any pose-bone state.
    The Action will be applied to the armature via the NLA strip — only
    the location curves matter; Blender ignores object-type-mismatched
    channels when the strip runs against the armature.
    """
    drop_action = bpy.data.actions.new(name=f"veraframe_sit_drop_{action_id}_a")
    # Build the FCurves directly so we don't need a temp owner object.
    for axis in range(3):
        fc = drop_action.fcurves.new(data_path="location", index=axis)
        # Two keyframes: rest at start, dropped at end. Only the Z curve
        # carries a real value; X and Y stay at 0 so the ADD blend is a
        # pure vertical offset that composes with walk_to's translation.
        kp0 = fc.keyframe_points.insert(frame=float(start_frame), value=0.0)
        kp1 = fc.keyframe_points.insert(
            frame=float(end_frame),
            value=(-SEATED_HIP_DROP_M if axis == 2 else 0.0),
        )
        kp0.interpolation = "LINEAR"
        kp1.interpolation = "LINEAR"
    return drop_action


__all__ = ["SitActionError", "execute"]
