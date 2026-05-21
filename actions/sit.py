"""Sit action — ramp the leg bones from rest pose into a seated pose."""

try:
    import bpy
except ImportError:
    bpy = None

from actions._seated_pose import REST, SEATED, SEATED_BONES


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
    sit_action = _build_sit_action(armature, action_id, s, e)

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_sit_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=sit_action)
    if hasattr(sit_action, "slots") and len(sit_action.slots):
        strip.action_slot = sit_action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = sit_action.slots[0].handle
    # REPLACE so seated leg poses override the rest pose; HOLD so the seated
    # pose persists after the strip ends (until a `stand` strip ramps it back).
    strip.blend_type = "REPLACE"
    strip.extrapolation = "HOLD"

    return {
        "armature": armature.name,
        "track": track.name,
        "frame_start": s,
        "frame_end": e,
        "bones": list(SEATED_BONES),
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


__all__ = ["SitActionError", "execute"]
