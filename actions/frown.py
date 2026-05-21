"""Frown action — drives the `Sorrow` VRM blendshape."""

from actions._blendshapes import hold_shape_key

_SHAPE_KEY = "Sorrow"


class FrownActionError(RuntimeError):
    pass


def execute(armature, start_frame: int, end_frame: int, action_id: str = "frown") -> dict:
    affected = hold_shape_key(armature, _SHAPE_KEY, start_frame, end_frame)
    return {
        "armature": armature.name,
        "shape_key": _SHAPE_KEY,
        "frame_start": int(start_frame),
        "frame_end": int(end_frame),
        "affected_meshes": affected,
        "noop": not affected,
    }


__all__ = ["FrownActionError", "execute"]
