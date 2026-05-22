"""Tests for the per-shot camera injection used to support multi-shot timelines."""

from blender_daemon.action_executor import _inject_per_shot_cameras


def _camera_cuts(timeline: dict) -> list[dict]:
    out: list[dict] = []
    for shot in timeline["shots"]:
        for a in shot["actions"]:
            if a.get("type") == "camera_cut":
                out.append(a)
    return out


def test_single_shot_no_explicit_cut_injected() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "camera": "wide",
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 0, "end": 8},
                ],
            }
        ]
    }
    out = _inject_per_shot_cameras(tl)
    cuts = _camera_cuts(out)
    assert len(cuts) == 1
    assert cuts[0]["camera"] == "wide"
    assert cuts[0]["start"] == 0


def test_multi_shot_each_shot_gets_its_camera() -> None:
    tl = {
        "shots": [
            {"id": "s1", "start": 0, "end": 5, "camera": "wide", "actions": []},
            {"id": "s2", "start": 5, "end": 12, "camera": "close", "actions": []},
            {"id": "s3", "start": 12, "end": 18, "camera": "wide", "actions": []},
        ]
    }
    out = _inject_per_shot_cameras(tl)
    cuts = _camera_cuts(out)
    assert len(cuts) == 3
    # Order matches the shots order.
    assert (cuts[0]["start"], cuts[0]["camera"]) == (0, "wide")
    assert (cuts[1]["start"], cuts[1]["camera"]) == (5, "close")
    assert (cuts[2]["start"], cuts[2]["camera"]) == (12, "wide")


def test_explicit_camera_cut_at_shot_start_wins() -> None:
    # If the user authored a camera_cut at the shot's start, we don't add a
    # second one — manual control takes priority.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "camera": "wide",
                "actions": [
                    {"id": "cut", "type": "camera_cut", "camera": "close",
                     "start": 0, "end": 0.5},
                ],
            }
        ]
    }
    out = _inject_per_shot_cameras(tl)
    cuts = _camera_cuts(out)
    assert len(cuts) == 1
    assert cuts[0]["camera"] == "close"  # the explicit one, not "wide"


def test_explicit_cut_mid_shot_does_not_block_injection() -> None:
    # An explicit camera_cut later in the shot still leaves the shot.start
    # binding implicit, so we inject for the shot-start position.
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "camera": "wide",
                "actions": [
                    {"id": "cut", "type": "camera_cut", "camera": "close",
                     "start": 4, "end": 4.5},
                ],
            }
        ]
    }
    out = _inject_per_shot_cameras(tl)
    cuts = _camera_cuts(out)
    assert len(cuts) == 2
    starts = sorted(c["start"] for c in cuts)
    assert starts == [0, 4]


def test_shot_without_camera_field_skipped() -> None:
    # If the manifest's Shot somehow has no `camera` key (older fixture, etc.),
    # we do nothing — the load-time scene camera applies.
    tl = {
        "shots": [
            {"id": "s1", "start": 0, "end": 8, "actions": []},
        ]
    }
    out = _inject_per_shot_cameras(tl)
    assert _camera_cuts(out) == []


def test_original_actions_preserved() -> None:
    tl = {
        "shots": [
            {
                "id": "s1",
                "start": 0,
                "end": 8,
                "camera": "wide",
                "actions": [
                    {"id": "a1", "type": "idle", "character": "alice", "start": 0, "end": 8},
                ],
            }
        ]
    }
    out = _inject_per_shot_cameras(tl)
    ids = {a["id"] for a in out["shots"][0]["actions"]}
    assert "a1" in ids
