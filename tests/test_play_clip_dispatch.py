"""Unit tests for the play_clip dispatcher (no real Blender)."""

from __future__ import annotations

import pytest

from blender_daemon import action_executor


@pytest.fixture
def fake_bpy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scene = type("S", (), {"objects": {}, "name": "fake"})()
    fake_bpy = type(
        "B",
        (),
        {
            "context": type("C", (), {"scene": fake_scene})(),
            "data": type("D", (), {"objects": []})(),
        },
    )
    monkeypatch.setattr(action_executor, "bpy", fake_bpy)


def test_play_clip_skipped_when_character_not_loaded(
    monkeypatch: pytest.MonkeyPatch, fake_bpy: None
) -> None:
    monkeypatch.setattr(action_executor, "_index_characters_by_handle", lambda: {})
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "play_clip",
                        "character": "alice",
                        "clip": "kick",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(
        timeline=timeline, asset_paths={"motion:kick": "/tmp/kick.fbx"}
    )
    assert result["executed"] == []
    skip = next(s for s in result["skipped"] if s["type"] == "play_clip")
    assert "not loaded" in skip["reason"]


def test_play_clip_skipped_when_clip_path_missing(
    monkeypatch: pytest.MonkeyPatch, fake_bpy: None
) -> None:
    monkeypatch.setattr(
        action_executor, "_index_characters_by_handle", lambda: {"alice": object()}
    )
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "play_clip",
                        "character": "alice",
                        "clip": "kick",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    # No motion:kick entry in asset_paths.
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    skip = next(s for s in result["skipped"] if s["type"] == "play_clip")
    assert "motion clip 'kick' not found" in skip["reason"]


def test_play_clip_skipped_when_clip_id_empty(
    monkeypatch: pytest.MonkeyPatch, fake_bpy: None
) -> None:
    monkeypatch.setattr(
        action_executor, "_index_characters_by_handle", lambda: {"alice": object()}
    )
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "play_clip",
                        "character": "alice",
                        "clip": "",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    skip = next(s for s in result["skipped"] if s["type"] == "play_clip")
    assert skip["reason"] == "no clip id"
