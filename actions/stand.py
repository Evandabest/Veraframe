"""Stand action — ramp the leg bones from the seated pose back to rest."""

try:
    import bpy
except ImportError:
    bpy = None

from actions._seated_pose import REST, SEATED, SEATED_BONES


class StandActionError(RuntimeError):
    """Raised when the stand action can't be placed."""


def execute(
    armature,
    start_frame: int,
    end_frame: int,
    action_id: str = "stand",
) -> dict:
    if bpy is None:
        raise StandActionError("bpy unavailable")

    missing = [b for b in SEATED_BONES if b not in armature.pose.bones]
    if missing:
        raise StandActionError(
            f"armature '{armature.name}' missing required bones: {missing}"
        )

    if armature.animation_data is None:
        armature.animation_data_create()

    s, e = int(start_frame), int(end_frame)
    stand_action = _build_stand_action(armature, action_id, s, e)

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_stand_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=stand_action)
    if hasattr(stand_action, "slots") and len(stand_action.slots):
        strip.action_slot = stand_action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = stand_action.slots[0].handle
    # REPLACE so we overwrite whatever seated pose a prior `sit` strip held.
    # NOTHING extrapolation so the stand effect ends cleanly at end_frame and
    # subsequent actions see the rest pose, not held mid-stand.
    strip.blend_type = "REPLACE"
    strip.extrapolation = "NOTHING"

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": s,
        "frame_end": e,
        "bones": list(SEATED_BONES),
    }


def _build_stand_action(armature, action_id: str, start_frame: int, end_frame: int):
    """Keyframe leg bones SEATED → REST so the strip ramps back to standing."""
    stand_action = bpy.data.actions.new(name=f"veraframe_stand_{action_id}_a")
    prev_tweak = armature.animation_data.action
    armature.animation_data.action = stand_action

    for bone_name in SEATED_BONES:
        bone = armature.pose.bones[bone_name]
        bone.rotation_mode = "QUATERNION"
        path = f'pose.bones["{bone_name}"].rotation_quaternion'

        start_pose = SEATED[bone_name]
        for idx in range(4):
            bone.rotation_quaternion[idx] = start_pose[idx]
            armature.keyframe_insert(data_path=path, index=idx, frame=start_frame)
        for idx in range(4):
            bone.rotation_quaternion[idx] = REST[idx]
            armature.keyframe_insert(data_path=path, index=idx, frame=end_frame)

    for bone_name in SEATED_BONES:
        bone = armature.pose.bones[bone_name]
        for idx in range(4):
            bone.rotation_quaternion[idx] = REST[idx]
    armature.animation_data.action = prev_tweak

    return stand_action


__all__ = ["StandActionError", "execute"]
