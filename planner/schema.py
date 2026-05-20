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
    CAMERA_CUT = "camera_cut"
    CAMERA_DOLLY = "camera_dolly"
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


class IdleAction(_TimedBase):
    type: Literal["idle"] = "idle"
    character: str = Field(min_length=1)
    emotion: Emotion | None = None


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


class CameraCutAction(_TimedBase):
    type: Literal["camera_cut"] = "camera_cut"
    camera: str = Field(min_length=1)


class CameraDollyAction(_TimedBase):
    type: Literal["camera_dolly"] = "camera_dolly"
    from_camera: str = Field(min_length=1)
    to_camera: str = Field(min_length=1)


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
    | CameraCutAction
    | CameraDollyAction
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
