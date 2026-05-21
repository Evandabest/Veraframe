"""Tests for `blender_daemon.scene_loader`.

Unit tests run without Blender by exploiting the `bpy is None` guard. The
integration tests load the real `dark_lab` scene and are gated behind
`BLENDER_AVAILABLE=1` like the daemon tests.
"""

import os
from pathlib import Path

import pytest

from blender_daemon import scene_loader
from blender_daemon.scene_loader import SceneLoadError, load_scene

# --- Unit (bpy unavailable) ---------------------------------------------------


def test_load_scene_raises_without_bpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_loader, "bpy", None)
    with pytest.raises(SceneLoadError, match="bpy is not available"):
        load_scene("/anything")


# --- Integration (real Blender) -----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


SCENE_PATH = str(Path("assets/scenes/dark_lab/scene.blend").resolve())


@needs_blender
def test_real_load_scene_returns_expected_inventory() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        result = h.call("load_scene", blend_path=SCENE_PATH)

    assert sorted(result["spawn_points"]) == ["center_room", "door", "robot_station"]
    assert result["cameras"] == ["close_student", "wide"]
    assert result["scene_name"]
    assert result["object_count"] >= 4  # 3 empties + 1 camera at minimum


@needs_blender
def test_real_load_scene_missing_file_surfaces_as_daemon_error() -> None:
    from planner import daemon_runner
    from planner.daemon_runner import DaemonError

    with daemon_runner.daemon() as h, pytest.raises(DaemonError, match="scene file not found"):
        h.call("load_scene", blend_path="/tmp/does_not_exist.blend")


@needs_blender
def test_real_status_still_responds_after_load_scene() -> None:
    from planner import daemon_runner

    with daemon_runner.daemon() as h:
        h.call("load_scene", blend_path=SCENE_PATH)
        status = h.call("status")
    assert status["ok"] is True
