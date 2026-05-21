# Veraframe

A natural-language animation compiler for Blender. Veraframe converts plain English scene descriptions into editable animated Blender videos using a structured timeline, reusable character actions, and (in future) generated character voices.

## Status

The core pipeline runs end-to-end: prompt → LLM-generated JSON timeline → Pydantic validation → Blender daemon execution → MP4. The Electron GUI is not built yet; use the developer CLI for now.

## Pipeline

```
prompt
  │
  ▼
LLM (LiteLLM)                       planner/
  │
  ▼
JSON timeline ── Pydantic validate ─ planner/schema.py + validator.py
  │
  ▼
Blender daemon (JSON-RPC over TCP)   blender_daemon/
  │
  ▼
NLA strips · constraints · markers   actions/ (idle, walk_to, look_at,
  │                                              smile, frown, blink,
  │                                              camera_cut)
  ▼
PNG sequence ─ ffmpeg ─► out.mp4    blender_daemon/render_manager.py
```

## Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Blender 5.x (set `BLENDER_PATH` env var if not on `$PATH`; macOS default `/Applications/Blender.app/Contents/MacOS/Blender` is auto-detected)
- FFmpeg on `$PATH` or `FFMPEG_PATH` env var (Blender's macOS build ships without it; install via `brew install ffmpeg`)
- An LLM provider account (OpenAI, Anthropic, Gemini) or a local model via Ollama — only needed for non-mock renders

## Setup

```bash
uv sync
uv run pytest                       # unit tests, no Blender
BLENDER_AVAILABLE=1 uv run pytest   # also run real-Blender integration tests
```

## Developer CLI

The CLI is gated behind `--dev` so the eventual end-user app (Electron) can ship the same binary without exposing internals.

**Mock render** — no LLM call, hand-written one-action timeline:

```bash
uv run veraframe --dev render --mock --out /tmp/out.mp4
```

**Full prompt render** — calls the configured LLM provider:

```bash
export OPENAI_API_KEY=...           # or ANTHROPIC_API_KEY, etc.
uv run veraframe --dev render \
  "the student walks to the center of the lab, smiles, then walks to the robot" \
  --out /tmp/out.mp4
```

## Repository layout

```
planner/          LLM client, schema, validator, registry, dev CLI, daemon runner
blender_daemon/   JSON-RPC server inside `blender --background`; loaders + render manager
actions/          Action implementations executed inside Blender
assets/
  scenes/         dark_lab/                 (programmatic + .blend)
  characters/     student_v1/               (Mixamo X-Bot)
  animations/     idle/, walk_in_place/     (Mixamo)
tests/            Unit tests + Blender integration tests (BLENDER_AVAILABLE=1)
```

## Supported actions

| action       | what it does                                                              |
|--------------|---------------------------------------------------------------------------|
| `idle`       | Place a Mixamo idle NLA strip on the character armature                   |
| `walk_to`    | Walk-in-place strip + custom translation curve to a named spawn point     |
| `look_at`    | Damped-track head bone constraint, influence keyframed on/off             |
| `smile`      | VRM `Joy` blendshape ramp (no-op on characters without the shape key)     |
| `frown`      | VRM `Sorrow` blendshape ramp                                              |
| `blink`      | VRM `Blink` shape-key pulse at action midpoint                            |
| `camera_cut` | Bind a named camera to a timeline marker; render resolves it per frame    |

## Architecture

Veraframe will ship as an Electron desktop app that supervises a long-lived Blender daemon over local TCP. The Python `planner/` package stays as the LLM + validator + registry, invoked by the Electron main process via subprocess-per-call.

## License

TBD.
