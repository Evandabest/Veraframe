"""Shake-head action — short horizontal head-bone yaw oscillation (no-shake)."""

from actions._head_gesture import HeadGestureError, execute_head_oscillation


class ShakeHeadActionError(HeadGestureError):
    """Raised when the shake_head action can't be placed."""


def execute(armature, start_frame: int, end_frame: int, action_id: str = "shake_head") -> dict:
    return execute_head_oscillation(
        armature,
        axis="z",  # local-frame yaw for Mixamo head bone
        amplitude_deg=20.0,
        cycles=2,
        start_frame=start_frame,
        end_frame=end_frame,
        action_id=action_id,
        track_prefix="shakehead",
    )


__all__ = ["ShakeHeadActionError", "execute"]
