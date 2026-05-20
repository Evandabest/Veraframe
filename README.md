# Veraframe

A natural-language animation compiler for Blender. Veraframe converts plain English scene descriptions into editable animated Blender videos using a structured timeline, reusable character actions, and (in future) generated character voices.

## Status

Early development. Not yet usable.

## Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Blender 4.2+ (set `BLENDER_PATH` env var if not on `$PATH`; macOS default `/Applications/Blender.app/Contents/MacOS/Blender` is auto-detected)
- FFmpeg on `$PATH` or `FFMPEG_PATH` env var (Blender's macOS build ships without it; install via `brew install ffmpeg`)
- An LLM provider account (OpenAI, Anthropic, Gemini) or a local model via Ollama

## Setup

```bash
uv sync
uv run pytest
```

## License

TBD.
