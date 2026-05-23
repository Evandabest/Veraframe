"""Pydantic models for the Veraframe scene timeline.

A `Project` is the structured artifact emitted by the LLM and consumed by the
Blender executor. Each action is a discriminated-union member; Pydantic
enforces the per-action required fields at parse time.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    JOY = "joy"
    ANGRY = "angry"
    SORROW = "sorrow"
    FUN = "fun"


class WalkStyle(StrEnum):
    """Gait flavor applied to walk_to. The executor maps these to NLA-strip
    speed multipliers on top of the standard walk_in_place clip — no
    per-style FBX required. Sneak is the slowest, run the fastest."""

    WALK = "walk"
    RUN = "run"
    JOG = "jog"
    SNEAK = "sneak"
    MARCH = "march"
    LIMP = "limp"


class IdleStyle(StrEnum):
    """Emotional/postural flavor applied to idle. Currently informational —
    the LLM picks a style and downstream tools can branch on it, but the
    executor doesn't yet have per-style idle clips."""

    NEUTRAL = "neutral"
    TIRED = "tired"
    ALERT = "alert"
    CONFIDENT = "confident"
    BORED = "bored"
    NERVOUS = "nervous"


class BodyPart(StrEnum):
    """Coarse body regions used by the optional `bone_mask` field on gestures.

    A gesture's bone_mask declares which limbs the action drives. Listeners
    use this to reason about layering: a `wave` (right_arm only) can run
    concurrently with a `walk_to` (full-body locomotion) without clobbering
    the legs, while two right_arm actions at the same time conflict.

    Values are intentionally coarse (one per limb / region) so the LLM can
    pick them by name without needing to know the underlying Mixamo bone
    naming. The executor maps each part to its bones internally.
    """

    HEAD = "head"
    SPINE = "spine"
    LEFT_ARM = "left_arm"
    RIGHT_ARM = "right_arm"
    LEFT_LEG = "left_leg"
    RIGHT_LEG = "right_leg"
    FACE = "face"


class ActionType(StrEnum):
    WALK_TO = "walk_to"
    IDLE = "idle"
    TURN_TO = "turn_to"
    LOOK_AT = "look_at"
    POINT_AT = "point_at"
    SIT = "sit"
    STAND = "stand"
    SMILE = "smile"
    FROWN = "frown"
    BLINK = "blink"
    TALK = "talk"
    NOD = "nod"
    SHAKE_HEAD = "shake_head"
    WAVE = "wave"
    CAMERA_CUT = "camera_cut"
    CAMERA_DOLLY = "camera_dolly"
    TRACK_SUBJECT = "track_subject"
    TWO_SHOT = "two_shot"
    OVER_SHOULDER = "over_shoulder"
    ORBIT = "orbit"
    SET_LIGHTING = "set_lighting"


class _TimedBase(BaseModel):
    """Shared timing fields and end>start invariant for actions and shots."""

    id: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_window(self) -> "_TimedBase":
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be > start ({self.start})")
        return self


class WalkToAction(_TimedBase):
    type: Literal["walk_to"] = "walk_to"
    character: str = Field(min_length=1)
    target: str = Field(min_length=1)
    emotion: Emotion | None = None
    style: WalkStyle | None = None


class IdleAction(_TimedBase):
    type: Literal["idle"] = "idle"
    character: str = Field(min_length=1)
    emotion: Emotion | None = None
    style: IdleStyle | None = None


class TurnToAction(_TimedBase):
    type: Literal["turn_to"] = "turn_to"
    character: str = Field(min_length=1)
    target: str = Field(min_length=1)


class LookAtAction(_TimedBase):
    type: Literal["look_at"] = "look_at"
    character: str = Field(min_length=1)
    target: str = Field(min_length=1)


class PointAtAction(_TimedBase):
    type: Literal["point_at"] = "point_at"
    character: str = Field(min_length=1)
    target: str = Field(min_length=1)
    bone_mask: list[BodyPart] | None = Field(
        default=None,
        description=(
            "Body parts this point gesture drives. Defaults to [right_arm]. Set"
            " to override (e.g. left_arm) when the character should point with"
            " a different limb."
        ),
    )


