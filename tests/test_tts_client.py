"""Tests for the TTS client (planner/tts_client.py).

The OpenAI call itself is network-bound and not exercised here — those would
go behind a `TTS_INTEGRATION=1` gate parallel to BLENDER_AVAILABLE. What we
test:
- TTSConfig env-var defaults and overrides
- Provider rejection for unknown providers
- Empty-text rejection
- WAV duration computation from a synthesized header (no network needed)
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from planner.tts_client import (
    TTSConfig,
    TTSError,
    _wav_duration_seconds,
    synthesize,
)


def test_config_default_values() -> None:
    cfg = TTSConfig()
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o-mini-tts"
    assert cfg.voice == "alloy"


def test_config_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERAFRAME_TTS_PROVIDER", "openai")
    monkeypatch.setenv("VERAFRAME_TTS_MODEL", "tts-1-hd")
    monkeypatch.setenv("VERAFRAME_TTS_VOICE", "nova")
    cfg = TTSConfig.from_env()
    assert cfg.model == "tts-1-hd"
    assert cfg.voice == "nova"


def test_synthesize_rejects_empty_text(tmp_path: Path) -> None:
    with pytest.raises(TTSError, match="empty"):
        synthesize("", tmp_path / "out.wav")


def test_synthesize_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(TTSError, match="unsupported TTS provider"):
        synthesize(
            "hello",
            tmp_path / "out.wav",
            config=TTSConfig(provider="elevenlabs"),
        )


def test_wav_duration_one_second(tmp_path: Path) -> None:
    # Hand-roll a tiny WAV: 24000 Hz, 1 channel, 16-bit, 1 second.
    path = tmp_path / "one_second.wav"
    sample_rate = 24000
    n_frames = sample_rate
    silence = struct.pack("<h", 0) * n_frames
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(silence)
    assert abs(_wav_duration_seconds(path) - 1.0) < 0.001


def test_wav_duration_rejects_non_wav(tmp_path: Path) -> None:
    bad = tmp_path / "not_a_wav.bin"
    bad.write_bytes(b"not actually a wav file")
    with pytest.raises(TTSError):
        _wav_duration_seconds(bad)
