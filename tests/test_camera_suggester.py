"""Tests for the AI-camera-suggester preprocessing step.

The suggester injects a sensible cinematic action into each shot that lacks
one. Coverage:
- Shots with explicit author-provided cinematic actions are left alone.
- Two characters with talk → two_shot is injected.
- One walker (no talkers) → track_subject is injected on the walker.
- No talk / no walk → suggestion skipped (per-shot camera_cut suffices).
- Implicit per-shot camera_cut (id prefix `_shot_camera_`) does NOT count as
  author intent — suggester should still run despite its presence.
"""

from __future__ import annotations

from blender_daemon.action_executor import _suggest_cameras


def _suggested(timeline: dict) -> list[dict]:
    out: list[dict] = []
    for shot in timeline["shots"]:
        for a in shot["actions"]:
            if str(a.get("id", "")).startswith("_suggested_"):
                out.append(a)
    return out


def test_no_actions_no_suggestion() -> None:
    tl = {"shots": [{"id": "s1", "start": 0, "end": 8, "actions": []}]}
    out = _suggest_cameras(tl)
    assert _suggested(out) == []


def test_explicit_camera_cut_blocks_suggestion() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "cc", "type": "camera_cut", "camera": "wide", "start": 0, "end": 0.5},
                    {"id": "w", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    assert _suggested(out) == []


def test_implicit_shot_camera_does_not_block_suggestion() -> None:
    """Per-shot camera_cut injected by _inject_per_shot_cameras has the
    `_shot_camera_` id prefix and should be treated as just a default — the
    suggester runs as if there's no authored intent."""
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "_shot_camera_s1", "type": "camera_cut", "camera": "wide",
                     "start": 0, "end": 0.1},
                    {"id": "w", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    suggestions = _suggested(out)
    assert len(suggestions) == 1
    assert suggestions[0]["type"] == "track_subject"
    assert suggestions[0]["character"] == "alice"


def test_two_talkers_get_two_shot() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "t1", "type": "talk", "character": "alice", "text": "Hi",
                     "start": 0, "end": 2},
                    {"id": "t2", "type": "talk", "character": "bob", "text": "Hello",
                     "start": 3, "end": 5},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    suggestions = _suggested(out)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["type"] == "two_shot"
    assert s["a"] == "alice" and s["b"] == "bob"
    assert s["start"] == 0 and s["end"] == 8


def test_one_walker_no_talkers_gets_track_subject() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "w", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    suggestions = _suggested(out)
    assert len(suggestions) == 1
    assert suggestions[0]["type"] == "track_subject"
    assert suggestions[0]["character"] == "alice"


def test_idle_only_no_suggestion() -> None:
    # No walk, no talk → no cinematic suggestion needed; the static per-shot
    # camera_cut is enough.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "i", "type": "idle", "character": "alice", "start": 0, "end": 8},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    assert _suggested(out) == []


def test_original_actions_preserved() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "w", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _suggest_cameras(tl)
    ids = {a["id"] for a in out["shots"][0]["actions"]}
    assert "w" in ids