class SitAction(_TimedBase):
    type: Literal["sit"] = "sit"
    character: str = Field(min_length=1)


class StandAction(_TimedBase):
    type: Literal["stand"] = "stand"
    character: str = Field(min_length=1)


class SmileAction(_TimedBase):
    type: Literal["smile"] = "smile"
    character: str = Field(min_length=1)


class FrownAction(_TimedBase):
    type: Literal["frown"] = "frown"
    character: str = Field(min_length=1)


class BlinkAction(_TimedBase):
    type: Literal["blink"] = "blink"
    character: str = Field(min_length=1)


class TalkAction(_TimedBase):
    type: Literal["talk"] = "talk"
    character: str = Field(min_length=1)
    text: str = Field(min_length=1)
    emotion: Emotion | None = None
    look_at: str | None = None
    gesture: str | None = None


class NodAction(_TimedBase):
    """Vertical head-bone pitch oscillation (yes-nod).

    Touches the head bone only — safe to layer over walk_to / idle.
    """

    type: Literal["nod"] = "nod"
    character: str = Field(min_length=1)
    bone_mask: list[BodyPart] | None = Field(
        default=None,
        description="Body parts this nod drives. Defaults to [head].",
    )


class ShakeHeadAction(_TimedBase):
    """Horizontal head-bone yaw oscillation (no-shake).

    Touches the head bone only — safe to layer over walk_to / idle.
    """

    type: Literal["shake_head"] = "shake_head"
    character: str = Field(min_length=1)
    bone_mask: list[BodyPart] | None = Field(
        default=None,
        description="Body parts this head shake drives. Defaults to [head].",
    )


class WaveAction(_TimedBase):
    """Right-arm wave — raises and oscillates the forearm.

    Touches the right-arm bones only — safe to layer over walk_to / idle
    (whose right-arm motion comes from the FBX cycle, which the wave
    keyframes override at the pose level).
    """

    type: Literal["wave"] = "wave"
    character: str = Field(min_length=1)
    target: str | None = None  # optional spawn point / character to wave at
    bone_mask: list[BodyPart] | None = Field(
        default=None,
        description=(
            "Body parts this wave drives. Defaults to [right_arm]. Override"
            " to [left_arm] for a left-handed wave."
        ),
    )


class CameraCutAction(_TimedBase):
    type: Literal["camera_cut"] = "camera_cut"
    camera: str = Field(min_length=1)


class CameraDollyAction(_TimedBase):
    type: Literal["camera_dolly"] = "camera_dolly"
    from_camera: str = Field(min_length=1)
    to_camera: str = Field(min_length=1)


class TrackSubjectAction(_TimedBase):
    """Active camera follows a character handle for the action's duration.

    The camera's position is animated from a behind-and-above offset relative
    to the character at start_frame to the same offset at end_frame. If the
    character walks during the window, the camera tracks them.
    """

    type: Literal["track_subject"] = "track_subject"
    character: str = Field(min_length=1)


class TwoShotAction(_TimedBase):
    """Active camera repositions to frame both `a` and `b` for the duration.

    Camera is placed perpendicular to the line A↔B, looking at the midpoint,
    at a distance proportional to their separation so both fit in frame.
    """

    type: Literal["two_shot"] = "two_shot"
    a: str = Field(min_length=1)
    b: str = Field(min_length=1)


class OverShoulderAction(_TimedBase):
    """Over-the-shoulder camera: positioned behind `a`, looking at `b`.

    Classic dialogue framing — the viewer sees the side of A's shoulder/head
    on one edge of the frame with B in conversation across the cut. The
    camera sits at a fixed offset behind A (along the -direction from A to B)
    and looks at B's upper body.
    """

    type: Literal["over_shoulder"] = "over_shoulder"
    a: str = Field(min_length=1)
    b: str = Field(min_length=1)


class OrbitAction(_TimedBase):
    """Active camera circles a target by `degrees` over the action duration.

    Positive degrees rotate counterclockwise (when viewed from above).
    Target is either a character handle or a scene spawn-point name.
    """

    type: Literal["orbit"] = "orbit"
    target: str = Field(min_length=1)
    degrees: float = Field(default=90.0)


