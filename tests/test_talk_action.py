"""Tests for the talk action."""

import os
from pathlib import Path

import pytest

from actions import talk as talk_action
from blender_daemon import action_executor

# --- Unit ---------------------------------------------------------------------


def test_syllabify_basic() -> None:
    syllables = talk_action.syllabify("hello world")
    assert len(syllables) >= 2
    # "e" is the first vowel, "o" is the second; both should appear as visemes.
    visemes = {s.viseme for s in syllables}
    assert {"E", "O"} <= visemes


def test_syllabify_empty_text() -> None:
    assert talk_action.syllabify("...") == []


def test_syllabify_consecutive_vowels_one_syllable() -> None:
    syllables = talk_action.syllabify("queue")
    assert len(syllables) == 1


def test_talk_unknown_character_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bpy = type(
        "B",
        (),
        {
            "context": type("C", (), {"scene": type("S", (), {"objects": {}})()})(),
            "data": type("D", (), {"objects": []})(),
        },
    )
    monkeypatch.setattr(action_executor, "bpy", fake_bpy)
    monkeypatch.setattr(action_executor, "_index_characters_by_handle", lambda: {})
    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "talk",
                        "character": "ghost",
                        "text": "hello",
                        "start": 0,
                        "end": 1,
                    }
                ]
            }
        ]
    }
    result = action_executor.execute_timeline(timeline=timeline, asset_paths={})
    assert result["executed"] == []
    assert "not loaded" in result["skipped"][0]["reason"]


# --- Integration --------------------------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())


@needs_blender
def test_real_talk_noops_on_xbot_but_reports_syllables() -> None:
    """X-Bot has no shape keys, so talk's keyframes affect nothing — but the
    syllable count and viseme list should still be reported, proving the
    pipeline works for a real VRM character once one is loaded."""
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "talk",
                        "character": "student",
                        "text": "hello world this is a test",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="center_room",
            handle="student",
        )
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    assert len(result["executed"]) == 1
    placed = result["executed"][0]
    assert placed["type"] == "talk"
    assert placed["syllable_count"] >= 5
    assert placed["noop"] is True
    assert placed["affected_meshes"] == []


@needs_blender
def test_real_talk_with_emotion_is_recorded() -> None:
    from planner import daemon_runner

    timeline = {
        "shots": [
            {
                "actions": [
                    {
                        "id": "a1",
                        "type": "talk",
                        "character": "student",
                        "text": "I am happy",
                        "emotion": "joy",
                        "start": 0,
                        "end": 2,
                    }
                ]
            }
        ]
    }
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="center_room",
            handle="student",
        )
        result = h.call("execute_timeline", timeline=timeline, asset_paths={})

    placed = result["executed"][0]
    assert placed["emotion_overlay"] == "Joy"
