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

    registry = Registry.load(Path(args.assets).resolve())
    print(
        f"registry: {len(registry.scenes)} scene(s), "
        f"{len(registry.characters)} character(s), "
        f"{len(registry.animations)} animation(s)",
        file=sys.stderr,
    )

    # Prepend hard constraints to the user prompt. We do this in the user
    # message (not the system prompt) because the validator's retry loop
    # rewrites the user prompt with feedback on each attempt — putting the
    # constraints there ensures they survive across retries.
    prompt = args.prompt
    constraint_lines: list[str] = []
    if args.selected_scene:
        if args.selected_scene not in registry.scenes:
            print(
                f"warning: --selected-scene='{args.selected_scene}' is not in the registry; "
                f"available: {', '.join(registry.scenes.keys())}",
                file=sys.stderr,
            )
        constraint_lines.append(
            f"# Hard constraint\n"
            f"You MUST use the scene with id `{args.selected_scene}`. Do not pick any other scene."
        )
    if args.selected_characters:
        char_ids = [c.strip() for c in args.selected_characters.split(",") if c.strip()]
        invalid = [c for c in char_ids if c not in registry.characters]
        if invalid:
            print(
                f"warning: --selected-characters contains unknown ids: {invalid}; "
                f"available: {', '.join(registry.characters.keys())}",
                file=sys.stderr,
            )
        constraint_lines.append(
            f"You MUST use ONLY these character presets when declaring characters: "
            f"{', '.join(char_ids)}. Do not introduce any other character preset."
        )
    if constraint_lines:
        prompt = "\n\n".join(constraint_lines) + "\n\n# User instruction\n" + args.prompt

    project = generate_validated_timeline(prompt, registry)
    json.dump(project.model_dump(mode="json"), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
