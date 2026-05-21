"""Blink action — drives the `Blink` VRM blendshape for a brief pulse."""

from actions._blendshapes import keyframe_shape_key

_SHAPE_KEY = "Blink"
_BLINK_DURATION_FRAMES = 4  # roughly 1/6 second at 24fps — eyes shut and reopen


class BlinkActionError(RuntimeError):
    pass


def execute(armature, start_frame: int, end_frame: int, action_id: str = "blink") -> dict:
    """A blink pulses to peak halfway through the action's window, then back.

    Unlike `smile`/`frown` which hold the expression for the full window, a
    blink is instantaneous — eyes close for a few frames and reopen.
    """
    s, e = int(start_frame), int(end_frame)
    mid = (s + e) // 2
    half = _BLINK_DURATION_FRAMES // 2

    affected: list[str] = []
    for frame, value in (
        (max(0, mid - half - 1), 0.0),
        (mid, 1.0),
        (mid + half + 1, 0.0),
    ):
        affected = keyframe_shape_key(armature, _SHAPE_KEY, value, frame)

    return {
        "armature": armature.name,
        "shape_key": _SHAPE_KEY,
        "blink_frame": mid,
        "frame_start": s,
        "frame_end": e,
        "affected_meshes": affected,
        "noop": not affected,
    }


__all__ = ["BlinkActionError", "execute"]
