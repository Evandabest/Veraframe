"""Tests for the TTS client (planner/tts_client.py).

The actual network calls (edge-tts, openai) aren't exercised here — those
need real network + paid accounts. What we test:
- TTSConfig env-var defaults and overrides (per-provider voice defaults)
- Provider rejection for unknown providers
- Empty-text rejection
- ffprobe-driven duration reading (uses a known WAV to verify behavior)
- Output-path extension normalization (.mp3 for edge, .wav for openai)
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from planner.tts_client import (
    TTSConfig,
    TTSError,
    _media_duration_seconds,
    synthesize,
)


def test_config_default_provider_is_edge() -> None:
    cfg = TTSConfig.from_env()
    assert cfg.provider == "edge"
    # When provider is edge and no env override is set, the default voice
    # should be a Microsoft Neural one.
    assert cfg.voice == "en-US-AriaNeural"


def test_config_env_switches_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERAFRAME_TTS_PROVIDER", "openai")
    monkeypatch.delenv("VERAFRAME_TTS_VOICE", raising=False)
    cfg = TTSConfig.from_env()
    assert cfg.provider == "openai"
    assert cfg.voice == "alloy"  # openai default kicks in


def test_config_explicit_voice_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERAFRAME_TTS_PROVIDER", "edge")
    monkeypatch.setenv("VERAFRAME_TTS_VOICE", "en-GB-LibbyNeural")
    cfg = TTSConfig.from_env()
    assert cfg.voice == "en-GB-LibbyNeural"


def test_synthesize_rejects_empty_text(tmp_path: Path) -> None:
    with pytest.raises(TTSError, match="empty"):
        synthesize("", tmp_path / "out.wav")


def test_synthesize_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(TTSError, match="unsupported TTS provider"):
        synthesize(
            "hello",
            tmp_path / "out.wav",
            config=TTSConfig(provider="elevenlabs", voice="x"),
        )


def test_edge_provider_rewrites_extension_to_mp3(tmp_path: Path) -> None:
    """Even if the caller passes .wav, edge synthesis should land at .mp3."""
    captured: dict[str, Path] = {}

    def fake_synth_edge(*, text: str, voice: str, output_path: Path) -> None:
        captured["path"] = output_path
        # Drop a minimal MP3-like file so ffprobe doesn't blow up; it'll
        # error on the duration read, which the caller will surface as
        # TTSError — that's fine for verifying the extension rewrite.
        output_path.write_bytes(b"\xff\xfb\x90\x00")

    with patch("planner.tts_client._synthesize_edge", fake_synth_edge):
        try:
            synthesize(
                "hello",
                tmp_path / "out.wav",
                config=TTSConfig(provider="edge", voice="en-US-AriaNeural"),
            )
        except TTSError:
            # Expected — the fake file isn't a valid MP3, ffprobe fails.
            pass
    assert captured["path"].suffix == ".mp3"


def test_openai_provider_rewrites_extension_to_wav(tmp_path: Path) -> None:
    captured: dict[str, Path] = {}

    def fake_synth_openai(*, text: str, model: str, voice: str, output_path: Path) -> None:
        captured["path"] = output_path
        output_path.write_bytes(b"RIFF")

    with patch("planner.tts_client._synthesize_openai", fake_synth_openai):
        try:
            synthesize(
                "hello",
                tmp_path / "out.mp3",
                config=TTSConfig(provider="openai", voice="alloy"),
            )
        except TTSError:
            pass
    assert captured["path"].suffix == ".wav"


def test_media_duration_via_ffprobe(tmp_path: Path) -> None:
    # Build a 1-second WAV; ffprobe should report ~1.0s. Gated on ffprobe
    # availability since CI environments without ffmpeg can't run this.
    import shutil

    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not available")
    path = tmp_path / "one_second.wav"
    sample_rate = 24000
    silence = struct.pack("<h", 0) * sample_rate
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(silence)
    assert abs(_media_duration_seconds(path) - 1.0) < 0.05


def test_media_duration_rejects_non_media(tmp_path: Path) -> None:
    import shutil

    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not available")
    bad = tmp_path / "garbage.bin"
    bad.write_bytes(b"not media at all")
    with pytest.raises(TTSError):
        _media_duration_seconds(bad)
