"""Beat-coherence pass.

A shot without any *body* action on any character is suspicious — the
camera is on, but the characters are static (no walk, no idle, no
gesture). Sometimes that's intentional (e.g. a held wide shot of an
empty scene), often it's a mistake. This pass surfaces a warning issue
that the retry loop can feed back to the LLM; it never auto-fixes.

A shot without an explicit camera action is fine — the shot-level
`camera` field already pins the framing, and the per-shot camera
injector in the daemon emits a `camera_cut` at shot start.
"""

from __future__ import annotations

from planner.registry import Registry
from planner.schema import Project
from planner.validators import PassResult

_BODY_ACTION_TYPES = frozenset(
    {
        "walk_to",
        "idle",
        "turn_to",
        "sit",
        "stand",
        "play_clip",
        "nod",
        "shake_head",
        "wave",
        "point_at",
        "look_at",
        "talk",
        "smile",
        "frown",
        "blink",
    }
)


def run(project: Project, registry: Registry) -> PassResult:
    del registry
    issues: list[str] = []

    for shot in project.shots:
        has_body = any(a.type in _BODY_ACTION_TYPES for a in shot.actions)
        if not has_body:
            issues.append(
                f"shot '{shot.id}' ({shot.start}-{shot.end}) has no body actions on "
                f"any character — add at least one (idle / walk_to / talk / gesture) "
                f"so the characters aren't frozen."
            )

    return PassResult(project=project, issues=issues)
