"""Stdout entrypoint that breaks a screenplay-format text into a list of
shot-level prompts with estimated timing (Step 40).

The user pastes Fountain-ish screenplay prose; this script asks the LLM
to segment it into beats and emit a list of `{start, end, prompt}`
objects matching the shape Veraframe's "Script mode" already accepts.

The supervisor (Electron app) calls this as a short-lived subprocess
and shows the result in a preview UI for the user to confirm / edit
before the actual timeline render runs.

Usage:

    uv run python -m planner.run_screenplay_breakdown \\
      --text "INT. CLASSROOM - DAY\\n\\nALICE..."

Stdout: JSON `{"segments": [{"start": 0.0, "end": 3.5, "prompt": "..."}]}`.
Stderr: free-form progress.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import litellm
from pydantic import BaseModel, Field

from planner.llm_client import LLMConfig

SYSTEM_PROMPT = """You break a screenplay-format text into shot-level beats for a Veraframe timeline.

Input is plain prose, typically with Fountain-style conventions:
- Scene headings like `INT. CLASSROOM - DAY` or `EXT. ROOFTOP - NIGHT`
- Action lines (no character prefix)
- Character cues (NAME in caps on its own line) followed by dialog
- Parentheticals like `(angrily)` modifying dialog

Output a JSON object `{"segments": [...]}` where each segment is `{start, end, prompt}`:
- `start` and `end` are seconds, in monotonically increasing order, non-overlapping
- `prompt` is a single-sentence natural-language description of what happens in that window
- Estimate dialog at ~2.5 words per second
- Estimate action lines at the time the described action would naturally take (a walk ~3-5s, a glance ~1s)
- Treat each line of dialog or each significant action sentence as its own beat
- Use the same character names the screenplay uses (lowercase the handle in the prompt: `ALICE` -> `alice`)
- Do NOT invent characters or props not in the screenplay
- Do NOT emit anything but the JSON object — no prose, no commentary
"""


class Segment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    prompt: str = Field(min_length=1)


class BreakdownResponse(BaseModel):
    segments: list[Segment]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="planner.run_screenplay_breakdown")
    parser.add_argument(
        "--text",
        required=True,
        help="Screenplay text to break down. Newlines as escape sequences are fine.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    text = args.text
    if not text.strip():
        print("[run_screenplay_breakdown] --text is empty", file=sys.stderr)
        return 2

    config = LLMConfig.from_env()
    print(
        f"screenplay_breakdown via {config.model_string} ({len(text)} chars)",
        file=sys.stderr,
    )
    t0 = time.time()
    response = litellm.completion(
        model=config.model_string,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format=BreakdownResponse,
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    print(f"[run_screenplay_breakdown] response in {time.time() - t0:.1f}s", file=sys.stderr)
    print(content, file=sys.stderr)
    parsed = BreakdownResponse.model_validate_json(content)

    # Defensive normalization: clip negative starts, enforce monotonicity
    # by dropping out-of-order segments. The UI surfaces what the model
    # produced; broken segments would only confuse the preview.
    cleaned: list[Segment] = []
    cursor = 0.0
    for seg in parsed.segments:
        if seg.start < cursor:
            print(
                f"[run_screenplay_breakdown] dropping out-of-order segment "
                f"start={seg.start} cursor={cursor}",
                file=sys.stderr,
            )
            continue
        if seg.end <= seg.start:
            print(
                f"[run_screenplay_breakdown] dropping zero-length segment "
                f"start={seg.start} end={seg.end}",
                file=sys.stderr,
            )
            continue
        cleaned.append(seg)
        cursor = seg.end

    sys.stdout.write(
        json.dumps({"segments": [s.model_dump(mode="json") for s in cleaned]}) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
