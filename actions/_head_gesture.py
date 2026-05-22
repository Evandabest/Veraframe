"""Shared head-bone oscillation helper used by `nod` and `shake_head`.

Both actions are short oscillations on a single rotation axis of the head
bone, returning to rest at the end. They differ only in (a) the axis they
oscillate around and (b) cosmetics (count of cycles, peak amplitude). The
helper builds a dedicated NLA action with a few quaternion keyframes and
hangs it on its own track with REPLACE blend + NOTHING extrapolation so it
doesn't leak the oscillation past its window.

The head bone name is `mixamorig:Head` for standard Mixamo rigs. We accept
either the prefixed or unprefixed form; tools imported via Blender's FBX
import sometimes strip the prefix.
"""

from __future__ import annotations

import math

try:
    import bpy
except ImportError:
    bpy = None


class HeadGestureError(RuntimeError):
    """Raised when a head-gesture action can't be placed."""


_HEAD_BONE_CANDIDATES = ("mixamorig:Head", "Head")


def _find_head_bone(armature) -> str:
    for name in _HEAD_BONE_CANDIDATES:
        if name in armature.pose.bones:
            return name
    raise HeadGestureError(
        f"armature '{armature.name}' has no head bone (looked for {list(_HEAD_BONE_CANDIDATES)})"
    )


def _axis_unit_quaternion(axis: str, angle_rad: float) -> tuple[float, float, float, float]:
    """Quaternion (w, x, y, z) for `angle_rad` rotation around `axis`.

    axis ∈ {"x", "y", "z"} — interpreted in the bone's local frame.
    """
    half = angle_rad / 2.0
    w = math.cos(half)
    s = math.sin(half)
    if axis == "x":
        return (w, s, 0.0, 0.0)
    if axis == "y":
        return (w, 0.0, s, 0.0)
    if axis == "z":
        return (w, 0.0, 0.0, s)
    raise ValueError(f"unknown axis '{axis}' (expected x/y/z)")


def execute_head_oscillation(
    armature,
    *,
    axis: str,
    amplitude_deg: float,
    cycles: int,
    start_frame: int,
    end_frame: int,
    action_id: str,
    track_prefix: str,
) -> dict:
    """Oscillate the head bone around `axis` for the given frame window.

    Generates `2 * cycles + 1` keyframes:
        rest, +peak, -peak, +peak, ..., rest.
    """
    if bpy is None:
        raise HeadGestureError("bpy unavailable")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise HeadGestureError(f"end_frame ({e}) must be > start_frame ({s})")

    bone_name = _find_head_bone(armature)

    if armature.animation_data is None:
        armature.animation_data_create()

    action = bpy.data.actions.new(name=f"veraframe_{track_prefix}_{action_id}_a")
    prev_tweak = armature.animation_data.action
    armature.animation_data.action = action
    try:
        bone = armature.pose.bones[bone_name]
        bone.rotation_mode = "QUATERNION"
        path = f'pose.bones["{bone_name}"].rotation_quaternion'

        # Generate evenly-spaced frames. For N cycles we want 2N peaks
        # bracketed by rest at the start and end.
        peaks = cycles * 2
        total_keys = peaks + 2  # +2 for the start + end rest keyframes
        amp_rad = math.radians(amplitude_deg)

        rest = (1.0, 0.0, 0.0, 0.0)
        for k in range(total_keys):
            frame = s + round((e - s) * k / max(1, total_keys - 1))
            if k == 0 or k == total_keys - 1:
                q = rest
            else:
                # Alternate sign between peaks: +, -, +, -, ...
                sign = 1.0 if (k - 1) % 2 == 0 else -1.0
                q = _axis_unit_quaternion(axis, amp_rad * sign)
            for idx in range(4):
                bone.rotation_quaternion[idx] = q[idx]
                armature.keyframe_insert(data_path=path, index=idx, frame=frame)

        # Reset live bone state so the next action starts from rest.
        for idx in range(4):
            bone.rotation_quaternion[idx] = rest[idx]
    finally:
        armature.animation_data.action = prev_tweak

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_{track_prefix}_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=action)
    if hasattr(action, "slots") and len(action.slots):
        strip.action_slot = action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = action.slots[0].handle
    strip.blend_type = "REPLACE"
    # Don't HOLD; the gesture should end at rest, not freeze at the last
    # interpolated frame.
    strip.extrapolation = "NOTHING"

    return {
        "armature": armature.name,
        "bone": bone_name,
        "track": track.name,
        "axis": axis,
        "amplitude_deg": amplitude_deg,
        "cycles": cycles,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["HeadGestureError", "execute_head_oscillation"]
