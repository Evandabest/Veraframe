"""Specialized validator pipeline (Step 54).

Each `ValidatorPass` owns one concern: reference resolution, beat
coherence, dialog companion checks, etc. The pipeline runs them in a
fixed order. Each pass either:

- **Fixes** the timeline locally (returning a mutated Project + the
  fixes it applied, so they can be reported), or
- **Flags** unfixable issues that surface to the retry loop and get
  fed back to the LLM as targeted feedback.

This is NOT an agent: there's no LLM in the loop between passes, the
order is fixed, and every pass is pure Python with deterministic
behavior. Closer to compiler passes than to tool use.

Add a new pass:
    1. Drop a module under `planner/validators/<name>.py` exporting a
       `pass_(project, registry) -> PassResult`.
    2. Register it in `DEFAULT_PIPELINE` below in the order it should run.
    3. Add tests under `tests/test_validator_<name>.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from planner.registry import Registry
from planner.schema import Project


@dataclass
class PassResult:
    """Output of a single validator pass.

    `project` is the (possibly-mutated) Project the next pass receives.
    `fixes` describe deterministic corrections the pass made — purely
    informational, surfaced to the user in render logs. `issues` are
    unfixable problems that get fed back to the LLM via the retry loop.
    """

    project: Project
    fixes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Aggregated output of running the full pipeline."""

    project: Project
    fixes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    # Name -> result for the per-pass breakdown (useful in debug logs / tests).
    per_pass: dict[str, PassResult] = field(default_factory=dict)


# A pass is just `(project, registry) -> PassResult`. We use a callable
# type instead of a Protocol so closures and module-level functions
# both work without ceremony.
ValidatorPass = Callable[[Project, Registry], PassResult]


def run_pipeline(
    project: Project, registry: Registry, passes: list[tuple[str, ValidatorPass]]
) -> PipelineResult:
    """Run every pass in order, threading the project through.

    Each pass sees the project as fixed by the previous passes — so a
    pass that depends on resolved references can run after the resolver.
    """
    aggregated_fixes: list[str] = []
    aggregated_issues: list[str] = []
    per_pass: dict[str, PassResult] = {}

    current = project
    for name, pass_fn in passes:
        result = pass_fn(current, registry)
        current = result.project
        per_pass[name] = result
        aggregated_fixes.extend(f"[{name}] {f}" for f in result.fixes)
        aggregated_issues.extend(f"[{name}] {i}" for i in result.issues)

    return PipelineResult(
        project=current,
        fixes=aggregated_fixes,
        issues=aggregated_issues,
        per_pass=per_pass,
    )


# Lazy import inside the function to avoid a circular import: the pass
# modules import from this `__init__.py` for the dataclasses.
def default_passes() -> list[tuple[str, ValidatorPass]]:
    """The standard pipeline order. Update when adding a new pass."""
    from planner.validators import (
        beat_coherence,
        channel_conflicts,
        dialog_companion,
        reference_autofix,
        reference_check,
    )

    return [
        # 1. Snap close-but-wrong references to the nearest valid name —
        #    catches LLM near-misses like "doorway" → "door" without
        #    burning a retry round.
        ("reference_autofix", reference_autofix.run),
        # 2. Hard reference resolution. Anything still broken after
        #    autofix surfaces as an issue for the LLM retry loop.
        ("reference_check", reference_check.run),
        # 3. Channel conflicts (overlap detection on the same body channel).
        ("channel_conflicts", channel_conflicts.run),
        # 4. Dialog companion — adds a default look_at to long talks.
        ("dialog_companion", dialog_companion.run),
        # 5. Beat coherence — warns about empty shots.
        ("beat_coherence", beat_coherence.run),
    ]


__all__ = [
    "DEFAULT_PIPELINE",
    "PassResult",
    "PipelineResult",
    "ValidatorPass",
    "default_passes",
    "run_pipeline",
]
