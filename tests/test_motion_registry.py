"""Tests for the motion-clip asset category (Step 51, Option C)."""

from __future__ import annotations

import json
from pathlib import Path

from planner.registry import MotionClipSpec, Registry, _load_motions


def _write(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


def test_load_motions_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert _load_motions(tmp_path / "missing") == {}


def test_load_motions_parses_a_clip(tmp_path: Path) -> None:
    motions_dir = tmp_path / "motions"
    _write(
        motions_dir / "kick" / "motion.json",
        {
            "id": "kick",
            "display_name": "Spinning kick",
            "description": "An aggressive martial-arts kick.",
            "fbx_file": "kick.fbx",
        },
    )
    out = _load_motions(motions_dir)
    assert set(out.keys()) == {"kick"}
    spec: MotionClipSpec = out["kick"]
    assert spec.display_name == "Spinning kick"
    assert spec.description == "An aggressive martial-arts kick."
    assert spec.fbx_path == motions_dir / "kick" / "kick.fbx"
    assert spec.applies_to_rig == "mixamo"


def test_load_motions_defaults_description_to_empty(tmp_path: Path) -> None:
    motions_dir = tmp_path / "motions"
    _write(
        motions_dir / "dance" / "motion.json",
        {"id": "dance", "display_name": "Disco shuffle", "fbx_file": "dance.fbx"},
    )
    assert _load_motions(motions_dir)["dance"].description == ""


def test_registry_load_populates_motions(tmp_path: Path) -> None:
    _write(
        tmp_path / "motions" / "kick" / "motion.json",
        {"id": "kick", "display_name": "Kick", "fbx_file": "kick.fbx"},
    )
    reg = Registry.load(tmp_path)
    assert "kick" in reg.motions


def test_system_prompt_omits_motions_section_when_empty(tmp_path: Path) -> None:
    reg = Registry.load(tmp_path)  # no motions dir at all
    # The section header is gated on `if self.motions`. The `play_clip`
    # action spec mentions "Available motion clips list below" in its
    # description regardless — check the actual header is absent.
    assert "# Available motion clips" not in reg.to_system_prompt_section()


def test_system_prompt_includes_motions_section_when_populated(tmp_path: Path) -> None:
    _write(
        tmp_path / "motions" / "kick" / "motion.json",
        {
            "id": "kick",
            "display_name": "Spinning kick",
            "description": "An aggressive martial-arts kick.",
            "fbx_file": "kick.fbx",
        },
    )
    reg = Registry.load(tmp_path)
    section = reg.to_system_prompt_section()
    assert "Available motion clips" in section
    assert "`kick` — Spinning kick" in section
    assert "An aggressive martial-arts kick." in section


def test_filtered_registry_preserves_motions(tmp_path: Path) -> None:
    _write(
        tmp_path / "motions" / "kick" / "motion.json",
        {"id": "kick", "display_name": "Kick", "fbx_file": "kick.fbx"},
    )
    reg = Registry.load(tmp_path)
    filtered = reg.filtered(scene_ids={"nope"}, character_ids={"nope"})
    assert "kick" in filtered.motions
