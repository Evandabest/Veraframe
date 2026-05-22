"""Stdout entrypoint that generates a single Action for an existing block on
the timeline.

The Electron app calls this when the user edits a block via a re-prompt. The
character handle, start/end window, and action id are FIXED by the caller; the
LLM only chooses the action type and its parameters.

Usage:

    uv run python -m planner.run_action \\
      --prompt "have her smile while looking at the robot" \\
      --assets ./assets \\
      --scene classroom \\
      --character student_actor \\
      --action-id act_001 \\
      --start 4.0 \\
      --end 6.0 \\
      --context-json '{"characters": [...], "shots": [...]}'

Stdout: JSON of the generated Action (matching planner.schema.Action).
Stderr: free-form progress.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import litellm
from pydantic import BaseModel, TypeAdapter

from planner.llm_client import LLMConfig
from planner.registry import Registry
from planner.schema import Action

SYSTEM_PROMPT_TEMPLATE = """You generate a SINGLE animation action for the Veraframe timeline.

You will be given:
- The registry of available scenes, characters, and action types.
- The active scene id, the character handle, and the time window the action must fill.
- (Optionally) the rest of the timeline as context so you can reference other characters or coordinate behaviour.
- A user instruction describing what the character should do during this time slot.

Output a JSON object containing ONE action that conforms to the action schema. The action's `character`, `start`, `end`, and `id` will be OVERWRITTEN by the caller — so you may put any plausible values there; what matters is the `type` and its type-specific parameters.

{registry_section}

# Rules

- Pick exactly one action type from the available actions list.
- For target / look_at fields, refer to either a spawn point in the active scene or another character handle from the context.
- Use only the listed emotion values: neutral, joy, angry, sorrow, fun.
- Output a JSON object with exactly one top-level key `action`. The value is the action object. No prose, no commentary."""


class ActionResponse(BaseModel):
    """LLM response wrapper — a single field whose schema is the discriminated
    Action union. Wrapping in a parent object makes structured output more
    reliable across providers than asking for a union at the top level."""

    action: Action


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="planner.run_action")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--assets", default="assets")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--character", required=True, help="Character handle (id), not preset.")
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--start", required=True, type=float)
    parser.add_argument(
        "--end",
        type=float,
        default=None,
        help="If provided, locks the action's end time (used when editing an existing block). "
        "Otherwise the LLM chooses a sensible duration based on the action type.",
    )
    parser.add_argument("--context-json", default="{}", help="Timeline-context JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    registry = Registry.load(Path(args.assets).resolve())

    try:
        context = json.loads(args.context_json)
    except json.JSONDecodeError:
        print(f"[run_action] --context-json was not valid JSON; ignoring", file=sys.stderr)
        context = {}

    config = LLMConfig.from_env()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        registry_section=registry.to_system_prompt_section()
    )

    if args.end is not None:
        timing_msg = (
            f"Time window: {args.start:.2f}s → {args.end:.2f}s (FIXED — use this exact window)."
        )
    else:
        timing_msg = (
            f"Start time: {args.start:.2f}s (FIXED). "
            "End time is up to you — pick a sensible duration for the action "
            "(facial expressions ~1-2s, walks ~3-5s, idles can be anything). "
            "The caller will accept whatever end you choose."
        )

    user_message = (
        f"Active scene: `{args.scene}`.\n"
        f"Character handle: `{args.character}`.\n"
        f"{timing_msg}\n"
        f"Existing timeline context (for reference):\n```json\n{json.dumps(context)}\n```\n\n"
        f"User instruction: {args.prompt}"
    )

    print(
        f"action via {config.model_string} for {args.character} @ "
        f"{args.start:.2f}-{args.end:.2f}s",
        file=sys.stderr,
    )

    response = litellm.completion(
        model=config.model_string,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format=ActionResponse,
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    print(f"[run_action] response from {config.model_string}:", file=sys.stderr)
    print(content, file=sys.stderr)
    wrapped = ActionResponse.model_validate_json(content)

    # Overwrite the fields the caller has authority over. Start and id and
    # character are always forced. End is only forced when the caller provided
    # one (edit flow); otherwise we keep the LLM's chosen end after a sanity
    # check.
    payload = wrapped.action.model_dump()
    payload["id"] = args.action_id
    payload["character"] = args.character
    payload["start"] = args.start
    if args.end is not None:
        payload["end"] = args.end
    if payload["end"] <= payload["start"]:
        print(
            f"[run_action] LLM picked end={payload['end']} <= start={payload['start']};"
            " falling back to start + 2s",
            file=sys.stderr,
        )
        payload["end"] = payload["start"] + 2.0
    final = TypeAdapter(Action).validate_python(payload)

    sys.stdout.write(json.dumps(final.model_dump(mode="json")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
