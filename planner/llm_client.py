"""LLM client — provider-agnostic timeline generation via LiteLLM.

This module performs the single positive-path call: prompt + registry in, a
syntactically-valid `Project` out. Semantic validation against the registry
(does the chosen scene actually have that spawn point? does that character
exist?) and the retry-with-feedback loop live in `planner.validator`.
"""

import os
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
- Declare every character you reference up front in the project's `characters` array. Each character's `spawn` must be one of the chosen scene's spawn points.
- Inside actions, the `target` and `look_at` fields must refer either to one of the chosen scene's spawn points or to another declared character's `id`.
- `camera`, `from_camera`, and `to_camera` must each be one of the chosen scene's camera presets.
- `preset` in `set_lighting` must be one of the chosen scene's lighting presets.
- All times are absolute seconds. Every action's `end` must be greater than its `start`. Action timestamps must fit within the parent shot's window.
- Use only action types from the available actions list. Respect each action's required and optional parameters.
- Use only the listed emotion values: neutral, joy, angry, sorrow, fun.
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
    return Project.model_validate_json(content)


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "LLMConfig",
    "build_system_prompt",
    "generate_timeline",
]
