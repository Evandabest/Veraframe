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
    already_seated: bool = False,
) -> dict:
    """Place a sit on `armature` for `[start_frame, end_frame]`.

    When `already_seated` is True, the previous sit's body-drop ADD strip
    is still HOLDing at -SEATED_HIP_DROP_M; placing another drop strip
    would ADD another -SEATED_HIP_DROP_M on top, sinking the character
    into the floor. In that case we skip the drop track and only place
    the leg-pose strip (a redundant REPLACE over the same held pose,
    visually identical to the prior sit's hold).
    """
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

    # 2. Body drop on a separate ADD-blend track. Skipped when the
    #    character is already seated to avoid compounding the drop.
    drop_track_name: str | None = None
    if not already_seated:
        drop_action = _build_hip_drop_action(action_id, s, e)
        drop_track = armature.animation_data.nla_tracks.new()
        drop_track.name = f"veraframe_sit_drop_{action_id}"
        drop_strip = drop_track.strips.new(
            name=f"drop_{action_id}", start=s, action=drop_action
        )
        drop_strip.blend_type = "ADD"
        drop_strip.extrapolation = "HOLD"
        drop_track_name = drop_track.name

    return {
        "armature": armature.name,
        "track": track.name,
        "drop_track": drop_track_name,
        "frame_start": s,
        "frame_end": e,
        "bones": list(SEATED_BONES),
        "hip_drop_m": 0.0 if already_seated else SEATED_HIP_DROP_M,
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
    """Keyframe object.location.z from 0 down to -SEATED_HIP_DROP_M.

    Mirrors walk_to._make_location_action: build the curves on a temp
    Empty so Blender 5.x's slotted-action machinery sets up the
    slot/layer/strip/channelbag for us. We then remove the Empty and
    apply the Action to the armature via an ADD-blend NLA strip — only
    the location channels matter on the armature.
    """
    drop_action = bpy.data.actions.new(name=f"veraframe_sit_drop_{action_id}_a")
    dummy = bpy.data.objects.new(f"veraframe_sit_drop_source_{action_id}", None)
    bpy.context.scene.collection.objects.link(dummy)
    try:
        dummy.animation_data_create()
        dummy.animation_data.action = drop_action
        for axis_index in range(3):
            dummy.location[axis_index] = 0.0
            dummy.keyframe_insert(data_path="location", index=axis_index, frame=start_frame)
            dummy.location[axis_index] = -SEATED_HIP_DROP_M if axis_index == 2 else 0.0
            dummy.keyframe_insert(data_path="location", index=axis_index, frame=end_frame)
    finally:
        bpy.data.objects.remove(dummy, do_unlink=True)
    return drop_action


__all__ = ["SitActionError", "execute"]
