"""Stand action — ramp the leg bones back to rest and lift the body
back up from the seated drop a prior `sit` applied."""

try:
    import bpy
except ImportError:
    bpy = None

from actions._seated_pose import REST, SEATED, SEATED_BONES, SEATED_HIP_DROP_M


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

    # 1. Leg-bone return to rest pose. REPLACE so we overwrite the seated
    #    pose a prior `sit` strip is holding. NOTHING so we don't bleed
    #    into subsequent actions.
    stand_action = _build_stand_action(armature, action_id, s, e)
    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_stand_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=stand_action)
    if hasattr(stand_action, "slots") and len(stand_action.slots):
        strip.action_slot = stand_action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = stand_action.slots[0].handle
    strip.blend_type = "REPLACE"
    strip.extrapolation = "NOTHING"

    # 2. Body lift on a separate ADD-blend track — adds +SEATED_HIP_DROP_M
    #    to the armature z, cancelling whatever the sit strip is holding.
    #    HOLD so the character stays upright after the stand ends.
    lift_action = _build_hip_lift_action(action_id, s, e)
    lift_track = armature.animation_data.nla_tracks.new()
    lift_track.name = f"veraframe_stand_lift_{action_id}"
    lift_strip = lift_track.strips.new(name=f"lift_{action_id}", start=s, action=lift_action)
    lift_strip.blend_type = "ADD"
    lift_strip.extrapolation = "HOLD"

    return {
        "armature": armature.name,
        "track": track.name,
        "lift_track": lift_track.name,
        "frame_start": s,
        "frame_end": e,
        "bones": list(SEATED_BONES),
        "hip_lift_m": SEATED_HIP_DROP_M,
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


def _build_hip_lift_action(action_id: str, start_frame: int, end_frame: int):
    """Keyframe armature.location.z from -SEATED_HIP_DROP_M back to 0
    so the character lifts out of a seated drop a prior `sit` applied.

    Same pattern as sit's drop action — two LINEAR keyframes on the z
    curve, x and y stay at 0 so the ADD blend doesn't move the character
    horizontally.
    """
    lift_action = bpy.data.actions.new(name=f"veraframe_stand_lift_{action_id}_a")
    for axis in range(3):
        fc = lift_action.fcurves.new(data_path="location", index=axis)
        kp0 = fc.keyframe_points.insert(
            frame=float(start_frame),
            value=(SEATED_HIP_DROP_M if axis == 2 else 0.0),
        )
        kp1 = fc.keyframe_points.insert(frame=float(end_frame), value=0.0)
        kp0.interpolation = "LINEAR"
        kp1.interpolation = "LINEAR"
    return lift_action


__all__ = ["StandActionError", "execute"]
