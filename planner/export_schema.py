"""Emit the timeline JSON Schema as a JSON file.

The renderer side consumes this via `json-schema-to-typescript` to produce
`app/shared/schema.ts`, and the LLM provider consumes it via its native
structured-output API (`response_format: json_schema` etc.).

Usage:

    uv run python -m planner.export_schema --output app/shared/schema.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from planner.schema import Project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="planner.export_schema")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the JSON Schema file.",
    )
    args = parser.parse_args(argv)

    schema = Project.model_json_schema()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
