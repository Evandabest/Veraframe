"""Stdout entrypoint that synthesizes dialogue audio for a `talk` action.

The Electron app calls this once per talk action just before kicking off
the Blender render — TTS lives outside the daemon so the daemon stays
single-threaded on Blender ops and so we can reuse the existing
subprocess-per-call pattern (mirrors `run_planner.py`, `run_action.py`).

Usage:

    uv run python -m planner.run_tts \\
        --text "Hello, world." \\
        --out /tmp/dialogue_001.wav

Stdout: JSON `{output_path, duration_s, provider, voice}`.
Stderr: free-form progress.
"""

from __future__ import annotations

import argparse
import json
import sys

from planner.tts_client import TTSConfig, TTSError, synthesize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="planner.run_tts")
    parser.add_argument("--text", required=True, help="Dialogue text to synthesize.")
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the WAV file (parent dirs are created).",
    )
    args = parser.parse_args(argv)

    config = TTSConfig.from_env()
    print(
        f"tts via {config.provider}:{config.model} voice={config.voice}",
        file=sys.stderr,
    )

    try:
        result = synthesize(args.text, args.out, config=config)
    except TTSError as e:
        print(f"tts error: {e}", file=sys.stderr)
        return 1

    json.dump(
        {
            "output_path": str(result.output_path),
            "duration_s": result.duration_s,
            "provider": result.provider,
            "voice": result.voice,
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
