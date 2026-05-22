"""Stdout entrypoint that rewrites a free-form user prompt into one that
references concrete registry assets (scenes, characters, spawn points,
cameras) by exact name.

The Electron app invokes this as a short-lived subprocess from the AI-enhance
button. The output is plain text (the rewritten prompt), not JSON.

Usage:

    uv run python -m planner.run_enhance --prompt "..." --assets ./assets

Stdout: the enhanced prompt.
Stderr: free-form log/progress.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import litellm

ENHANCE_SYSTEM_PROMPT = """You are a prompt-rewriting assistant for Veraframe, a system that turns natural-language scene descriptions into structured Blender animation timelines.

Your job: take the user's free-form prompt and rewrite it so the downstream planner can map every reference to a concrete asset. Use the EXACT names from the catalog below; do NOT invent scenes, characters, spawn points, cameras, or action types.

{registry_section}

# Rewrite rules

- **Preserve the user's original intent.** The story beats, character actions, mood, and overall narrative arc must remain the same — you are sharpening references and timing, not re-imagining the scene. If the user wrote "she walks in sadly", the rewrite still has her walk in sadly. If they didn't mention something, don't add it.
- Pick one scene by id and reference it explicitly.
- For every character the user mentions, name THREE things separately so the downstream planner doesn't confuse them:
  - a short human handle for the rest of the prompt (a role name like "the teacher" or whatever fits the user's wording),
  - the character preset to load — must be one of the ids from the "Available characters" catalog above,
  - the spawn point — must be one of the chosen scene's spawn points.
  Mention the preset id in a backticked parenthetical right after the handle (e.g. "the teacher (preset \`SOME_PRESET_FROM_THE_CATALOG\`)"). Substitute a REAL preset id from the catalog — never emit angle brackets, ALL CAPS slot names, or any literal text from these rules.
- Translate vague verbs into action types from the action list. Resolve targets to spawn point names or other character handles (not preset ids).
- Add explicit absolute timestamps (in seconds) for each action — choose plausible durations if the user gave none.
- Pick a camera preset from the chosen scene's list. Camera presets and character presets are different lists — never use a camera name where a character preset is expected, or vice versa.
- Keep the rewrite concise (a short paragraph or a few short sentences). Do NOT output JSON. Do NOT add commentary, preface, or explanation — only the rewritten prompt itself.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="planner.run_enhance")
    parser.add_argument("--prompt", required=True, help="The user's free-form prompt.")
    parser.add_argument(
        "--assets",
        default="assets",
        help="Asset registry directory (default: ./assets).",
    )
    args = parser.parse_args(argv)

    from planner.llm_client import LLMConfig
    from planner.registry import Registry

    registry = Registry.load(Path(args.assets).resolve())
    config = LLMConfig.from_env()
    system_prompt = ENHANCE_SYSTEM_PROMPT.format(
        registry_section=registry.to_system_prompt_section()
    )

    print(
        f"enhance via {config.model_string} ({len(registry.scenes)} scene(s), "
        f"{len(registry.characters)} character(s))",
        file=sys.stderr,
    )

    response = litellm.completion(
        model=config.model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": args.prompt},
        ],
        temperature=0.3,
    )
    content = response.choices[0].message.content or ""
    sys.stdout.write(content.strip() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
