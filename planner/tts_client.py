"""Text-to-speech client for the `talk` action.

Synthesizes a string of dialogue into a WAV file and returns its duration in
seconds so the orchestrator can plan placement on the timeline. The provider
and voice are env-configurable; OpenAI's TTS API is the default because it
has the simplest auth (single `OPENAI_API_KEY`) and reasonable quality on
the free tier.

The output is a 24 kHz 16-bit mono WAV. We use that container (rather than
the smaller MP3 default) because ffmpeg's later mux step handles it without
re-encoding decisions, and Blender's audio import (for future viseme-from-
audio work) prefers uncompressed PCM.

Provider selection mirrors `LLMConfig.from_env`:

    VERAFRAME_TTS_PROVIDER   default: openai
    VERAFRAME_TTS_MODEL      default: gpt-4o-mini-tts
    VERAFRAME_TTS_VOICE      default: alloy
    OPENAI_API_KEY           required for the openai provider
"""

from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when TTS synthesis fails."""


@dataclass(frozen=True)
class TTSConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini-tts"
    voice: str = "alloy"

    @classmethod
    def from_env(cls) -> "TTSConfig":
        return cls(
            provider=os.getenv("VERAFRAME_TTS_PROVIDER", cls.provider),
            model=os.getenv("VERAFRAME_TTS_MODEL", cls.model),
            voice=os.getenv("VERAFRAME_TTS_VOICE", cls.voice),
        )


@dataclass(frozen=True)
class TTSResult:
    output_path: Path
    duration_s: float
    provider: str
    voice: str


def synthesize(text: str, output_path: str | Path, config: TTSConfig | None = None) -> TTSResult:
    """Generate spoken audio for `text`, write to `output_path` (WAV), return metadata.

    Raises `TTSError` if the configured provider is unavailable, the API key
    is missing, or the upstream call fails. The caller is responsible for
    placing the resulting WAV onto the render's audio track.
    """
    cfg = config or TTSConfig.from_env()
    out_path = Path(output_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not text or not text.strip():
        raise TTSError("text is empty")

    if cfg.provider == "openai":
        _synthesize_openai(text=text, model=cfg.model, voice=cfg.voice, output_path=out_path)
    else:
        raise TTSError(f"unsupported TTS provider '{cfg.provider}' (expected: openai)")

    duration = _wav_duration_seconds(out_path)
    return TTSResult(
        output_path=out_path,
        duration_s=duration,
        provider=cfg.provider,
        voice=cfg.voice,
    )


def _synthesize_openai(*, text: str, model: str, voice: str, output_path: Path) -> None:
    """Call OpenAI's TTS endpoint and write the WAV body to disk."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise TTSError(
            "OPENAI_API_KEY is not set; the openai TTS provider needs it. "
            "Either set the key or change VERAFRAME_TTS_PROVIDER."
        )

    try:
        # Use the openai SDK if it's already in the dependency tree (it is —
        # litellm pulls it). Direct SDK keeps us away from LiteLLM's audio
        # surface, which is less stable than its chat surface.
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as e:
        raise TTSError(f"openai package missing: {e}") from e

    client = OpenAI(api_key=api_key)
    try:
        with client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            response_format="wav",
        ) as response:
            response.stream_to_file(str(output_path))
    except Exception as e:  # noqa: BLE001 — surfaces upstream errors uniformly
        raise TTSError(f"openai TTS call failed: {e}") from e


def _wav_duration_seconds(path: Path) -> float:
    """Read a WAV file's header to compute its playback duration."""
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            if rate <= 0:
                raise TTSError(f"wav file has zero framerate: {path}")
            return frames / float(rate)
    except wave.Error as e:
        raise TTSError(f"could not read wav at {path}: {e}") from e


__all__ = ["TTSConfig", "TTSError", "TTSResult", "synthesize"]
