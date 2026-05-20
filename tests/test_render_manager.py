"""Tests for `blender_daemon.render_manager`.

Unit tests cover ffmpeg discovery and the no-bpy guard. Integration tests
render a tiny clip (3 frames) end-to-end and verify the MP4 exists.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import render_manager
from blender_daemon.render_manager import RenderError, _find_ffmpeg

# --- Unit (no Blender) --------------------------------------------------------


def test_render_raises_without_bpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(render_manager, "bpy", None)
    with pytest.raises(RenderError, match="bpy unavailable"):
        render_manager.render(0, 1, "/tmp/never.mp4")


def test_find_ffmpeg_uses_env_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setenv("FFMPEG_PATH", str(fake))
    assert _find_ffmpeg() == str(fake)


def test_find_ffmpeg_raises_for_bad_env_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FFMPEG_PATH", "/definitely/not/here/ffmpeg")
    with pytest.raises(RenderError, match="FFMPEG_PATH"):
        _find_ffmpeg()


def test_find_ffmpeg_falls_back_to_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    fake = tmp_path / "ffmpeg"
    fake.write_text("")
    monkeypatch.setattr(render_manager.shutil, "which", lambda _: str(fake))
    assert _find_ffmpeg() == str(fake)


def test_find_ffmpeg_raises_when_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(render_manager.shutil, "which", lambda _: None)
    with pytest.raises(RenderError, match="ffmpeg not found"):
        _find_ffmpeg()


# --- Integration (real Blender) -----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())
CHAR_PATH = str(Path("assets/characters/student_v1/character.fbx").resolve())
IDLE_PATH = str(Path("assets/animations/idle/animation.fbx").resolve())


@needs_blender
def test_real_render_writes_mp4(tmp_path: Path) -> None:
    from planner import daemon_runner

    out = tmp_path / "test.mp4"
    timeline = {
        "shots": [
            {
                "id": "s1",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0,
                        "end": 0.5,
                    }
                ],
            }
        ]
    }

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        h.call(
            "load_character",
            fbx_path=CHAR_PATH,
            spawn_point="door",
            handle="student",
        )
        h.call("execute_timeline", timeline=timeline, asset_paths={"idle": IDLE_PATH})
        result = h.call(
            "render",
            start_frame=0,
            end_frame=2,
            output_path=str(out),
        )

    assert out.exists(), f"render did not produce {out}"
    assert out.stat().st_size > 0, "MP4 is empty"
    assert result["frame_count"] == 3
    assert result["duration_s"] == pytest.approx(3 / 24)
    assert result["camera"] == "wide"


@needs_blender
def test_real_render_keep_frames_preserves_dir(tmp_path: Path) -> None:
    from planner import daemon_runner

    out = tmp_path / "kept.mp4"
    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        result = h.call(
            "render",
            start_frame=0,
            end_frame=1,
            output_path=str(out),
            keep_frames=True,
        )

    assert out.exists()
    assert result["frames_dir"] is not None
    frames_dir = Path(result["frames_dir"])
    assert frames_dir.is_dir()
    pngs = list(frames_dir.glob("*.png"))
    assert len(pngs) == 2  # frames 0 and 1
