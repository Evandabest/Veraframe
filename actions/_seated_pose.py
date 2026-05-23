"""Shared seated-pose bone keyframes used by `sit` and `stand`.

Defines the target pose as a small set of pose-bone quaternion rotations on
the Mixamo leg bones. The pose is **legs only** so upper-body actions (idle,
look_at, smile) keep evaluating on top of the seated strip — `REPLACE` blend
on the NLA strip only masks channels the strip actually keyframes.

Quaternions are computed inline for clarity (`q = (cos(θ/2), axis * sin(θ/2))`).
The numerical values are tuned to read as "knees-forward, shins-down" from
the wide camera; refine if the seated character looks anatomically wrong.
"""

import math


def _quat_x(angle_deg: float) -> tuple[float, float, float, float]:
    """Quaternion rotation around the bone's local X axis."""
    half = math.radians(angle_deg) / 2.0
    return (math.cos(half), math.sin(half), 0.0, 0.0)


# Rest pose (identity quaternion).
REST = (1.0, 0.0, 0.0, 0.0)

# Seated pose:
#   UpLeg +90° X: thigh swings forward to horizontal (knees out).
#   Leg   -90° X: knee bends, shin drops to vertical.
SEATED: dict[str, tuple[float, float, float, float]] = {
    "mixamorig:LeftUpLeg": _quat_x(90.0),
    "mixamorig:RightUpLeg": _quat_x(90.0),
    "mixamorig:LeftLeg": _quat_x(-90.0),
    "mixamorig:RightLeg": _quat_x(-90.0),
}


SEATED_BONES = tuple(SEATED.keys())

# Vertical drop (in armature world units, ~meters for our Mixamo rigs)
# applied during a sit so the character's body lowers from standing
# hip height to seated hip height. The leg-bone pose alone doesn't move
# the hips — without this, the character looks like they're hovering on
# an invisible chair at standing-hip altitude. Tuned to read well on
# the bundled X-Bot scale; refine if a different rig sits too high/low.
SEATED_HIP_DROP_M = 0.45
