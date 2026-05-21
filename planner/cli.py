"""Veraframe developer CLI — exercises the full pipeline without the GUI.

Gated behind `--dev` so end users (who use the Electron app) don't see it.

Usage:

    veraframe --dev render "a student stands in the lab" --out out.mp4
    veraframe --dev render --mock --out out.mp4   # canned timeline, no LLM call

The non-`--dev` invocation prints a message pointing to the Electron app.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("veraframe")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="veraframe")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable developer commands (required for `render`).",
    )

    subparsers = parser.add_subparsers(dest="command")

    render_parser = subparsers.add_parser(
        "render", help="Generate a scene from a prompt and render it to MP4."
    )
    render_parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Natural-language scene description (omitted with --mock).",
    )
    render_parser.add_argument("--out", required=True, help="Output MP4 path.")
    render_parser.add_argument(
        "--assets", default="assets", help="Asset registry directory (default: ./assets)."
    )
    render_parser.add_argument(
        "--mock",
        action="store_true",
        help="Skip the LLM call and use a hand-written single-idle timeline.",
    )
    render_parser.add_argument(
        "--fps", type=int, default=24, help="Frame rate for execution + render."
    )
    render_parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Length of the mock timeline in seconds (only used with --mock).",
    )
    render_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args(argv)

    if not args.dev:
        print("Use the Electron app. Pass --dev to run the developer CLI.")
        return 1

    if args.command == "render":
        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
        return _cmd_render(args)

    parser.print_help()
    return 1


def _cmd_render(args: argparse.Namespace) -> int:
    # Imports here so `--help` doesn't pay the cost of pulling in litellm etc.
    from planner.daemon_runner import DaemonError, daemon
    from planner.registry import Registry

    if not args.mock and not args.prompt:
        log.error("a prompt is required unless --mock is passed")
        return 2

    assets_dir = Path(args.assets).resolve()
    out_path = Path(args.out).resolve()

    log.info("loading registry from %s", assets_dir)
    registry = Registry.load(assets_dir)
    log.info(
        "registry: %d scene(s), %d character(s), %d animation(s)",
        len(registry.scenes),
        len(registry.characters),
        len(registry.animations),
    )

    if args.mock:
        log.info(
            "--mock: skipping LLM call, using canned %.1fs single-idle timeline",
            args.duration,
        )
        project_dict = _canned_timeline(registry, duration=args.duration)
    else:
        from planner.validator import generate_validated_timeline

        log.info("calling LLM with prompt: %r", args.prompt)
        t0 = time.monotonic()
        project = generate_validated_timeline(args.prompt, registry)
        log.info("LLM produced timeline in %.1fs", time.monotonic() - t0)
        project_dict = project.model_dump(mode="json")

    log.debug("timeline: %s", json.dumps(project_dict, indent=2))

    scene_id = project_dict["scene"]
    if scene_id not in registry.scenes:
        log.error("scene '%s' not in registry", scene_id)
        return 3
    scene_spec = registry.scenes[scene_id]
    blend_path = str(scene_spec.blend_path.resolve())

    asset_paths = {
        anim_id: str(spec.fbx_path.resolve()) for anim_id, spec in registry.animations.items()
    }

    duration_s = max((shot["end"] for shot in project_dict["shots"]), default=0.0)
    if duration_s <= 0:
        log.error("timeline has zero duration; nothing to render")
        return 4
    end_frame = int(duration_s * args.fps)
    log.info(
        "rendering scene '%s' for %.2fs (%d frame(s)) -> %s",
        scene_id,
        duration_s,
        end_frame + 1,
        out_path,
    )

    try:
        with daemon() as h:
            log.info("daemon up, blender %s", h.call("status")["blender_version"])
            log.info("load_scene %s", blend_path)
            h.call("load_scene", blend_path=blend_path)

            for character in project_dict["characters"]:
                preset_id = character["preset"]
                if preset_id not in registry.characters:
                    log.error("character preset '%s' not in registry", preset_id)
                    return 5
                fbx = str(registry.characters[preset_id].mesh_path.resolve())
                log.info(
                    "load_character handle=%s preset=%s spawn=%s",
                    character["id"],
                    preset_id,
                    character["spawn"],
                )
                h.call(
                    "load_character",
                    fbx_path=fbx,
                    spawn_point=character["spawn"],
                    handle=character["id"],
                )

            log.info("execute_timeline (%d shot(s))", len(project_dict["shots"]))
            exec_result = h.call(
                "execute_timeline",
                timeline=project_dict,
                asset_paths=asset_paths,
                fps=args.fps,
            )
            log.info(
                "executed: %d, skipped: %d",
                len(exec_result["executed"]),
                len(exec_result["skipped"]),
            )
            for skip in exec_result["skipped"]:
                log.warning("skipped %s (%s): %s", skip["id"], skip["type"], skip["reason"])

            log.info("rendering frames 0..%d", end_frame)
            render_result = h.call(
                "render",
                start_frame=0,
                end_frame=end_frame,
                output_path=str(out_path),
                fps=args.fps,
            )
    except DaemonError as e:
        log.error("daemon failed: %s", e)
        return 6

    log.info("done: %s (%.2fs)", render_result["video_path"], render_result["duration_s"])
    print(render_result["video_path"])
    return 0


def _canned_timeline(registry: Any, duration: float = 2.0) -> dict:
    """Build a hand-written timeline for `--mock`.

    If the registry has a `walk_in_place` animation and the scene has more
    than one spawn point, the canned timeline walks the character from a
    starting spawn to a centered one and then idles for the remainder.
    Otherwise it falls back to a single idle of `duration` seconds.
    """
    if not registry.scenes:
        raise SystemExit("--mock: registry has no scenes")
    if not registry.characters:
        raise SystemExit("--mock: registry has no characters")

    scene_id, scene = next(iter(registry.scenes.items()))
    char_preset_id = next(iter(registry.characters))
    camera = scene.camera_presets[0]

    has_walk = "walk_in_place" in registry.animations
    centered = "center_room" if "center_room" in scene.spawn_points else None
    walk_start = next((s for s in scene.spawn_points if s != centered), None)

    if has_walk and centered and walk_start and duration >= 3.0:
        # Mixamo's Walking clip cycles at ~1.4m per cycle and ~3 cycles per
        # 4 seconds. Door→center_room is 5m, so a 5–6 second walk matches the
        # foot stride; faster and the character slides instead of stepping.
        walk_duration = min(6.0, duration * 0.5)
        return {
            "project": "mock",
            "scene": scene_id,
            "characters": [{"id": "student", "preset": char_preset_id, "spawn": walk_start}],
            "shots": [
                {
                    "id": "shot_001",
                    "start": 0.0,
                    "end": duration,
                    "camera": camera,
                    "actions": [
                        {
                            "id": "a1",
                            "type": "walk_to",
                            "character": "student",
                            "target": centered,
                            "start": 0.0,
                            "end": walk_duration,
                        },
                        {
                            "id": "a2",
                            "type": "idle",
                            "character": "student",
                            "start": walk_duration,
                            "end": duration,
                        },
                    ],
                }
            ],
        }

    spawn = centered or scene.spawn_points[0]
    return {
        "project": "mock",
        "scene": scene_id,
        "characters": [{"id": "student", "preset": char_preset_id, "spawn": spawn}],
        "shots": [
            {
                "id": "shot_001",
                "start": 0.0,
                "end": duration,
                "camera": camera,
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0.0,
                        "end": duration,
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    sys.exit(main())
