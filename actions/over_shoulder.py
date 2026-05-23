"""Over-the-shoulder camera action — frame B from over A's shoulder.

Heuristic placement:
- Direction = B − A (in XY plane).
- Camera sits behind A along the −direction, offset slightly sideways so
  A's shoulder appears in the corner of the frame (not centered behind A
  blocking B).
- Camera height = mid-torso of A (~1.3m above floor).
- Camera looks at B's upper torso (~1.4m).

Single keyframe at start_frame; camera holds for the duration.
"""

from __future__ import annotations

import math

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None


class OverShoulderError(RuntimeError):
    """Raised when the over-shoulder action can't be placed."""


def execute(
    a_armature,
    b_armature,
    start_frame: int,
    end_frame: int,
    action_id: str = "over_shoulder",
) -> dict:
    if bpy is None or mathutils is None:
        raise OverShoulderError("bpy / mathutils unavailable")

    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        raise OverShoulderError("no active scene camera to drive")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise OverShoulderError(f"end_frame ({e}) must be > start_frame ({s})")

    prev_frame = scene.frame_current
    try:
        scene.frame_set(s)
        pa = a_armature.matrix_world.translation.copy()
        pb = b_armature.matrix_world.translation.copy()
    finally:
        scene.frame_set(prev_frame)

    direction_xy = mathutils.Vector((pb.x - pa.x, pb.y - pa.y))
    if direction_xy.length < 1e-4:
        raise OverShoulderError(
            f"over_shoulder: a ('{a_armature.name}') and b ('{b_armature.name}') "
            "are at the same XY position"
        )
    direction_xy.normalize()
    # Perpendicular for the sideways offset. Rotating 90° clockwise places
    # the camera on A's left shoulder (frame-right of the subject).
    perp_xy = mathutils.Vector((direction_xy.y, -direction_xy.x))

    # Tunables. Distance behind A is ~0.7m so the shoulder dominates the
    # corner of the frame; sideways offset 0.35m to put A's silhouette to
    # one side without obscuring B.
    back_dist = 0.7
    side_dist = 0.35
    cam_pos = mathutils.Vector(
        (
            pa.x - direction_xy.x * back_dist + perp_xy.x * side_dist,
            pa.y - direction_xy.y * back_dist + perp_xy.y * side_dist,
            pa.z + 1.55,  # eye-line of A
        )
    )
    look_at = mathutils.Vector((pb.x, pb.y, pb.z + 1.4))
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
        "back_distance": back_dist,
        "side_distance": side_dist,
        "look_at_yaw_deg": math.degrees(math.atan2(direction_xy.x, -direction_xy.y)),
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["OverShoulderError", "execute"]
