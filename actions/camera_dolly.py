"""Camera dolly action — interpolate the active camera between two named
cameras over a frame range.

Creates a temporary "dolly" camera that copies the lens of `from_camera`,
keyframes its location and quaternion-rotation from `from_camera`'s pose to
`to_camera`'s pose across the action frame range, and binds it to a timeline
marker at `start_frame`. A second marker at `end_frame` switches the active
camera to `to_camera` so the dolly only governs the in-between frames.

Quaternion rotation gives a smoother shortest-path interpolation than Euler
when the two cameras face significantly different directions.
"""

try:
    import bpy
except ImportError:
    bpy = None


class CameraDollyActionError(RuntimeError):
    """Raised when the camera dolly can't be placed."""


def execute(
    scene,
    from_camera_name: str,
    to_camera_name: str,
    start_frame: int,
    end_frame: int,
    action_id: str = "camera_dolly",
) -> dict:
    if bpy is None:
        raise CameraDollyActionError("bpy unavailable")

    from_cam = scene.objects.get(from_camera_name)
    if from_cam is None or from_cam.type != "CAMERA":
        raise CameraDollyActionError(
            f"from_camera '{from_camera_name}' not a camera in scene '{scene.name}'"
        )
    to_cam = scene.objects.get(to_camera_name)
    if to_cam is None or to_cam.type != "CAMERA":
        raise CameraDollyActionError(
            f"to_camera '{to_camera_name}' not a camera in scene '{scene.name}'"
        )

    # See camera_cut.execute: assigning a camera to a marker clobbers
    # scene.camera, so the initial-camera anchor must be dropped before the
    # first marker bind.
    existing_cam_markers = [m for m in scene.timeline_markers if m.camera is not None]
    if not existing_cam_markers and scene.camera is not None:
        anchor_frame = max(0, scene.frame_start)
        anchor = scene.timeline_markers.new(
            name="veraframe_initial_camera", frame=anchor_frame
        )
        anchor.camera = scene.camera

    dolly_data = bpy.data.cameras.new(f"veraframe_dolly_{action_id}_data")
    dolly_data.lens = from_cam.data.lens
    dolly_obj = bpy.data.objects.new(f"veraframe_dolly_{action_id}", dolly_data)
    scene.collection.objects.link(dolly_obj)
    dolly_obj.rotation_mode = "QUATERNION"

    start_loc = tuple(from_cam.matrix_world.translation)
    end_loc = tuple(to_cam.matrix_world.translation)
    start_quat = from_cam.matrix_world.to_quaternion()
    end_quat = to_cam.matrix_world.to_quaternion()

    s = int(start_frame)
    e = int(end_frame)

    for axis in range(3):
        dolly_obj.location[axis] = start_loc[axis]
        dolly_obj.keyframe_insert(data_path="location", index=axis, frame=s)
        dolly_obj.location[axis] = end_loc[axis]
        dolly_obj.keyframe_insert(data_path="location", index=axis, frame=e)

    for idx, value in enumerate(start_quat):
        dolly_obj.rotation_quaternion[idx] = value
        dolly_obj.keyframe_insert(data_path="rotation_quaternion", index=idx, frame=s)
    for idx, value in enumerate(end_quat):
        dolly_obj.rotation_quaternion[idx] = value
        dolly_obj.keyframe_insert(data_path="rotation_quaternion", index=idx, frame=e)

    start_marker = scene.timeline_markers.new(
        f"veraframe_dolly_start_{action_id}", frame=s
    )
    start_marker.camera = dolly_obj

    end_marker = scene.timeline_markers.new(f"veraframe_dolly_end_{action_id}", frame=e)
    end_marker.camera = to_cam

    return {
        "dolly_camera": dolly_obj.name,
        "from_camera": from_camera_name,
        "to_camera": to_camera_name,
        "start_marker": start_marker.name,
        "end_marker": end_marker.name,
        "frame_start": s,
        "frame_end": e,
    }


__all__ = ["CameraDollyActionError", "execute"]
