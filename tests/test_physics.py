"""Tests for the Step 52 physics post-pass helpers."""

from __future__ import annotations

import math

from blender_daemon.physics import (
    DEFAULT_NATURAL_STRIDE_M,
    compute_walk_repeat,
    legacy_walk_repeat,
)


def test_natural_stride_is_one_point_five() -> None:
    # Document the chosen default; if this constant shifts, callers
    # that compare visually against existing renders need to know.
    assert DEFAULT_NATURAL_STRIDE_M == 1.5


def test_repeat_scales_with_distance() -> None:
    # 3 meters of travel at the default 1.5m stride → 2 cycles.
    assert math.isclose(compute_walk_repeat(distance_m=3.0, duration_s=4.0), 2.0)


def test_repeat_is_independent_of_duration() -> None:
    # Same distance, different durations → same number of cycles. The
    # *rate* changes (faster walk = each cycle is shorter wall-clock
    # time) but the foot-plant world positions are identical, which is
    # the whole point of the new formula.
    short = compute_walk_repeat(distance_m=6.0, duration_s=2.0)
    long = compute_walk_repeat(distance_m=6.0, duration_s=8.0)
    assert math.isclose(short, long)


def test_speed_multiplier_scales_legs_only() -> None:
    base = compute_walk_repeat(distance_m=6.0, duration_s=4.0)
    fast = compute_walk_repeat(distance_m=6.0, duration_s=4.0, speed_mult=1.6)
    assert math.isclose(fast, base * 1.6)


def test_zero_distance_does_not_collapse_to_zero() -> None:
    # A degenerate "walk to current position" still plays half a cycle
    # so the legs don't visibly freeze.
    assert compute_walk_repeat(distance_m=0.0, duration_s=2.0) == 0.5


def test_custom_natural_stride() -> None:
    # A clip with a 1.0m stride should produce 6 cycles for 6m of travel.
    assert math.isclose(
        compute_walk_repeat(distance_m=6.0, duration_s=4.0, natural_stride_m=1.0),
        6.0,
    )


def test_legacy_formula_matches_pre_step52_inline_math() -> None:
    # 4s walk, 32-frame action length, no speed multiplier:
    # repeat = 4 / 32 = 0.125, clamped to MIN_REPEAT (0.5).
    assert legacy_walk_repeat(duration_s=4.0, action_length_frames=32) == 0.5
    # 100-frame walk against the same 32-frame clip → ~3.125 cycles.
    assert math.isclose(
        legacy_walk_repeat(duration_s=100.0, action_length_frames=32), 100 / 32
    )


def test_legacy_speed_multiplier_applies() -> None:
    # Run mode = 1.6×; 100/32 cycles times 1.6.
    assert math.isclose(
        legacy_walk_repeat(duration_s=100.0, action_length_frames=32, speed_mult=1.6),
        (100 / 32) * 1.6,
    )
