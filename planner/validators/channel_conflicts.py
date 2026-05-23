"""Channel-conflict pass.

Two actions in the same channel on the same character may not overlap
in time. Channels group action types that physically compete for the
same body / scene resource — two `walk_to`s, two `talk`s, two camera
cuts, etc.

Boundary-touching (a.end == b.start) is not an overlap.
"""

from __future__ import annotations

from collections import defaultdict

from planner.registry import Registry
from planner.schema import Project
from planner.validators import PassResult

_PER_CHARACTER_CHANNELS: list[tuple[str, frozenset[str]]] = [
    ("body", frozenset({"walk_to", "idle", "turn_to", "sit", "stand", "play_clip"})),
    ("face_expression", frozenset({"smile", "frown"})),
    ("talk", frozenset({"talk"})),
    ("look_at", frozenset({"look_at"})),
    ("point_at", frozenset({"point_at"})),
]
_GLOBAL_CHANNELS: list[tuple[str, frozenset[str]]] = [
    ("camera", frozenset({"camera_cut", "camera_dolly"})),
    ("lighting", frozenset({"set_lighting"})),
]


def run(project: Project, registry: Registry) -> PassResult:
    del registry  # not needed for this pass
    issues: list[str] = []
    for shot in project.shots:
        buckets: dict[tuple[str, str | None], list] = defaultdict(list)
        for action in shot.actions:
            for channel_name, types in _PER_CHARACTER_CHANNELS:
                if action.type in types and hasattr(action, "character"):
                    buckets[(channel_name, action.character)].append(action)
            for channel_name, types in _GLOBAL_CHANNELS:
                if action.type in types:
                    buckets[(channel_name, None)].append(action)

        for (channel, owner), actions in buckets.items():
            actions.sort(key=lambda a: a.start)
            for i, a in enumerate(actions):
                for b in actions[i + 1 :]:
                    if a.end <= b.start:
                        break  # sorted; no later b can overlap with a either
                    where = f"character '{owner}'" if owner is not None else "scene"
                    issues.append(
                        f"actions '{a.id}' ({a.start}-{a.end}) and '{b.id}' "
                        f"({b.start}-{b.end}) both occupy the '{channel}' channel for "
                        f"{where} during shot '{shot.id}'"
                    )
    return PassResult(project=project, issues=issues)
