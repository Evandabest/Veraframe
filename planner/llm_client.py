"""LLM client — provider-agnostic timeline generation via LiteLLM.

This module performs the single positive-path call: prompt + registry in, a
syntactically-valid `Project` out. Semantic validation against the registry
(does the chosen scene actually have that spawn point? does that character
exist?) and the retry-with-feedback loop live in `planner.validator`.
"""

import os
import sys
from dataclasses import dataclass

import litellm

from planner.registry import Registry
from planner.schema import Project

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o"


@dataclass(frozen=True)
class LLMConfig:
    """Provider/model configuration. Defaults to OpenAI GPT-4o."""

    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    temperature: float = 0.2

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            provider=os.getenv("VERAFRAME_LLM_PROVIDER", DEFAULT_PROVIDER),
            model=os.getenv("VERAFRAME_LLM_MODEL", DEFAULT_MODEL),
        )

    @property
    def model_string(self) -> str:
        """LiteLLM model identifier (e.g. `openai/gpt-4o`).

        Ollama gets routed through the chat endpoint (`ollama_chat/`) since
        we send role-tagged messages; the generic `ollama/` prefix uses the
        text-completion endpoint and silently ignores the chat structure.
        """
        if "/" in self.model:
            return self.model
        if self.provider == "ollama":
            return f"ollama_chat/{self.model}"
        return f"{self.provider}/{self.model}"


SYSTEM_PROMPT_TEMPLATE = """You are Veraframe, a system that converts natural-language scene descriptions into structured timelines for a Blender animation engine.

You will output a JSON object that conforms exactly to the provided schema. Do not include any fields the schema does not define. Pick scene IDs, character IDs, spawn point names, camera preset names, and action types only from the lists below.

{registry_section}

# Output rules

- Choose exactly one scene from the available scenes list.
- Declare every character you reference up front in the project's `characters` array.
- **Each entry in `characters` has three required fields and they mean different things — keep them distinct:**
  - `id`: a short role handle you choose freely. Used by actions to refer to this character. Do NOT use a preset id, scene id, or camera name as a handle.
  - `preset`: must be exactly one of the entries in the "Available characters" section above. This is the asset that gets loaded.
  - `spawn`: must be exactly one of the chosen scene's spawn points.
- Inside actions, the `character` field, plus `target` and `look_at` when they point at another character, must use the handle from `id`, NOT the preset id.
- Each shot needs `id` (a string you choose, e.g. "shot_001"), `start`, `end`, and `camera`. The shot's `camera` must be one of the chosen scene's camera presets.
- `from_camera` and `to_camera` (in `camera_dolly`) must each be one of the chosen scene's camera presets.
- `preset` in `set_lighting` must be one of the chosen scene's lighting presets — distinct from character presets and camera presets.
- All times are absolute seconds. Every action's `end` must be greater than its `start`. Action timestamps must fit within the parent shot's window.
- Use only action types from the available actions list. Respect each action's required and optional parameters.
- Use only the listed emotion values: neutral, joy, angry, sorrow, fun.

# Concurrent actions per character

A character can do multiple things at once. Different action types live on different channels:

- **Body channel** (only one at a time per character): `walk_to`, `idle`, `turn_to`, `sit`, `stand`, `play_clip`. Overlap two of these on the same character and the validator rejects the timeline.
- **Talk channel**: `talk`. Independent of the body — a character can `walk_to` and `talk` at the same time. Prefer this over splitting into two shots when the dialog naturally happens while moving.
- **Head channel**: `look_at`. Independent of body and talk — a character can `walk_to` AND `talk` AND `look_at` another character simultaneously.
- **Face channel**: `smile`, `frown`, `blink`. Independent of body / talk / head — a smile can overlap any of them.
- **Right-arm / left-arm gestures**: `wave`, `point_at` drive a single arm. They layer over `walk_to` / `idle` cleanly (pose-keyframe overrides win on the gesture's bones). The default arm is right; set `bone_mask=["left_arm"]` to use the left.
- **Head gestures**: `nod`, `shake_head` drive only the head bone — safe over walk_to / idle / talk simultaneously.

Use concurrency to compose richer beats. Examples:
- *"alice walks to the door and says hi to bob"* → one shot, concurrent `walk_to` + `talk` + (auto) `look_at(bob)` on alice.
- *"the student waves while walking in"* → `walk_to` + `wave` overlapping (the wave's right-arm keyframes override the walk cycle's right arm).
- *"she nods at the robot while smiling"* → `nod` + `smile` + `look_at(robot)`, all overlapping, all on the same character.

Do not stack two actions on the same channel for the same character at the same time. If the user asks for two gestures on the same arm at once, give one of them a `bone_mask` override so they target different limbs.

# Seated state and the sit → stand pairing

`sit` puts the character into a seated pose AND drops the body to seated hip height; that pose is held automatically after the action ends, until a matching `stand` lifts them back up. So:

- If the user says *"stays sitting"* / *"remains seated"* / *"is still at her desk"* after a previous `sit`, emit ANOTHER `sit` action covering the new window (NOT `idle` — `idle` would override the seated pose with a standing one and the character would visibly pop up). Repeated `sit` actions compose correctly.
- Only emit `stand` when the user actually wants the character to get back up.
- If a scene starts with the character already seated and the user wants them to remain so for the duration, the first action on that character should be a `sit` covering the relevant window.
- Conversely, after a `stand` or for a never-seated character, default body coverage is `idle`.

**Critical: every string value you emit must be either a value from the "Available …" sections above, a handle you invented for the `id` field of a character or shot, or a free text field (like `text` in `talk`). Never emit angle-bracketed placeholders, ALL CAPS slot names, or words from the rules above.**
"""


def build_system_prompt(registry: Registry) -> str:
    """Compose the LLM system prompt from a registry."""
    return SYSTEM_PROMPT_TEMPLATE.format(registry_section=registry.to_system_prompt_section())


def generate_timeline(
    prompt: str,
    registry: Registry,
    config: LLMConfig | None = None,
    *,
    mock_response: str | None = None,
) -> Project:
    """Generate a structured `Project` timeline from a natural-language prompt.

    The model is asked to emit JSON matching the `Project` schema. The result
    is parsed and Pydantic-validated; structural errors raise
    `pydantic.ValidationError`. Semantic validation (registry membership,
    cross-references) is layered in `planner.validator`.

    `mock_response`, when provided, short-circuits the network call and feeds
    the given string into LiteLLM's mock-completion path. Used in tests.
    """
    config = config or LLMConfig.from_env()

    response = litellm.completion(
        model=config.model_string,
        messages=[
            {"role": "system", "content": build_system_prompt(registry)},
            {"role": "user", "content": prompt},
        ],
        response_format=Project,
        temperature=config.temperature,
        mock_response=mock_response,
    )

    content = response.choices[0].message.content
    # Mirror the raw LLM output to stderr so the Electron app's [planner]
    # forwarder shows it in the terminal. Helpful for debugging when the
    # model emits malformed JSON the validator then retries.
    print(f"[llm_client] response from {config.model_string}:", file=sys.stderr)
    print(content, file=sys.stderr)
    return Project.model_validate_json(content)


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "LLMConfig",
    "build_system_prompt",
    "generate_timeline",
]
