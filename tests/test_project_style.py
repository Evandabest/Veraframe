"""Tests for the project-style-lock preprocessing (default lighting injection)."""

from __future__ import annotations

from blender_daemon.action_executor import _inject_default_lighting


def _injected(timeline: dict) -> list[dict]:
    out: list[dict] = []
    for shot in timeline["shots"]:
        for a in shot["actions"]:
            if str(a.get("id", "")).startswith("_project_lighting_"):
                out.append(a)
    return out


def test_lighting_injected_into_each_shot() -> None:
    tl = {
        "shots": [
            {"id": "s1", "start": 0, "end": 5, "actions": []},
            {"id": "s2", "start": 5, "end": 10, "actions": []},
        ]
    }
    out = _inject_default_lighting(tl, "dim")
    injected = _injected(out)
    assert len(injected) == 2
    assert all(a["type"] == "set_lighting" for a in injected)
    assert all(a["preset"] == "dim" for a in injected)
    # Times match the shot starts.
    starts = sorted(a["start"] for a in injected)
    assert starts == [0.0, 5.0]


def test_explicit_set_lighting_at_shot_start_blocks_injection() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 5,
                "actions": [
                    {"id": "auth", "type": "set_lighting", "preset": "emergency",
                     "start": 0, "end": 0.5},
                ],
            }
        ]
    }
    out = _inject_default_lighting(tl, "default")
    assert _injected(out) == []
    # Author's choice is preserved untouched.
    assert out["shots"][0]["actions"][0]["preset"] == "emergency"


def test_mid_shot_set_lighting_does_not_block_injection() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "actions": [
                    {"id": "auth", "type": "set_lighting", "preset": "dim",
                     "start": 3, "end": 3.5},
                ],
            }
        ]
    }
    out = _inject_default_lighting(tl, "default")
    injected = _injected(out)
    assert len(injected) == 1
    assert injected[0]["start"] == 0
    assert injected[0]["preset"] == "default"


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
    out = _inject_default_lighting(tl, "dim")
    ids = {a["id"] for a in out["shots"][0]["actions"]}
    assert "w" in ids
    assert any(i.startswith("_project_lighting_") for i in ids)


def test_no_shots_no_injection() -> None:
    tl = {"shots": []}
    out = _inject_default_lighting(tl, "dim")
    assert out["shots"] == []
