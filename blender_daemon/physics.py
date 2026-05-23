"""Physics post-pass helpers (Step 52).

Pure-math utilities that the executor applies after placing NLA strips
to clean up the most visible physical-plausibility problems:

- **Foot slide.** When the walk-cycle plays at a fixed rate but the
  character's travel distance varies, the feet appear to glide across
  the floor (cycles too few = giant strides; too many = micro-steps).
  `compute_walk_repeat` ties the strip's repeat count to actual travel
  distance instead of just duration, so the planted-foot phase happens
  while the character is moving that foot's stride length.

- **Balance / momentum.** Not implemented yet — placeholders for follow-up
  work. Foot-locking via IK constraints and travel-velocity smoothing
  are the obvious next steps once the daemon-side post-pass infra here
  is settled.

Everything in this module is pure Python (no `bpy`) so it can be unit-
tested without spinning up Blender.
"""

from __future__ import annotations

# Per-clip natural stride length in meters — the distance the character
# advances per full walk cycle in the underlying FBX. Mixamo's bundled
# "Walking" clip travels about 1.5m per cycle when imported at scale
# 1.0; that's the default until a user-uploaded clip provides its own.
DEFAULT_NATURAL_STRIDE_M = 1.5

# Floor under which the walk-repeat clamp refuses to collapse: even a
# tiny step has to play at least this fraction of one cycle so the legs
# don't visibly freeze. 0.5 = half a cycle = one footfall.
_MIN_REPEAT = 0.5


def compute_walk_repeat(
    distance_m: float,
    duration_s: float,
    natural_stride_m: float = DEFAULT_NATURAL_STRIDE_M,
    speed_mult: float = 1.0,
) -> float:
    """Return the NLA strip repeat count that keeps feet planted.

    The walk cycle's footfalls happen at fixed phases of the cycle.
    Setting repeat = distance / natural_stride means the cycle plays as
    many times as there are natural strides in the travel distance — so
    the planted-foot phase falls on the same world position regardless
    of how long the walk takes.

    `duration_s` is currently unused in the formula but kept in the
    signature so callers can pass it without restructuring (and so the
    future balance/momentum passes have it at hand). `speed_mult` mirrors
    the existing `_STYLE_SPEED_MULTIPLIER` knob in walk_to: 'run' speeds
    the legs up relative to ground travel, 'sneak' slows them.
    """
    if distance_m <= 0 or natural_stride_m <= 0:
        return _MIN_REPEAT
    repeat = (distance_m / natural_stride_m) * speed_mult
    # Single-character argument check — the runtime never sees these.
    _ = duration_s
    return max(_MIN_REPEAT, repeat)


def legacy_walk_repeat(
    duration_s: float,
    action_length_frames: float,
    speed_mult: float = 1.0,
) -> float:
    """Pre-Step-52 formula. Kept here so the executor can fall back to
    the old behavior when the physics post-pass is disabled.

    Same as the current walk_to.py inline formula:
    repeat = (desired_duration_frames / action_length_frames) * speed_mult
    """
    if action_length_frames <= 0:
        return _MIN_REPEAT
    return max(_MIN_REPEAT, (duration_s / action_length_frames) * speed_mult)
