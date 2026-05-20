"""Tests for `planner.daemon_runner`.

The unit tests run without Blender. The integration test spawns a real Blender
daemon and exercises the round-trip; it's gated behind `BLENDER_AVAILABLE=1`
so CI/dev machines without Blender can still run the rest of the suite.
"""

import os
import socket

import pytest

from planner import daemon_runner
from planner.daemon_runner import (
    DaemonError,
    find_blender,
    pick_free_port,
)

# --- find_blender -------------------------------------------------------------


def test_find_blender_uses_env_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake = tmp_path / "blender"
    fake.write_text("#!/bin/sh\necho hi\n")
    monkeypatch.setenv("BLENDER_PATH", str(fake))
    assert find_blender() == str(fake)


def test_find_blender_raises_for_bad_env_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLENDER_PATH", "/definitely/not/here/blender")
    with pytest.raises(DaemonError, match="BLENDER_PATH"):
        find_blender()


def test_find_blender_falls_back_to_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    fake = tmp_path / "blender"
    fake.write_text("")
    monkeypatch.setattr(daemon_runner.shutil, "which", lambda _: str(fake))
    # Also stub the macOS fallback path so the test doesn't accidentally find a real install.
    monkeypatch.setattr(daemon_runner, "MACOS_DEFAULT_BLENDER", "/nope")
    assert find_blender() == str(fake)


def test_find_blender_raises_when_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    monkeypatch.setattr(daemon_runner.shutil, "which", lambda _: None)
    monkeypatch.setattr(daemon_runner, "MACOS_DEFAULT_BLENDER", "/nope")
    with pytest.raises(DaemonError, match="Could not locate"):
        find_blender()


# --- pick_free_port -----------------------------------------------------------


def test_pick_free_port_returns_usable_port() -> None:
    port = pick_free_port()
    assert 1024 <= port <= 65535
    # Sanity: we can immediately bind to it (the OS released it when pick_free_port closed).
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))


# --- Integration (real Blender) ----------------------------------------------


needs_blender = pytest.mark.skipif(
    os.environ.get("BLENDER_AVAILABLE") != "1",
    reason="set BLENDER_AVAILABLE=1 to run integration tests against a real Blender",
)


@needs_blender
def test_real_blender_status_round_trip() -> None:
    with daemon_runner.daemon() as handle:
        result = handle.call("status")
    assert result["ok"] is True
    assert result["blender_version"] != "unavailable"


@needs_blender
def test_real_blender_reset_round_trip() -> None:
    with daemon_runner.daemon() as handle:
        result = handle.call("reset")
    assert result == {"ok": True}


@needs_blender
def test_real_blender_unknown_method_raises() -> None:
    with daemon_runner.daemon() as handle, pytest.raises(DaemonError, match="method not found"):
        handle.call("not_a_method")
