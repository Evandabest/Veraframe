"""Shared helper for VRM-style blendshape (shape key) keyframing.

Used by the emotion-style actions (`smile`, `frown`, `blink`, future `talk`
visemes) to drive named shape keys on all meshes parented to a character's
armature.

If the character has no matching shape keys (e.g. the bundled X-Bot has
none), the call is a no-op and the returned `affected_meshes` list is empty.
Callers can surface that fact in their result dict so the executor's
response makes the no-op visible.
"""

try:
    import bpy
except ImportError:
    bpy = None


class BlendshapeError(RuntimeError):
    """Raised when blendshape keyframing can't be performed."""


def keyframe_shape_key(armature, shape_key_name: str, value: float, frame: int) -> list[str]:
    """Set `shape_key_name` to `value` on every parented mesh and keyframe it.

    Returns the names of meshes that actually had the shape key. Meshes
    without that key (or without shape keys at all) are skipped silently.
    """
    if bpy is None:
        raise BlendshapeError("bpy unavailable")

    affected: list[str] = []
    for obj in bpy.data.objects:
        if obj.parent is not armature or obj.type != "MESH":
            continue
        keys = obj.data.shape_keys
        if keys is None:
            continue
        kb = keys.key_blocks.get(shape_key_name)
        if kb is None:
            continue
        kb.value = value
        keys.keyframe_insert(data_path=f'key_blocks["{shape_key_name}"].value', frame=int(frame))
        affected.append(obj.name)
    return affected


def hold_shape_key(
    armature,
    shape_key_name: str,
    start_frame: int,
    end_frame: int,
    *,
    peak_value: float = 1.0,
) -> list[str]:
    """Ramp `shape_key_name` from 0 → peak at `start_frame`, hold to
    `end_frame`, then drop back to 0. Returns affected mesh names from the
    last keyframe call (empty if the character has no matching shape key).
    """
    s, e = int(start_frame), int(end_frame)
    affected: list[str] = []
    for frame, value in (
        (max(0, s - 1), 0.0),
        (s, peak_value),
        (e, peak_value),
        (e + 1, 0.0),
    ):
        affected = keyframe_shape_key(armature, shape_key_name, value, frame)
    return affected


__all__ = ["BlendshapeError", "hold_shape_key", "keyframe_shape_key"]
