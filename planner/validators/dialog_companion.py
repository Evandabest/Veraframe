"""Dialog companion pass.

A `talk` action that lasts more than `_MIN_TALK_FOR_LOOK_AT` seconds
without an explicit `look_at` is jarring — the character speaks at the
camera or into space. This pass auto-attaches a `look_at` value when:

- the talk is long enough to warrant one, AND
- there's exactly one other character in the same shot to look at, AND
- the LLM didn't already specify one.

If we can't pick an unambiguous target (multiple other characters in
the shot, or none), we don't touch the action — the LLM made its call,
or there's nobody to look at.

This is a fix-only pass; it never adds issues.
"""

from __future__ import annotations

from planner.registry import Registry
from planner.schema import Project
from planner.validators import PassResult

_MIN_TALK_FOR_LOOK_AT = 1.0


def run(project: Project, registry: Registry) -> PassResult:
    del registry  # not needed
    fixes: list[str] = []

    for shot in project.shots:
        # Characters that appear in *any* action of this shot. Used to
        # pick a single unambiguous target for the look_at default.
        shot_character_ids = {
            getattr(a, "character", None)
            for a in shot.actions
            if hasattr(a, "character") and getattr(a, "character", None) is not None
        }

        for action in shot.actions:
            if action.type != "talk":
                continue
            if (action.end - action.start) <= _MIN_TALK_FOR_LOOK_AT:
                continue
            if action.look_at:
                continue
            # Candidate listeners: characters in this shot other than the speaker.
            others = shot_character_ids - {action.character}
            if len(others) != 1:
                continue
            target = next(iter(others))
            action.look_at = target
            fixes.append(
                f"talk '{action.id}' had no look_at; defaulting to '{target}' "
                f"(only other character in shot '{shot.id}')"
            )

    return PassResult(project=project, fixes=fixes)
