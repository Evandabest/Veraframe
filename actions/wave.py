"""Wave action — raise the right arm and oscillate the forearm.

Bone-rotation animation on Mixamo's `RightArm` (upper) and `RightForeArm`.
The upper arm rotates up and slightly out at the start, holds for the
duration, then returns to rest; meanwhile the forearm oscillates side to
side a few times to read as a wave.
"""

from __future__ import annotations

import math

try:
    import bpy
except ImportError:
    bpy = None


class WaveActionError(RuntimeError):
    """Raised when the wave action can't be placed."""


_UPPER_ARM_CANDIDATES = ("mixamorig:RightArm", "RightArm")
_FOREARM_CANDIDATES = ("mixamorig:RightForeArm", "RightForeArm")


def _find_bone(armature, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in armature.pose.bones:
            return name
    raise WaveActionError(
        f"armature '{armature.name}' missing one of {list(candidates)}"
    )


def _axis_quaternion(axis: str, angle_rad: float) -> tuple[float, float, float, float]:
    half = angle_rad / 2.0
    w = math.cos(half)
    s = math.sin(half)
    return {
        "x": (w, s, 0.0, 0.0),
        "y": (w, 0.0, s, 0.0),
        "z": (w, 0.0, 0.0, s),
    }[axis]


def execute(armature, start_frame: int, end_frame: int, action_id: str = "wave") -> dict:
    if bpy is None:
        raise WaveActionError("bpy unavailable")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise WaveActionError(f"end_frame ({e}) must be > start_frame ({s})")

    upper = _find_bone(armature, _UPPER_ARM_CANDIDATES)
    forearm = _find_bone(armature, _FOREARM_CANDIDATES)

    if armature.animation_data is None:
        armature.animation_data_create()

    action = bpy.data.actions.new(name=f"veraframe_wave_{action_id}_a")
    prev_tweak = armature.animation_data.action
    armature.animation_data.action = action
    try:
        rest = (1.0, 0.0, 0.0, 0.0)
        # Upper-arm raise. We rotate ~80° around Z and slightly around X to
        # bring the arm up and forward. Exact axis behavior depends on bone
        # roll; this approximates a friendly waving position for Mixamo X-Bot.
        raise_q = _axis_quaternion("z", math.radians(-80.0))
        # Forearm oscillation amplitude.
        wave_amp = math.radians(35.0)

        upper_path = f'pose.bones["{upper}"].rotation_quaternion'
        forearm_path = f'pose.bones["{forearm}"].rotation_quaternion'
        armature.pose.bones[upper].rotation_mode = "QUATERNION"
        armature.pose.bones[forearm].rotation_mode = "QUATERNION"

        # Upper-arm timing: ramp up over first ~15%, hold, ramp down over last ~15%.
        ramp_in = s + int((e - s) * 0.15)
        ramp_out = s + int((e - s) * 0.85)

        for idx in range(4):
            armature.pose.bones[upper].rotation_quaternion[idx] = rest[idx]
            armature.keyframe_insert(data_path=upper_path, index=idx, frame=s)
            armature.pose.bones[upper].rotation_quaternion[idx] = raise_q[idx]
            armature.keyframe_insert(data_path=upper_path, index=idx, frame=ramp_in)
            armature.pose.bones[upper].rotation_quaternion[idx] = raise_q[idx]
            armature.keyframe_insert(data_path=upper_path, index=idx, frame=ramp_out)
            armature.pose.bones[upper].rotation_quaternion[idx] = rest[idx]
            armature.keyframe_insert(data_path=upper_path, index=idx, frame=e)

        # Forearm oscillation: 4 peaks evenly between ramp_in and ramp_out,
        # bracketed by rest at the start (s) and end (e).
        peaks = 4
        for k in range(peaks + 2):
            frame = s + round((e - s) * k / max(1, peaks + 1))
            if k == 0 or k == peaks + 1:
                q = rest
            else:
                sign = 1.0 if (k - 1) % 2 == 0 else -1.0
                q = _axis_quaternion("y", wave_amp * sign)
            for idx in range(4):
                armature.pose.bones[forearm].rotation_quaternion[idx] = q[idx]
                armature.keyframe_insert(data_path=forearm_path, index=idx, frame=frame)

        # Reset live bone state.
        for bone_name in (upper, forearm):
            for idx in range(4):
                armature.pose.bones[bone_name].rotation_quaternion[idx] = rest[idx]
    finally:
        armature.animation_data.action = prev_tweak

    track = armature.animation_data.nla_tracks.new()
    track.name = f"veraframe_wave_{action_id}"
    strip = track.strips.new(name=action_id, start=s, action=action)
    if hasattr(action, "slots") and len(action.slots):
        strip.action_slot = action.slots[0]
        if hasattr(strip, "action_slot_handle"):
            strip.action_slot_handle = action.slots[0].handle
    strip.blend_type = "REPLACE"
    strip.extrapolation = "NOTHING"

    return {
        "armature": armature.name,
        "bones": [upper, forearm],
        "track": track.name,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["WaveActionError", "execute"]
