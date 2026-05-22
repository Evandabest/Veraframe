"""Two-shot camera action — frame two characters together.

Computes a camera position perpendicular to the line connecting characters
A and B, at a distance that scales with their separation so both fit in
frame. Static for the action's duration (single keyframe at start_frame;
camera holds via NLA HOLD-extrapolation on subsequent actions).

Heuristic: midpoint between A and B becomes the look-at target. Camera is
placed `distance = max(3.0, 1.8 * separation)` units away along a vector
perpendicular to the A-B line in the XY plane, slightly raised in Z.
"""

from __future__ import annotations

import math

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None


class TwoShotError(RuntimeError):
    """Raised when the two_shot action can't be placed."""


def execute(
    a_armature,
    b_armature,
    start_frame: int,
    end_frame: int,
    action_id: str = "two_shot",
) -> dict:
    if bpy is None or mathutils is None:
        raise TwoShotError("bpy / mathutils unavailable")

    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        raise TwoShotError("no active scene camera to drive")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise TwoShotError(f"end_frame ({e}) must be > start_frame ({s})")

    # Evaluate character positions at start_frame so we honor any walk_to
    # keyframes already placed.
    prev_frame = scene.frame_current
    try:
        scene.frame_set(s)
        pa = a_armature.matrix_world.translation.copy()
        pb = b_armature.matrix_world.translation.copy()
    finally:
        scene.frame_set(prev_frame)

    midpoint = mathutils.Vector(((pa.x + pb.x) / 2, (pa.y + pb.y) / 2, (pa.z + pb.z) / 2))
    separation = (pa - pb).length

    # Perpendicular direction in XY plane. If A and B are at the same XY,
    # fall back to +Y (in front of the default Mixamo facing).
    line_xy = mathutils.Vector((pb.x - pa.x, pb.y - pa.y))
    if line_xy.length < 1e-4:
        perp = mathutils.Vector((0.0, 1.0, 0.0))
    else:
        # Rotate 90° clockwise: (x, y) → (y, -x). Negate the rotated y so the
        # camera lands in front of -Y-facing characters by default.
        perp = mathutils.Vector((line_xy.y, -line_xy.x, 0.0)).normalized()

    distance = max(3.0, 1.8 * separation)
    cam_pos = mathutils.Vector(
        (
            midpoint.x + perp.x * distance,
            midpoint.y + perp.y * distance,
            midpoint.z + 1.6,
        )
    )

    look_at = mathutils.Vector((midpoint.x, midpoint.y, midpoint.z + 1.2))
    rot = (look_at - cam_pos).to_track_quat("-Z", "Y")

    cam.rotation_mode = "QUATERNION"
    for axis_idx in range(3):
        cam.location[axis_idx] = cam_pos[axis_idx]
        cam.keyframe_insert(data_path="location", index=axis_idx, frame=s)
    for q_idx in range(4):
        cam.rotation_quaternion[q_idx] = rot[q_idx]
        cam.keyframe_insert(data_path="rotation_quaternion", index=q_idx, frame=s)

    return {
        "camera": cam.name,
        "a": a_armature.name,
        "b": b_armature.name,
        "midpoint": [midpoint.x, midpoint.y, midpoint.z],
        "separation": separation,
        "distance": distance,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["TwoShotError", "execute"]
