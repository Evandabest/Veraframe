"""Scene loading — open a `.blend` or import a `.fbx`, then report inventory.

Called by the daemon as the `load_scene` RPC. Returns the names of empties
(used as spawn points) and cameras found in the loaded scene, so the caller
can verify the manifest matches what's actually on disk.

Both `.blend` and `.fbx` scenes are supported. `.blend` is the native format
(fast, lossless). `.fbx` is accepted for user convenience — the FBX is
imported into an empty scene; spawn-point Empties and Camera objects must
exist in the FBX with the names the manifest references.

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

    `blend_path` may be a `.blend` (opened via `wm.open_mainfile`) or a
    `.fbx` (imported into a freshly-emptied scene via `import_scene.fbx`).
    File-format choice is detected from the path's extension.

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

    ext = path.suffix.lower()
    if ext == ".blend":
        # `wm.open_mainfile` replaces the running file's contents with the
        # loaded one. It works in background mode (unlike
        # `read_factory_settings`) because it doesn't try to tear down UI
        # regions that don't exist headless.
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif ext == ".fbx":
        # Empty the current scene before importing the FBX so we get just the
        # FBX's contents. `read_factory_settings(use_empty=True)` crashes in
        # background mode, so we batch-remove datablocks directly.
        for collection_name in (
            "objects",
            "meshes",
            "materials",
            "armatures",
            "cameras",
            "lights",
            "images",
            "actions",
            "node_groups",
            "collections",
        ):
            coll = getattr(bpy.data, collection_name, None)
            if coll is not None:
                bpy.data.batch_remove(list(coll))
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise SceneLoadError(
            f"unsupported scene file format '{ext}'; expected .blend or .fbx"
        )

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
