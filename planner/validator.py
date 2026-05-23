"""Semantic validation of a `Project` against a `Registry`, plus the retry loop
that wraps `planner.llm_client.generate_timeline` and feeds validation errors
back to the model.

Schema-level validation (required fields, types, enums, end>start) is enforced
by Pydantic in `planner.schema`. The actual semantic checks live in
`planner.validators` as a pipeline of named passes — see that package's
docstring for the architecture and how to add a new pass. This module is
the thin façade that runs the pipeline and adapts its output to the
existing retry-loop API.
"""

from collections.abc import Sequence

from pydantic import ValidationError

from planner.llm_client import LLMConfig, generate_timeline
from planner.registry import Registry
from planner.schema import Project
from planner.validators import PipelineResult, default_passes, run_pipeline


class TimelineGenerationError(RuntimeError):
    """Raised by `generate_validated_timeline` when retries are exhausted."""

    def __init__(self, attempts: int, last_feedback: list[str]) -> None:
        self.attempts = attempts
        self.last_feedback = list(last_feedback)
        joined = "\n".join(f"- {m}" for m in last_feedback)
        super().__init__(f"giving up after {attempts} attempt(s). Last errors:\n{joined}")


# ---------------------------------------------------------------------------
# Validator façade
# ---------------------------------------------------------------------------


def validate(project: Project, registry: Registry) -> list[str]:
    """Return human-readable issue messages; empty list = valid.

    Back-compat shim over `run_validator_pipeline` — applies the same
    default pipeline and surfaces unfixable issues as a flat list of
    strings. Callers that want the fix log or the per-pass breakdown
    should use `run_validator_pipeline` directly.
    """
    result = run_validator_pipeline(project, registry)
    return list(result.issues)


def run_validator_pipeline(project: Project, registry: Registry) -> PipelineResult:
    """Run the default specialized-validator pipeline (Step 54).

    Returns the (possibly mutated) project along with the list of
    auto-applied fixes and any unfixable issues. The retry loop only
    feeds `issues` back to the LLM; `fixes` are surfaced separately so
    the user can see what the pipeline corrected on their behalf.
    """
    return run_pipeline(project, registry, default_passes())


# ---------------------------------------------------------------------------
# Retry loop
# ---------------------------------------------------------------------------


def generate_validated_timeline(
    prompt: str,
    registry: Registry,
    config: LLMConfig | None = None,
    *,
    max_attempts: int = 3,
    mock_responses: Sequence[str] | None = None,
) -> Project:
    """Generate a `Project`, feeding validation errors back to the model on failure.

    Each attempt re-prompts the model with the prior attempt's errors. Returns
    the first `Project` that passes both Pydantic and semantic validation.

    Raises `TimelineGenerationError` when `max_attempts` is exhausted without
    success. `mock_responses` is for offline tests: a list of canned model
    outputs, one per attempt.
    """
    last_feedback: list[str] = []

    for attempt in range(max_attempts):
        mock = (
            mock_responses[attempt]
            if mock_responses is not None and attempt < len(mock_responses)
            else None
        )

        attempt_prompt = prompt
        if last_feedback:
            joined = "\n".join(f"- {m}" for m in last_feedback)
            attempt_prompt = (
                f"{prompt}\n\n"
                f"# Errors from your previous attempt — fix all of these and try again:\n{joined}"
            )

        try:
            project = generate_timeline(attempt_prompt, registry, config=config, mock_response=mock)
        except ValidationError as e:
            last_feedback = [
                f"output did not match schema: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}"
            ]
            continue
        except ValueError as e:
            last_feedback = [f"output was not valid JSON: {e}"]
            continue

        pipeline_result = run_validator_pipeline(project, registry)
        # Use the (possibly auto-fixed) project — dialog_companion may
        # have attached look_at defaults, for example.
        project = pipeline_result.project
        if not pipeline_result.issues:
            return project
        last_feedback = pipeline_result.issues

    raise TimelineGenerationError(attempts=max_attempts, last_feedback=last_feedback)


__all__ = [
    "TimelineGenerationError",
    "generate_validated_timeline",
    "run_validator_pipeline",
    "validate",
]
