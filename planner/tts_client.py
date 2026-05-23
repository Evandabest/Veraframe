"""Text-to-speech client for the `talk` action.

Synthesizes a string of dialogue into an audio file and returns its duration
so the orchestrator can plan placement on the timeline.

Default provider is **Microsoft Edge TTS** (`edge-tts`) — it taps the same
backend the Edge browser uses for accessibility, returns MP3, and **needs no
API key or paid account**. The OpenAI provider is also wired (output: WAV)
for users who prefer it; switch via `VERAFRAME_TTS_PROVIDER=openai` and set
`OPENAI_API_KEY`.

Env knobs (all optional):

    VERAFRAME_TTS_PROVIDER   default: edge   (or: openai)
    VERAFRAME_TTS_VOICE      default depends on provider — see DEFAULT_VOICE.
    VERAFRAME_TTS_MODEL      only meaningful for openai (default: gpt-4o-mini-tts).

The output file's extension is determined by the provider (mp3 for edge,
wav for openai). The actual saved path is returned in `TTSResult.output_path`;
callers should use that, not the path they requested.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class TTSError(RuntimeError):
    """Raised when TTS synthesis fails."""


_DEFAULT_VOICES: dict[str, str] = {
    "edge": "en-US-AriaNeural",
    "openai": "alloy",
}


@dataclass(frozen=True)
class TTSConfig:
    provider: str = "edge"
    model: str = "gpt-4o-mini-tts"  # openai-only; ignored for edge
    voice: str = ""  # filled in from provider default if empty

    @classmethod
    def from_env(cls) -> "TTSConfig":
        provider = os.getenv("VERAFRAME_TTS_PROVIDER", "edge")
        voice = os.getenv("VERAFRAME_TTS_VOICE") or _DEFAULT_VOICES.get(provider, "")
        return cls(
            provider=provider,
            model=os.getenv("VERAFRAME_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=voice,
        )


@dataclass(frozen=True)
class TTSResult:
    output_path: Path
    duration_s: float
    provider: str
    voice: str


def synthesize(text: str, output_path: str | Path, config: TTSConfig | None = None) -> TTSResult:
    """Generate spoken audio for `text`, write to `output_path`, return metadata.

    Raises `TTSError` if the provider is unavailable, a key is missing, or
    the upstream call fails. The output's extension is normalized to match
    the provider's natural format (.mp3 for edge, .wav for openai); the
    actual saved path is in the returned `TTSResult`.
    """
    cfg = config or TTSConfig.from_env()
    if not cfg.voice:
        # Test paths that construct TTSConfig directly without specifying a
        # voice still get a working default per-provider.
        cfg = TTSConfig(provider=cfg.provider, model=cfg.model,
                        voice=_DEFAULT_VOICES.get(cfg.provider, "en-US-AriaNeural"))

    out_path = Path(output_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not text or not text.strip():
        raise TTSError("text is empty")

    if cfg.provider == "edge":
        # edge-tts produces MP3; rewrite the extension so callers don't have
        # to know the format up-front.
        if out_path.suffix.lower() != ".mp3":
            out_path = out_path.with_suffix(".mp3")
        _synthesize_edge(text=text, voice=cfg.voice, output_path=out_path)
    elif cfg.provider == "openai":
        if out_path.suffix.lower() != ".wav":
            out_path = out_path.with_suffix(".wav")
        _synthesize_openai(text=text, model=cfg.model, voice=cfg.voice, output_path=out_path)
    else:
        raise TTSError(
            f"unsupported TTS provider '{cfg.provider}' (expected: edge or openai)"
        )

    duration = _media_duration_seconds(out_path)
    return TTSResult(
        output_path=out_path,
        duration_s=duration,
        provider=cfg.provider,
        voice=cfg.voice,
    )


def _synthesize_edge(*, text: str, voice: str, output_path: Path) -> None:
    """Call Microsoft Edge TTS (no API key) and write MP3 to disk."""
    try:
        import edge_tts  # type: ignore[import-untyped]
    except ImportError as e:
        raise TTSError(f"edge-tts package missing: {e}") from e

    async def _do() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    try:
        asyncio.run(_do())
    except Exception as e:  # noqa: BLE001 — surfaces network / quota / voice errors
        raise TTSError(f"edge-tts call failed: {e}") from e


def _synthesize_openai(*, text: str, model: str, voice: str, output_path: Path) -> None:
    """Call OpenAI's TTS endpoint and write WAV to disk."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise TTSError(
            "OPENAI_API_KEY is not set; the openai TTS provider needs it. "
            "Use VERAFRAME_TTS_PROVIDER=edge to switch to the free Microsoft "
            "Edge TTS instead."
        )

    try:
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
    except Exception as e:  # noqa: BLE001
        raise TTSError(f"openai TTS call failed: {e}") from e


def _media_duration_seconds(path: Path) -> float:
    """Read a media file's duration via ffprobe.

    Works for both .mp3 (edge output) and .wav (openai output). ffprobe is
    bundled with ffmpeg which is already a hard dependency of the render
    pipeline, so no new install requirement.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return float(result.stdout.strip())
    except FileNotFoundError as e:
        raise TTSError(
            "ffprobe not found; install ffmpeg (brew install ffmpeg) to read "
            "audio duration."
        ) from e
    except (subprocess.SubprocessError, ValueError) as e:
        raise TTSError(f"could not read duration of {path}: {e}") from e


__all__ = ["TTSConfig", "TTSError", "TTSResult", "synthesize"]
