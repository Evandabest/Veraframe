"""Tests for the implicit-idle gap fill in execute_timeline."""

from blender_daemon.action_executor import _fill_pose_gaps_with_idle


def _injected(timeline: dict) -> list[dict]:
    """Pull just the injected gap-fill idles out of a result timeline."""
    out: list[dict] = []
    for shot in timeline["shots"]:
        for a in shot["actions"]:
            if a["id"].startswith("_gap_idle_"):
                out.append(a)
    return out


def test_no_gaps_no_injection() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 0, "end": 8},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    assert _injected(out) == []


def test_leading_gap_filled() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 2, "end": 8},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    gaps = _injected(out)
    assert len(gaps) == 1
    assert gaps[0]["character"] == "alice"
    assert gaps[0]["start"] == 0
    assert gaps[0]["end"] == 2
    assert gaps[0]["type"] == "idle"


def test_middle_gap_filled() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 2},
                    {"id": "a2", "type": "idle", "character": "alice", "start": 5, "end": 8},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    gaps = _injected(out)
    assert len(gaps) == 1
    assert gaps[0]["start"] == 2
    assert gaps[0]["end"] == 5


def test_trailing_gap_filled() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    gaps = _injected(out)
    assert len(gaps) == 1
    assert gaps[0]["start"] == 4
    assert gaps[0]["end"] == 8


def test_multiple_characters_independent_gaps() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 0, "end": 4},
                    {"id": "a2", "type": "idle", "character": "bob", "start": 5, "end": 8},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    gaps = _injected(out)
    by_char = {g["character"]: g for g in gaps}
    assert set(by_char.keys()) == {"alice", "bob"}
    # alice has a trailing gap 4→8
    assert by_char["alice"]["start"] == 4
    assert by_char["alice"]["end"] == 8
    # bob has a leading gap 0→5
    assert by_char["bob"]["start"] == 0
    assert by_char["bob"]["end"] == 5


def test_face_actions_do_not_block_gap_fill() -> None:
    # A character with only a `smile` action (face-only) still gets a body
    # idle for the full shot — smile doesn't cover the body pose.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 0, "end": 8},
                    {"id": "a2", "type": "smile", "character": "alice", "start": 2, "end": 4},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    # No gap-fill needed — alice's body is covered by the idle. The smile
    # is ignored for gap-fill purposes.
    assert _injected(out) == []


def test_face_only_character_gets_full_idle() -> None:
    # A character with only face actions (no walk/idle/etc.) still needs
    # body coverage — otherwise the rest of the rig defaults to Mixamo's
    # T-pose. Gap-fill should drop an idle spanning the whole shot so the
    # character has a normal standing pose under the face action.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "smile", "character": "alice", "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    injected = _injected(out)
    assert len(injected) == 1
    assert injected[0]["character"] == "alice"
    assert injected[0]["start"] == 0.0
    assert injected[0]["end"] == 8.0


def test_original_actions_preserved() -> None:
    # Sanity: the original action list is intact, just with idles appended.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "a1", "type": "walk_to", "character": "alice", "target": "door",
                     "start": 0, "end": 4},
                ],
            }
        ]
    }
    out = _fill_pose_gaps_with_idle(tl)
    ids = {a["id"] for a in out["shots"][0]["actions"]}
    assert "a1" in ids
