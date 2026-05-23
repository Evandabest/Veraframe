"""Tests for the range-edit subprocess entry point.

Network calls to the LLM are not exercised here — those happen in real
end-to-end flows. We pin the argparse contract + the inverted-window
guard so the supervisor (Electron main process) doesn't accidentally
shell out with a malformed request.
"""

from __future__ import annotations

import io
import sys

from planner.run_range_edit import RangeResponse, _parse_args, main


def test_argparse_requires_prompt_scene_start_end() -> None:
    args = _parse_args(
        [
            "--prompt",
            "make this tense",
            "--scene",
            "lab",
            "--start",
            "4",
            "--end",
            "10",
        ]
    )
    assert args.prompt == "make this tense"
    assert args.scene == "lab"
    assert args.start == 4.0
    assert args.end == 10.0
    assert args.assets == "assets"  # default


def test_inverted_window_exits_nonzero_without_calling_llm() -> None:
    # If --end <= --start, main() must short-circuit before any LLM call.
    err = io.StringIO()
    saved = sys.stderr
    sys.stderr = err
    try:
        rc = main(
            [
                "--prompt",
                "x",
                "--scene",
                "lab",
                "--start",
                "5",
                "--end",
                "5",
            ]
        )
    finally:
        sys.stderr = saved
    assert rc == 2
    assert "must be >" in err.getvalue()


def test_range_response_validates_a_minimal_payload() -> None:
    payload = {
        "actions": [
            {
                "id": "r1",
                "type": "idle",
                "character": "alice",
                "start": 4.0,
                "end": 6.0,
            }
        ]
    }
    parsed = RangeResponse.model_validate(payload)
    assert len(parsed.actions) == 1
    assert parsed.actions[0].type == "idle"
