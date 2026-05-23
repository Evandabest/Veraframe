"""Stdout entrypoint that generates a list of Actions for a *time window*.

Used by the Electron app's natural-language range-edit feature. The user
selects [start, end] on the timeline, types a re-prompt like "make this
beat tense", and the supervisor invokes this subprocess. We hand the LLM
the current timeline as context, fix the active scene + window, and ask
for a fresh list of actions to occupy that window.

Usage:

    uv run python -m planner.run_range_edit \\
      --prompt "alice should pace nervously" \\
      --assets ./assets \\
      --scene classroom \\
      --start 4.0 \\
      --end 10.0 \\
      --context-json '{"characters": [...], "shots": [...]}'

Stdout: JSON `{"actions": [...]}` where every action has start/end in
[start, end] and a unique id (the caller can rename ids if it wants).
Stderr: free-form progress.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import litellm
from pydantic import BaseModel

from planner.llm_client import LLMConfig
from planner.registry import Registry
from planner.schema import Action

SYSTEM_PROMPT_TEMPLATE = """You generate a LIST of animation actions that fill a fixed time window in an existing Veraframe timeline.

You will be given:
- The registry of available scenes, characters, and action types.
- The active scene id.
- The time window [start_s, end_s] you are responsible for.
- The current timeline as context — actions outside the window stay as-is; you must NOT reference or duplicate them.
- A user instruction describing what should happen in the window.

Output a JSON object with a single key `actions`. Its value is a list of action objects, each conforming to the action schema.

# Rules

- Every action's `start` and `end` must fall inside [start_s, end_s]. You may use the full window or only part of it.
- Every action's `end` must be greater than its `start`.
- Each action gets a unique `id` (e.g. "range_1", "range_2"). The caller may rename ids; only the relative ordering matters.
- The actions can mix camera, character, and stage actions; pick what best matches the user instruction.
- For target / look_at fields, refer to either a spawn point in the active scene or a character handle from the timeline context.
- Use only the listed emotion values: neutral, joy, angry, sorrow, fun.
- Output NOTHING but the JSON object. No prose, no commentary.

{registry_section}
"""


class RangeResponse(BaseModel):
    """LLM response wrapper holding the new actions for the window."""

    actions: list[Action]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="planner.run_range_edit")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--assets", default="assets")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument("--end", required=True, type=float)
    parser.add_argument("--context-json", default="{}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.end <= args.start:
        print(
            f"[run_range_edit] end ({args.end}) must be > start ({args.start})",
            file=sys.stderr,
        )
        return 2

    registry = Registry.load(Path(args.assets).resolve())
    try:
        context = json.loads(args.context_json)
    except json.JSONDecodeError:
        print("[run_range_edit] --context-json was not valid JSON; ignoring", file=sys.stderr)
        context = {}

    config = LLMConfig.from_env()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        registry_section=registry.to_system_prompt_section()
    )

    user_message = (
        f"Active scene: `{args.scene}`.\n"
        f"Time window: {args.start:.2f}s → {args.end:.2f}s. All emitted actions must fall inside this window.\n"
        f"Existing timeline context (do NOT duplicate anything outside the window):\n"
        f"```json\n{json.dumps(context)}\n```\n\n"
        f"User instruction: {args.prompt}"
    )

    print(
        f"range_edit via {config.model_string} for window {args.start:.2f}-{args.end:.2f}s",
        file=sys.stderr,
    )
    t0 = time.time()
    response = litellm.completion(
        model=config.model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format=RangeResponse,
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    print(f"[run_range_edit] response in {time.time() - t0:.1f}s:", file=sys.stderr)
    print(content, file=sys.stderr)
    wrapped = RangeResponse.model_validate_json(content)

    # Clamp + rename ids defensively so the caller doesn't have to.
    payload = []
    for i, a in enumerate(wrapped.actions):
        obj = a.model_dump(mode="json")
        # Force every action's window inside [start, end]. The LLM is told
        # to do this but we double-check.
        obj["start"] = max(args.start, float(obj["start"]))
        obj["end"] = min(args.end, float(obj["end"]))
        if obj["end"] <= obj["start"]:
            print(
                f"[run_range_edit] dropped action with empty window after clamp: {obj}",
                file=sys.stderr,
            )
            continue
        obj["id"] = obj.get("id") or f"range_{i + 1}"
        payload.append(obj)

    sys.stdout.write(json.dumps({"actions": payload}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
