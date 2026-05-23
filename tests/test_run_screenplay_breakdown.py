"""Tests for the screenplay-breakdown subprocess (Step 40)."""

from __future__ import annotations

import io
import sys

from planner.run_screenplay_breakdown import BreakdownResponse, _parse_args, main


def test_argparse_requires_text() -> None:
    args = _parse_args(["--text", "INT. ROOM - DAY\nALICE enters."])
    assert args.text.startswith("INT.")


def test_empty_text_exits_without_llm_call() -> None:
    err = io.StringIO()
    saved = sys.stderr
    sys.stderr = err
    try:
        rc = main(["--text", "   "])
    finally:
        sys.stderr = saved
    assert rc == 2
    assert "empty" in err.getvalue()


def test_breakdown_response_validates() -> None:
    out = BreakdownResponse.model_validate(
        {"segments": [{"start": 0.0, "end": 3.5, "prompt": "alice enters"}]}
    )
    assert len(out.segments) == 1
    assert out.segments[0].prompt == "alice enters"


def test_breakdown_response_rejects_zero_length_segment() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BreakdownResponse.model_validate(
            {"segments": [{"start": 0.0, "end": 0.0, "prompt": "x"}]}
        )
