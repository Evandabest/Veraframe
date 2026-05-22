# Veraframe

A natural-language animation compiler for Blender. Veraframe converts plain-English scene descriptions into editable, rendered videos using a structured timeline, reusable character actions, and a desktop GUI for previewing and refining each block.

![Veraframe desktop app](docs/app-screenshot.png)

## Status

The MVP is feature-complete and runs as an Electron desktop app over a long-lived Blender daemon. Cloud LLMs (OpenAI / Anthropic / Gemini) and local Ollama models are all supported. The timeline is interactive: you can scrub the video, click any action block to re-prompt it, or `+` past the end of the video to extend it — both edits and extensions render only the changed window and ffmpeg-splice or -append the result into the existing MP4 so iterations stay fast.

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
  │                                              point_at, sit, stand,
  │                                              turn_to, smile, frown,
  │                                              blink, talk, camera_cut,
  │                                              camera_dolly, set_lighting)
  ▼
PNG sequence ─ Blender mp4 ──────►   per-render slice
  │
  ▼
ffmpeg concat / splice  ◄─ (incremental: edits + extensions)
  │
  ▼
out.mp4
```

## Quick start

```bash
# 1. Python deps
uv sync

# 2. Node deps (Electron app)
npm --prefix app install

# 3. Run the desktop app (Electron + Vite + Python daemon supervisor)
npm --prefix app run dev
```

The Render button runs end-to-end (LLM → daemon → ffmpeg). **Mock** mode loads a pre-baked MP4 + timeline from `assets/fixtures/` so you can exercise the timeline editor without a 60-second wait per render.

## Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for Python deps
- Node 20+ and npm for the Electron app
- Blender 5.x (`BLENDER_PATH` env var if not on `$PATH`; macOS `/Applications/Blender.app/...` is auto-detected)
- FFmpeg on `$PATH` (`brew install ffmpeg`) — used for incremental render merges
- One of:
  - OpenAI / Anthropic / Gemini API key (export `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`)
  - **Ollama** running locally — the UI auto-detects installed models via `GET /api/tags`

## Editing the timeline

Once a render finishes, the timeline below the video is fully interactive:

| Interaction | What it does |
|---|---|
| Click anywhere on a lane / ruler | Seek the video to that point |
| Click + drag | Scrub-seek smoothly (rAF-driven, 60Hz playhead) |
| Click an action block | Open the editor; re-prompt the action via the LLM, see a green diff overlay on the timeline, **Accept** to re-render just that window, **Reject** to keep the original |
| Click `+` at the end of a lane | Add a new action. If past the current end, the timeline **extends** and ffmpeg appends the rendered tail onto the existing MP4 |
| Click ✨ Enhance in either textarea | Rewrite the prompt using actual asset names from the registry (same provider/model as render) |
| `+` Character | Stub — reserved for adding a second character mid-edit (not wired up yet) |

The incremental render strategy:
- **Edit** existing block → `ffmpeg` splices the new slice in at `[action.start, action.end]`
- **Extend** past current end → `ffmpeg` appends the new tail
- **First render of the session** → full render (no previous video to merge into)

## Developer CLI

The same Python pipeline is available headless for tests and one-off renders. The CLI is gated behind `--dev` so the Electron build can ship the same binary without exposing internals.

```bash
# Mock render (canned timeline, no LLM)
uv run veraframe --dev render --mock --out /tmp/out.mp4

# Prompt render (uses the LLM)
export OPENAI_API_KEY=...           # or ANTHROPIC_API_KEY / GEMINI_API_KEY
uv run veraframe --dev render \
  "the student walks to the center of the lab, smiles, then walks to the robot" \
  --out /tmp/out.mp4

# Switch provider/model via env vars
VERAFRAME_LLM_PROVIDER=ollama VERAFRAME_LLM_MODEL=llama3.1 \
  uv run veraframe --dev render "..." --out /tmp/out.mp4
```

## Repository layout

```
planner/          LLM client, schema, validator, registry, dev CLI
  ├─ schema.py            Pydantic timeline types
  ├─ validator.py         retry-with-feedback loop
  ├─ llm_client.py        LiteLLM wrapper, system prompt
  ├─ run_planner.py       full-timeline subprocess entrypoint
  ├─ run_action.py        single-action subprocess entrypoint (block edits)
  └─ run_enhance.py       prompt-rewrite subprocess entrypoint

blender_daemon/   JSON-RPC server inside `blender --background`
actions/          Per-action implementations executed inside Blender

app/              Electron + React + Tailwind desktop GUI
  ├─ src/main/            Electron main: daemon supervisor, render orchestration, ffmpeg splice/append
  ├─ src/preload/         IPC bridge
  └─ src/renderer/        React UI (App, TimelinePanel, ActionEditor)

assets/
  scenes/         dark_lab/, classroom/        (programmatic + .blend)
  characters/     student_v1/, robot_v1/       (Mixamo X-Bot)
  animations/     idle/, walk_in_place/        (Mixamo)
  fixtures/       mock-classroom.mp4 + .json   (pre-baked demo content)

tests/            Unit tests + Blender integration tests (BLENDER_AVAILABLE=1)
docs/             Screenshots, design notes
```

## Supported actions

| action          | what it does                                                              |
|-----------------|---------------------------------------------------------------------------|
| `walk_to`       | Walk-in-place strip + translation curve to a named spawn point            |
| `idle`          | Mixamo idle NLA strip                                                     |
| `turn_to`       | Rotate the character to face a target spawn point / character             |
| `look_at`       | Damped-track head-bone constraint, influence keyframed on/off             |
| `point_at`      | Arm IK pointing at a target                                               |
| `sit` / `stand` | Pose transitions                                                          |
| `smile`         | `Joy` blendshape ramp (no-op on characters without the key)               |
| `frown`         | `Sorrow` blendshape ramp                                                  |
| `blink`         | `Blink` shape-key pulse                                                   |
| `talk`          | Viseme distribution from a text string (audio TTS planned)                |
| `camera_cut`    | Bind a named camera preset to a timeline marker                           |
| `camera_dolly`  | Interpolate between two camera presets                                    |
| `set_lighting`  | Switch to a named lighting preset on the active scene                     |

## Tests

```bash
uv sync
uv run pytest                       # unit tests, no Blender required
BLENDER_AVAILABLE=1 uv run pytest   # also run integration tests against a real Blender
```

The Electron app uses TypeScript everywhere:

```bash
npm --prefix app run typecheck
npm --prefix app run build
```

## Architecture notes

- **Blender stays daemon-resident.** Cold-starting Blender is ~5s; we keep it running and send JSON-RPC calls (`load_scene`, `load_character`, `execute_timeline`, `render`) over a local socket.
- **The planner is a subprocess.** Electron's main process spawns `uv run python -m planner.*` per LLM call — no in-process Python. Lets us swap models/providers per-request via env vars.
- **Incremental render relies on full setup, partial rendering.** Each edit still runs `load_scene` + `load_character` + `execute_timeline` (~10-20s) to put Blender in the right state, but only renders the changed frame range. ffmpeg merges that slice into the previous MP4.
- **Mock mode is a pure fixture.** No Blender, no LLM — just reads `assets/fixtures/mock-classroom.{mp4,json}` and registers the file under the custom `veraframe-render://` protocol so the existing player and editor pipeline works.

## License

TBD.
