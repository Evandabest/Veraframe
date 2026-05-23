"""Orbit camera action — sweep the active camera in a circle around a target.

Reads the active camera's position at start_frame, computes its vector from
the target in the XY plane, then keyframes additional positions at
end_frame so the camera describes a circular arc of `degrees` (positive =
counterclockwise viewed from +Z) around the target's vertical axis. Camera
height and look-at point are held constant — the camera always tracks the
target.

Linear interpolation between two keyframes produces a chord rather than a
true arc, which on short orbits (~30°) reads fine. For longer orbits the
animator can split into multiple orbit actions chained back-to-back, or we
add intermediate keyframes here in a future pass.
"""

from __future__ import annotations

import math

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None


class OrbitError(RuntimeError):
    """Raised when the orbit action can't be placed."""


def execute(
    target_obj,
    start_frame: int,
    end_frame: int,
    degrees: float,
    action_id: str = "orbit",
) -> dict:
    if bpy is None or mathutils is None:
        raise OrbitError("bpy / mathutils unavailable")

    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        raise OrbitError("no active scene camera to drive")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise OrbitError(f"end_frame ({e}) must be > start_frame ({s})")

    prev_frame = scene.frame_current
    try:
        scene.frame_set(s)
        cam_start = cam.matrix_world.translation.copy()
        target_pos = target_obj.matrix_world.translation.copy()
    finally:
        scene.frame_set(prev_frame)

    # Polar offset in the XY plane around the target's vertical axis.
    offset_x = cam_start.x - target_pos.x
    offset_y = cam_start.y - target_pos.y
    radius = math.hypot(offset_x, offset_y)
    if radius < 1e-3:
        raise OrbitError(
            f"orbit: camera is on top of target '{target_obj.name}' (XY); pick a different target"
        )
    start_angle = math.atan2(offset_y, offset_x)
    sweep = math.radians(degrees)
    end_angle = start_angle + sweep

    cam_end = mathutils.Vector(
        (
            target_pos.x + radius * math.cos(end_angle),
            target_pos.y + radius * math.sin(end_angle),
            cam_start.z,
        )
    )

    # Camera looks at target at start and end (approximately constant height).
    look_at = mathutils.Vector((target_pos.x, target_pos.y, target_pos.z + 1.2))
    rot_start = (look_at - cam_start).to_track_quat("-Z", "Y")
    rot_end = (look_at - cam_end).to_track_quat("-Z", "Y")

    cam.rotation_mode = "QUATERNION"
    for axis_idx in range(3):
        cam.location[axis_idx] = cam_start[axis_idx]
        cam.keyframe_insert(data_path="location", index=axis_idx, frame=s)
        cam.location[axis_idx] = cam_end[axis_idx]
        cam.keyframe_insert(data_path="location", index=axis_idx, frame=e)
    for q_idx in range(4):
        cam.rotation_quaternion[q_idx] = rot_start[q_idx]
        cam.keyframe_insert(data_path="rotation_quaternion", index=q_idx, frame=s)
        cam.rotation_quaternion[q_idx] = rot_end[q_idx]
        cam.keyframe_insert(data_path="rotation_quaternion", index=q_idx, frame=e)

    return {
        "camera": cam.name,
        "target": target_obj.name,
        "radius": radius,
        "degrees": degrees,
        "start_angle_deg": math.degrees(start_angle),
        "end_angle_deg": math.degrees(end_angle),
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["OrbitError", "execute"]
