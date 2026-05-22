"""Stdout entrypoint that emits a validated timeline JSON for a prompt.

Used by the Electron main process (and any other supervisor) to get a fresh
timeline without depending on Python for the daemon orchestration. The
supervisor invokes this as a short-lived subprocess and feeds the JSON to its
own daemon client.

Usage:

    uv run python -m planner.run_planner --prompt "..." --assets ./assets

Stdout: the validated timeline JSON.
Stderr: free-form log/progress messages.
Exit 0 on success; non-zero on failure (LLM error or validation exhaustion).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="planner.run_planner")
    parser.add_argument("--prompt", required=True, help="Natural-language scene description.")
    parser.add_argument(
        "--assets",
        default="assets",
        help="Asset registry directory (default: ./assets).",
    )
    parser.add_argument(
        "--selected-scene",
        default=None,
        help="If set, hard-constrain the LLM to use this scene id.",
    )
    parser.add_argument(
        "--selected-characters",
        default=None,
        help="Comma-separated list of character preset ids; if set, restricts the LLM to these.",
    )
    args = parser.parse_args(argv)

    from planner.registry import Registry
    from planner.validator import generate_validated_timeline

    full_registry = Registry.load(Path(args.assets).resolve())
    print(
        f"registry: {len(full_registry.scenes)} scene(s), "
        f"{len(full_registry.characters)} character(s), "
        f"{len(full_registry.animations)} animation(s)",
        file=sys.stderr,
    )

    # Filter the registry to just the user-selected scene + characters so the
    # system-prompt "Available …" section only lists what's allowed. The
    # validator also uses this filtered registry, so any timeline that
    # references something outside the selection fails semantic validation
    # and the retry loop kicks in — turning the soft prompt-level
    # constraint into a hard enforcement.
    scene_filter: set[str] | None = None
    if args.selected_scene:
        if args.selected_scene not in full_registry.scenes:
            print(
                f"warning: --selected-scene='{args.selected_scene}' is not in the registry; "
                f"available: {', '.join(full_registry.scenes.keys())}",
                file=sys.stderr,
            )
        else:
            scene_filter = {args.selected_scene}
    character_filter: set[str] | None = None
    if args.selected_characters:
        char_ids = [c.strip() for c in args.selected_characters.split(",") if c.strip()]
        invalid = [c for c in char_ids if c not in full_registry.characters]
        if invalid:
            print(
                f"warning: --selected-characters contains unknown ids: {invalid}; "
                f"available: {', '.join(full_registry.characters.keys())}",
                file=sys.stderr,
            )
        valid = [c for c in char_ids if c in full_registry.characters]
        if valid:
            character_filter = set(valid)

    registry = full_registry.filtered(scene_filter, character_filter)
    if scene_filter or character_filter:
        print(
            f"filtered registry: {len(registry.scenes)} scene(s), "
            f"{len(registry.characters)} character(s)",
            file=sys.stderr,
        )

    # The filtered registry alone makes the catalog tight. We still add a
    # belt-and-suspenders constraint line so the model sees an explicit
    # instruction (helpful for small Ollama models that occasionally
    # hallucinate ids that aren't in the catalog).
    prompt = args.prompt
    constraint_lines: list[str] = []
    if scene_filter:
        constraint_lines.append(
            f"# Hard constraint\n"
            f"You MUST use the scene with id `{next(iter(scene_filter))}`. "
            f"It is the only scene listed in the catalog above."
        )
    if character_filter:
        constraint_lines.append(
            f"You MUST use ONLY these character presets when declaring characters: "
            f"{', '.join(sorted(character_filter))}. They are the only presets in the catalog."
        )
    if constraint_lines:
        prompt = "\n\n".join(constraint_lines) + "\n\n# User instruction\n" + args.prompt

    project = generate_validated_timeline(prompt, registry)
    json.dump(project.model_dump(mode="json"), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
