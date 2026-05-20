"""Scene loading — open a `.blend` and report its inventory.

Called by the daemon as the `load_scene` RPC. Returns the names of empties
(used as spawn points) and cameras found in the loaded scene, so the caller
can verify the manifest matches what's actually on disk.

Runs inside Blender; `bpy` must be available at call time. Imported in the
daemon process unconditionally so we guard the import here too for unit tests
that exercise the module without Blender.
"""

from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class SceneLoadError(RuntimeError):
    """Raised when a scene file can't be loaded or fails inventory."""


def load_scene(blend_path: str) -> dict:
    """Open `blend_path` as the active scene and return its inventory.

    Inventory returned:

    - `scene_name`: the active scene name after load
    - `spawn_points`: sorted names of `EMPTY` objects in the active scene
    - `cameras`: sorted names of `CAMERA` objects in the active scene
    - `object_count`: total object count in the active scene
    """
    if bpy is None:
        raise SceneLoadError("bpy is not available; load_scene must run inside Blender")

    path = Path(blend_path).expanduser().resolve()
    if not path.is_file():
        raise SceneLoadError(f"scene file not found: {path}")

    # `wm.open_mainfile` replaces the running file's contents with the loaded
    # one. It works in background mode (unlike `read_factory_settings`) because
    # it doesn't try to tear down UI regions that don't exist headless.
    bpy.ops.wm.open_mainfile(filepath=str(path))

    scene = bpy.context.scene
    spawn_points = sorted(obj.name for obj in scene.objects if obj.type == "EMPTY")
    cameras = sorted(obj.name for obj in scene.objects if obj.type == "CAMERA")

    return {
        "scene_name": scene.name,
        "spawn_points": spawn_points,
        "cameras": cameras,
        "object_count": len(scene.objects),
    }


__all__ = ["SceneLoadError", "load_scene"]
