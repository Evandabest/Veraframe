"""Track-subject camera action — active camera follows a character.

Animates the active scene camera's location + rotation so it sits at a
behind-and-above offset relative to the target character throughout the
action window. We sample the character's location at start_frame and
end_frame (via `scene.frame_set` for accurate eval of walk-to curves) and
keyframe the camera between those positions. Linear interpolation between
the two endpoints assumes the character's underlying motion is also linear
(true for walk_to), which is fine for the MVP.

Camera rotation is computed at start/end via `to_track_quat` so the camera
points at the character.
"""

from __future__ import annotations

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None


class TrackSubjectError(RuntimeError):
    """Raised when the track_subject action can't be placed."""


# Camera offset relative to the character at the moment of capture, in world
# coordinates. The character faces -Y at rest (Mixamo convention) so a +Y
# offset puts the camera in front of the character.
_DEFAULT_OFFSET = (0.0, -5.0, 1.8)


def execute(
    armature,
    start_frame: int,
    end_frame: int,
    action_id: str = "track_subject",
) -> dict:
    if bpy is None or mathutils is None:
        raise TrackSubjectError("bpy / mathutils unavailable")

    scene = bpy.context.scene
    cam = scene.camera
    if cam is None:
        raise TrackSubjectError("no active scene camera to drive")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise TrackSubjectError(f"end_frame ({e}) must be > start_frame ({s})")

    # Sample the character's position at the start + end of the window. We
    # round-trip through frame_set so any walk_to keyframes that were already
    # placed get correctly evaluated.
    prev_frame = scene.frame_current
    try:
        scene.frame_set(s)
        char_start = armature.matrix_world.translation.copy()
        scene.frame_set(e)
        char_end = armature.matrix_world.translation.copy()
    finally:
        scene.frame_set(prev_frame)

    ox, oy, oz = _DEFAULT_OFFSET
    cam_start = mathutils.Vector((char_start.x + ox, char_start.y + oy, char_start.z + oz))
    cam_end = mathutils.Vector((char_end.x + ox, char_end.y + oy, char_end.z + oz))

    # Camera looks at the character (slightly above their feet so the head
    # frames in the center).
    look_start = mathutils.Vector((char_start.x, char_start.y, char_start.z + 1.4))
    look_end = mathutils.Vector((char_end.x, char_end.y, char_end.z + 1.4))

    rot_start = (look_start - cam_start).to_track_quat("-Z", "Y")
    rot_end = (look_end - cam_end).to_track_quat("-Z", "Y")

    cam.rotation_mode = "QUATERNION"

    # Two keyframes per channel (start + end). Linear interpolation in between.
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
        "character": armature.name,
        "frame_start": s,
        "frame_end": e,
        "offset": list(_DEFAULT_OFFSET),
    }


__all__ = ["TrackSubjectError", "execute"]
