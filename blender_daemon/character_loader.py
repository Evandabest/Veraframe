"""Character loading — import a rigged FBX and place at a spawn point.

Called by the daemon as the `load_character` RPC. Imports the character's
mesh and armature into the active scene, places the armature at the named
spawn point, and returns an inventory the caller can validate.

Mixamo bone-name validation and VRM blendshape presence are reported via the
returned `warnings` list rather than raising — missing blendshapes are
expected for many test characters (e.g. the default Mixamo X Bot has none).
"""

from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


class CharacterLoadError(RuntimeError):
    """Raised when a character FBX can't be loaded."""


_HANDLE_PROP = "veraframe_handle"


def load_character(
    fbx_path: str,
    spawn_point: str,
    handle: str | None = None,
) -> dict:
    """Import `fbx_path`, place its armature at `spawn_point`, return inventory.

    Returns a dict with:

    - `handle`: caller-supplied or auto-generated string used to reference this
      character later
    - `armature_name`: name of the imported armature in `bpy.data.objects`
    - `mesh_names`: names of imported skinned mesh objects
    - `bone_count`: total bones in the armature
    - `mixamo_bone_count`: bones whose name starts with `mixamorig:`
    - `blendshapes`: union of shape-key names across all imported meshes
    - `spawn_location`: [x, y, z] the armature was placed at
    - `warnings`: list of human-readable strings (non-fatal issues)
    """
    if bpy is None:
        raise CharacterLoadError("bpy is not available; load_character must run inside Blender")

    path = Path(fbx_path).expanduser().resolve()
    if not path.is_file():
        raise CharacterLoadError(f"character file not found: {path}")

    scene = bpy.context.scene
    spawn_obj = scene.objects.get(spawn_point)
    if spawn_obj is None:
        raise CharacterLoadError(
            f"spawn point '{spawn_point}' not in active scene "
            f"'{scene.name}'. Available: {sorted(o.name for o in scene.objects)}"
        )
    spawn_location = (spawn_obj.location.x, spawn_obj.location.y, spawn_obj.location.z)

    before_objects = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=str(path))
    new_object_names = set(bpy.data.objects.keys()) - before_objects
    new_objects = [bpy.data.objects[name] for name in new_object_names]

    armatures = [obj for obj in new_objects if obj.type == "ARMATURE"]
    if not armatures:
        raise CharacterLoadError(f"no armature found in {path.name}")
    armature = armatures[0]

    bone_names = [b.name for b in armature.data.bones]
    mixamo_bones = [n for n in bone_names if n.startswith("mixamorig:")]

    meshes = [obj for obj in new_objects if obj.type == "MESH"]
    blendshapes: set[str] = set()
    for mesh in meshes:
        keys = mesh.data.shape_keys
        if keys is None:
            continue
        blendshapes.update(k.name for k in keys.key_blocks)

    warnings: list[str] = []
    if not mixamo_bones:
        warnings.append(
            f"armature '{armature.name}' has no `mixamorig:*` bones — "
            f"animation clips made for Mixamo rigs will not retarget correctly"
        )
    elif len(mixamo_bones) < len(bone_names) * 0.5:
        warnings.append(
            f"armature '{armature.name}' has {len(mixamo_bones)}/{len(bone_names)} "
            f"`mixamorig:*` bones — may be partially non-Mixamo"
        )
    if not blendshapes:
        warnings.append(
            "no shape keys found on imported meshes — emotion/talk actions "
            "(`set_emotion`, `talk`, `smile`, `frown`) will be no-ops"
        )

    armature.location = spawn_location

    # Face the active scene camera by default. Mixamo characters in Blender
    # import with the Y-up → Z-up conversion baked into the armature's
    # rotation (usually as a quaternion), so directly setting rotation_euler
    # has no effect — we have to compose a world-Z yaw quaternion onto whatever
    # mode the importer used.
    camera = scene.camera or next(
        (obj for obj in scene.objects if obj.type == "CAMERA"), None
    )
    if camera is not None:
        import math

        import mathutils

        dx = camera.location.x - spawn_location[0]
        dy = camera.location.y - spawn_location[1]
        if dx * dx + dy * dy > 1e-12:
            # Mixamo characters' natural forward in world space is -Y. Solve
            # for the yaw θ around world Z that aligns -Y with (dx, dy):
            #   -Y rotated by θ = (sin θ, -cos θ) = (dx, dy)/length
            yaw = math.atan2(dx, -dy)
            yaw_quat = mathutils.Quaternion((0.0, 0.0, 1.0), yaw)
            # Preserve the importer's Y-up → Z-up rotation by composing on top.
            current_quat = armature.matrix_basis.to_quaternion()
            armature.rotation_mode = "QUATERNION"
            armature.rotation_quaternion = yaw_quat @ current_quat

    if handle is None:
        existing_handles = {
            obj.get(_HANDLE_PROP)
            for obj in bpy.data.objects
            if obj.type == "ARMATURE" and obj.get(_HANDLE_PROP)
        }
        base = path.stem.lower().replace(" ", "_")
        candidate = base
        suffix = 1
        while candidate in existing_handles:
            suffix += 1
            candidate = f"{base}_{suffix}"
        handle = candidate

    armature[_HANDLE_PROP] = handle

    return {
        "handle": handle,
        "armature_name": armature.name,
        "mesh_names": sorted(m.name for m in meshes),
        "bone_count": len(bone_names),
        "mixamo_bone_count": len(mixamo_bones),
        "blendshapes": sorted(blendshapes),
        "spawn_location": list(spawn_location),
        "warnings": warnings,
    }


__all__ = ["CharacterLoadError", "load_character"]