class SetLightingAction(_TimedBase):
    type: Literal["set_lighting"] = "set_lighting"
    preset: str = Field(min_length=1)


Action = Annotated[
    WalkToAction
    | IdleAction
    | TurnToAction
    | LookAtAction
    | PointAtAction
    | SitAction
    | StandAction
    | SmileAction
    | FrownAction
    | BlinkAction
    | TalkAction
    | NodAction
    | ShakeHeadAction
    | WaveAction
    | CameraCutAction
    | CameraDollyAction
    | TrackSubjectAction
    | TwoShotAction
    | OverShoulderAction
    | OrbitAction
    | SetLightingAction,
    Field(discriminator="type"),
]


class Character(BaseModel):
    id: str = Field(min_length=1)
    preset: str = Field(min_length=1)
    spawn: str = Field(min_length=1)


class Shot(BaseModel):
    id: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    camera: str = Field(min_length=1)
    actions: list[Action]

    @model_validator(mode="after")
    def _check_window(self) -> "Shot":
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be > start ({self.start})")
        return self


class Project(BaseModel):
    project: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    characters: list[Character]
    shots: list[Shot]


# Per-action-type defaults for the body parts the action drives. Used by
# `effective_bone_mask` so callers don't need to know the implementation
# detail of which bones each gesture touches — they only see body parts.
_DEFAULT_BONE_MASKS: dict[str, list[BodyPart]] = {
    "nod": [BodyPart.HEAD],
    "shake_head": [BodyPart.HEAD],
    "wave": [BodyPart.RIGHT_ARM],
    "point_at": [BodyPart.RIGHT_ARM],
    "look_at": [BodyPart.HEAD],
    "smile": [BodyPart.FACE],
    "frown": [BodyPart.FACE],
    "blink": [BodyPart.FACE],
    "talk": [BodyPart.FACE],
    "turn_to": [BodyPart.SPINE],
    # Whole-body locomotion / poses — everything else is "all parts".
    "walk_to": [
        BodyPart.HEAD,
        BodyPart.SPINE,
        BodyPart.LEFT_ARM,
        BodyPart.RIGHT_ARM,
        BodyPart.LEFT_LEG,
        BodyPart.RIGHT_LEG,
    ],
    "idle": [
        BodyPart.HEAD,
        BodyPart.SPINE,
        BodyPart.LEFT_ARM,
        BodyPart.RIGHT_ARM,
        BodyPart.LEFT_LEG,
        BodyPart.RIGHT_LEG,
    ],
    "sit": [
        BodyPart.HEAD,
        BodyPart.SPINE,
        BodyPart.LEFT_ARM,
        BodyPart.RIGHT_ARM,
        BodyPart.LEFT_LEG,
        BodyPart.RIGHT_LEG,
    ],
    "stand": [
        BodyPart.HEAD,
        BodyPart.SPINE,
        BodyPart.LEFT_ARM,
        BodyPart.RIGHT_ARM,
        BodyPart.LEFT_LEG,
        BodyPart.RIGHT_LEG,
    ],
}


def effective_bone_mask(action: Action) -> list[BodyPart]:
    """Return the body parts an action drives, honoring an explicit
    `bone_mask` override and falling back to the per-type default."""
    explicit = getattr(action, "bone_mask", None)
    if explicit:
        return list(explicit)
    return list(_DEFAULT_BONE_MASKS.get(action.type, []))


def actions_conflict(a: Action, b: Action) -> bool:
    """True if two actions on the same character overlap in time AND drive
    at least one common body part. Camera / lighting actions never conflict.

    Used by the validator and by Step 46's layering hints to surface
    "wave + walk_to overlap and both drive the right arm" early."""
    if a.character != getattr(b, "character", None):
        return False
    # Time overlap.
    if a.end <= b.start or b.end <= a.start:
        return False
    parts_a = set(effective_bone_mask(a))
    parts_b = set(effective_bone_mask(b))
    return bool(parts_a & parts_b)
