"""Camera cut action — switch the active scene camera at a specified frame
by binding a timeline marker to the named camera.

Blender's animation renderer respects timeline-marker camera bindings: when
playback crosses a marker bound to a camera, the active camera switches to
that camera until the next bound marker. This is the canonical way to do
per-shot cuts inside one rendered animation.
"""

try:
    import bpy
except ImportError:
    bpy = None


class CameraCutActionError(RuntimeError):
    """Raised when the camera cut can't be placed."""


def execute(scene, camera_name: str, start_frame: int, action_id: str = "camera_cut") -> dict:
    if bpy is None:
        raise CameraCutActionError("bpy unavailable")

    camera_obj = scene.objects.get(camera_name)
    if camera_obj is None:
        raise CameraCutActionError(f"camera '{camera_name}' not found in scene '{scene.name}'")
    if camera_obj.type != "CAMERA":
        raise CameraCutActionError(f"object '{camera_name}' is type {camera_obj.type}, not CAMERA")

    # IMPORTANT: assigning a camera to a marker immediately overwrites
    # `scene.camera` with that camera. If this is the first camera_cut in
    # the timeline and no anchor marker exists for the original active
    # camera, drop one at the scene's start frame so frames BEFORE the cut
    # keep using the original camera. Must happen before the new marker
    # bind, otherwise scene.camera will already have been clobbered.
    existing_cam_markers = [m for m in scene.timeline_markers if m.camera is not None]
    if not existing_cam_markers and scene.camera is not None and scene.camera is not camera_obj:
        anchor_frame = max(0, scene.frame_start)
        anchor = scene.timeline_markers.new(
            name="veraframe_initial_camera", frame=anchor_frame
        )
        anchor.camera = scene.camera

    marker_name = f"veraframe_cut_{action_id}"
    marker = scene.timeline_markers.new(marker_name, frame=int(start_frame))
    marker.camera = camera_obj

    return {
        "marker": marker_name,
        "camera": camera_name,
        "frame": int(start_frame),
    }


__all__ = ["CameraCutActionError", "execute"]
