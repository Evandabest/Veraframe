"""Talk action — drive VRM mouth visemes across an action window.

Splits `text` into syllables (cluster-of-vowels heuristic — adequate for
English without dragging in a hyphenation library), maps each syllable to one
of the VRM standard mouth shape keys (`A`, `I`, `U`, `E`, `O`), and pulses
that shape key around each syllable's time slot.

Optional `emotion` is layered as a held shape key over the entire window via
the same helper used by `smile`/`frown`. Optional `look_at` is not handled
here — compose `look_at` separately in the timeline.

X-Bot has no shape keys, so `talk` is visually a no-op on the bundled
character (same as the other VRM-driven actions). The result dict reports
`affected_meshes` so the executor can surface this to the caller.
"""

import re
from dataclasses import dataclass

try:
    import bpy
except ImportError:
    bpy = None

from actions._blendshapes import hold_shape_key, keyframe_shape_key


class TalkActionError(RuntimeError):
    """Raised when the talk action can't be placed."""


# Map of dominant vowel → VRM viseme shape key.
_VOWEL_TO_VISEME: dict[str, str] = {
    "a": "A",
    "e": "E",
    "i": "I",
    "o": "O",
    "u": "U",
    "y": "I",
}

# VRM emotion shape keys used as the held overlay.
_EMOTION_TO_SHAPE: dict[str, str] = {
    "joy": "Joy",
    "sorrow": "Sorrow",
    "angry": "Angry",
    "fun": "Fun",
    "neutral": "Neutral",
}


@dataclass(frozen=True)
class Syllable:
    text: str
    viseme: str


def syllabify(text: str) -> list[Syllable]:
    """Split `text` into syllables on consecutive vowel clusters.

    `"hello world"` → `["he", "llo", "wo", "rld"]` (roughly). Each syllable is
    tagged with the viseme of its first vowel.
    """
    syllables: list[Syllable] = []
    current = ""
    in_vowel_group = False
    last_vowel: str | None = None

    for ch in text.lower():
        if not ch.isalpha():
            continue
        is_vowel = ch in _VOWEL_TO_VISEME
        if is_vowel:
            if in_vowel_group:
                current += ch
            else:
                # New vowel group starts — flush previous syllable if any.
                if current and last_vowel is not None:
                    syllables.append(
                        Syllable(text=current, viseme=_VOWEL_TO_VISEME[last_vowel])
                    )
                current = ch
                in_vowel_group = True
            last_vowel = ch
        else:
            current += ch
            in_vowel_group = False

    if current and last_vowel is not None:
        syllables.append(Syllable(text=current, viseme=_VOWEL_TO_VISEME[last_vowel]))

    return syllables


def execute(
    armature,
    text: str,
    start_frame: int,
    end_frame: int,
    action_id: str = "talk",
    emotion: str | None = None,
) -> dict:
    if bpy is None:
        raise TalkActionError("bpy unavailable")
    if not text.strip():
        raise TalkActionError("text is empty")

    s, e = int(start_frame), int(end_frame)
    if e <= s:
        raise TalkActionError("end_frame must be > start_frame")

    syllables = syllabify(text)
    if not syllables:
        raise TalkActionError(f"could not extract syllables from text: {text!r}")

    span = e - s
    per_syllable = max(1, span // len(syllables))

    visemes_used: set[str] = set()
    affected_meshes: set[str] = set()

    for idx, syl in enumerate(syllables):
        viseme_start = s + idx * per_syllable
        viseme_peak = viseme_start + max(1, per_syllable // 2)
        viseme_end = min(e, s + (idx + 1) * per_syllable)

        for frame, value in (
            (viseme_start, 0.0),
            (viseme_peak, 1.0),
            (viseme_end, 0.0),
        ):
            affected = keyframe_shape_key(armature, syl.viseme, value, frame)
            affected_meshes.update(affected)
        visemes_used.add(syl.viseme)

    emotion_shape = _EMOTION_TO_SHAPE.get(emotion.lower()) if emotion else None
    if emotion_shape:
        emotion_affected = hold_shape_key(armature, emotion_shape, s, e, peak_value=0.6)
        affected_meshes.update(emotion_affected)

    return {
        "armature": armature.name,
        "frame_start": s,
        "frame_end": e,
        "syllable_count": len(syllables),
        "visemes_used": sorted(visemes_used),
        "emotion_overlay": emotion_shape,
        "affected_meshes": sorted(affected_meshes),
        "noop": len(affected_meshes) == 0,
    }


__all__ = ["TalkActionError", "Syllable", "execute", "syllabify"]
