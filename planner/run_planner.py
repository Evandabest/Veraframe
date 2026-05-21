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

    project = generate_validated_timeline(args.prompt, registry)
    json.dump(project.model_dump(mode="json"), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
