"""Tests for the `veraframe` developer CLI.

Unit tests cover the argparse surface (the `--dev` gate, prompt-required
without --mock). The integration test runs the full mocked pipeline against
real Blender and verifies an MP4 lands on disk.
"""

import os
from pathlib import Path

import pytest

from planner.cli import main

# --- Unit ---------------------------------------------------------------------


def test_without_dev_flag_prints_redirect(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["render", "--mock", "--out", "/tmp/never.mp4"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Electron app" in captured.out


def test_dev_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--dev"])
    assert code == 1
    captured = capsys.readouterr()
    assert "render" in captured.out


def test_dev_render_without_prompt_or_mock_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    code = main(["--dev", "render", "--out", "/tmp/never.mp4"])
    assert code == 2
    assert any("prompt is required" in r.message for r in caplog.records)


# --- Integration (real Blender) ----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


@needs_blender
def test_dev_render_mock_produces_mp4(tmp_path: Path) -> None:
    out = tmp_path / "phase1.mp4"
    code = main(["--dev", "render", "--mock", "--out", str(out)])
    assert code == 0, "CLI exited non-zero"
    assert out.exists(), "MP4 was not written"
    assert out.stat().st_size > 0, "MP4 is empty"
