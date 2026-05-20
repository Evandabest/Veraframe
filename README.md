# Veraframe

A natural-language animation compiler for Blender. Veraframe converts plain English scene descriptions into editable animated Blender videos using a structured timeline, reusable character actions, and (in future) generated character voices.

## Status

Early development. Not yet usable.

## Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Blender 4.2+ on `$PATH`
- An LLM provider account (OpenAI, Anthropic, Gemini) or a local model via Ollama

## Setup

```bash
uv sync
uv run pytest
```

## License

TBD.
