"""Nod action — short vertical head-bone pitch oscillation (yes-nod)."""

from actions._head_gesture import HeadGestureError, execute_head_oscillation


class NodActionError(HeadGestureError):
    """Raised when the nod action can't be placed."""


def execute(armature, start_frame: int, end_frame: int, action_id: str = "nod") -> dict:
    return execute_head_oscillation(
        armature,
        axis="x",  # local-frame pitch for Mixamo head bone
        amplitude_deg=14.0,
        cycles=2,
        start_frame=start_frame,
        end_frame=end_frame,
        action_id=action_id,
        track_prefix="nod",
    )


__all__ = ["NodActionError", "execute"]
