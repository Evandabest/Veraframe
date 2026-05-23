"""Stdout entrypoint that generates Action(s) for a block on the timeline.

The Electron app calls this when the user edits or adds an action via a
re-prompt. The character handle, start time, and action-id prefix are
FIXED by the caller; the LLM chooses action types and parameters and may
return more than one action when the user's description has concurrent
beats (e.g. "sit and face the camera" → a `sit` on the body channel
plus a `turn_to` on the rotation channel).

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

Stdout: JSON `{"actions": [...]}` — one or more Actions matching the
schema. The Electron caller is responsible for inserting all of them.
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

SYSTEM_PROMPT_TEMPLATE = """You generate one or more animation actions for the Veraframe timeline.

You will be given:
- The registry of available scenes, characters, and action types.
- The active scene id, the character handle, and the time window the actions must fill.
- (Optionally) the rest of the timeline as context so you can reference other characters or coordinate behaviour.
- A user instruction describing what the character should do during this time slot.

Output a JSON object `{"actions": [...]}`. Each item's `character`, `start`, `end`, and `id` will be OVERWRITTEN by the caller — so you may put any plausible values there; what matters is each action's `type` and type-specific parameters.

{registry_section}

# Rules

- Most prompts map to ONE action. Emit multiple actions only when the user describes truly concurrent beats on different channels (e.g. "sit and face the camera" → `sit` for the body + `turn_to` for the rotation; "walk to the door while talking" → `walk_to` + `talk`). Do NOT split a single intent across two actions to look thorough.
- The channels that compose concurrently for the same character: body (sit / stand / idle / walk_to / play_clip — pick one), talk, look_at, point_at, gestures (wave / nod / shake_head), face (smile / frown / blink). Two actions in the same channel at the same time = invalid.
- For target / look_at fields, refer to either a spawn point in the active scene or another character handle from the context. **NEVER use a camera preset name** as a target. If the user wrote "face the camera" / "turn to the camera", pick a character handle from the context that the camera is roughly framing; if none fits, prefer a head-only `look_at` over a body-rotating `turn_to`, or skip the rotation entirely.
- **Seated state.** If the character is currently in a held `sit` (the timeline shows a prior `sit` action with no subsequent `stand`) and the user says "stay seated" / "remain sitting" / "sit there", emit another `sit` — NOT `idle`. `idle` is a standing pose and would visibly pop the character out of the chair. Only emit `stand` when the user explicitly wants the character to get up.
- Use only the listed emotion values: neutral, joy, angry, sorrow, fun.
- Output a JSON object with exactly one top-level key `actions` — a non-empty list. No prose, no commentary."""


class ActionResponse(BaseModel):
    """LLM response wrapper.

    A list of Actions so the caller can request truly concurrent beats
    (sit + turn_to, walk_to + talk) in a single call. Most prompts still
    map to a single-element list. Wrapping the list in a parent object
    makes structured output reliable across providers.
    """

    actions: list[Action]


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

    # `args.end` is None in the add-action flow (LLM picks duration); only
    # the edit flow locks both endpoints.
    end_label = f"{args.end:.2f}s" if args.end is not None else "?"
    print(
        f"action via {config.model_string} for {args.character} @ "
        f"{args.start:.2f}-{end_label}",
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

    if not wrapped.actions:
        print("[run_action] LLM returned an empty actions list", file=sys.stderr)
        return 1

    # Overwrite the fields the caller has authority over. Start, character,
    # and id are always forced. End is only forced when the caller provided
    # one (edit flow); otherwise we keep the LLM's chosen end after a
    # sanity check. The caller's --action-id is the BASE — when the LLM
    # returns multiple actions we suffix `_2`, `_3`, … so each is unique.
    finals = []
    for index, action in enumerate(wrapped.actions):
        payload = action.model_dump()
        payload["id"] = args.action_id if index == 0 else f"{args.action_id}_{index + 1}"
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
        finals.append(TypeAdapter(Action).validate_python(payload))

    sys.stdout.write(
        json.dumps({"actions": [a.model_dump(mode="json") for a in finals]}) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
