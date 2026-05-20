"""Tests for `planner.llm_client` — system-prompt building, config, and mocked completion."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from planner.llm_client import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    LLMConfig,
    build_system_prompt,
    generate_timeline,
)
from planner.registry import Registry
from planner.schema import Project


@pytest.fixture
def registry() -> Registry:
    return Registry.load(Path("assets"))


@pytest.fixture
def valid_timeline_dict() -> dict:
    return {
        "project": "test",
        "scene": "dark_lab",
        "characters": [{"id": "student", "preset": "student_v1", "spawn": "door"}],
        "shots": [
            {
                "id": "shot_001",
                "start": 0,
                "end": 2,
                "camera": "wide",
                "actions": [
                    {
                        "id": "a1",
                        "type": "idle",
                        "character": "student",
                        "start": 0,
                        "end": 2,
                    }
                ],
            }
        ],
    }


# --- LLMConfig ----------------------------------------------------------------


def test_config_defaults() -> None:
    cfg = LLMConfig()
    assert cfg.provider == DEFAULT_PROVIDER
    assert cfg.model == DEFAULT_MODEL


def test_config_from_env_reads_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERAFRAME_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("VERAFRAME_LLM_MODEL", "claude-opus-4-7")
    cfg = LLMConfig.from_env()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-4-7"


def test_config_from_env_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERAFRAME_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VERAFRAME_LLM_MODEL", raising=False)
    cfg = LLMConfig.from_env()
    assert cfg.provider == DEFAULT_PROVIDER
    assert cfg.model == DEFAULT_MODEL


def test_model_string_prepends_provider_when_missing() -> None:
    assert LLMConfig(provider="openai", model="gpt-4o").model_string == "openai/gpt-4o"


def test_model_string_keeps_explicit_prefix() -> None:
    cfg = LLMConfig(provider="openai", model="anthropic/claude-opus-4-7")
    assert cfg.model_string == "anthropic/claude-opus-4-7"


# --- build_system_prompt ------------------------------------------------------


def test_system_prompt_includes_registry_sections(registry: Registry) -> None:
    prompt = build_system_prompt(registry)
    assert "# Available scenes" in prompt
    assert "# Available characters" in prompt
    assert "# Available actions" in prompt
    assert "dark_lab" in prompt
    assert "student_v1" in prompt


def test_system_prompt_includes_output_rules(registry: Registry) -> None:
    prompt = build_system_prompt(registry)
    assert "# Output rules" in prompt
    assert "absolute seconds" in prompt
    assert "neutral, joy, angry, sorrow, fun" in prompt


# --- generate_timeline with mock_response -------------------------------------


def test_generate_timeline_parses_mock_response(
    registry: Registry, valid_timeline_dict: dict
) -> None:
    result = generate_timeline(
        "a student stands in the lab",
        registry,
        mock_response=json.dumps(valid_timeline_dict),
    )
    assert isinstance(result, Project)
    assert result.scene == "dark_lab"
    assert result.shots[0].actions[0].type == "idle"


def test_generate_timeline_raises_on_invalid_json(registry: Registry) -> None:
    with pytest.raises(ValueError):
        generate_timeline(
            "anything",
            registry,
            mock_response="not even json {",
        )


def test_generate_timeline_raises_on_schema_violation(registry: Registry) -> None:
    bad = json.dumps(
        {
            "project": "test",
            "scene": "dark_lab",
            "characters": [],
            "shots": [
                {
                    "id": "shot_001",
                    "start": 0,
                    "end": 2,
                    "camera": "wide",
                    "actions": [
                        {
                            "id": "a1",
                            "type": "walk_to",
                            # missing required `character` and `target`
                            "start": 0,
                            "end": 2,
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        generate_timeline("anything", registry, mock_response=bad)


def test_generate_timeline_uses_supplied_config(
    registry: Registry, valid_timeline_dict: dict
) -> None:
    # Just confirms a config can be passed and the call still works under mock.
    cfg = LLMConfig(provider="anthropic", model="claude-opus-4-7")
    result = generate_timeline(
        "anything",
        registry,
        config=cfg,
        mock_response=json.dumps(valid_timeline_dict),
    )
    assert isinstance(result, Project)
