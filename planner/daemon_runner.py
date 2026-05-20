"""Spawn and supervise the Blender daemon process.

Used by the development CLI and the Electron app's main process to start the
Blender daemon, wait for it to accept connections, send JSON-RPC requests,
and shut it down cleanly. The daemon itself lives at `blender_daemon/daemon.py`.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DAEMON_SCRIPT = Path(__file__).resolve().parent.parent / "blender_daemon" / "daemon.py"
MACOS_DEFAULT_BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"


class DaemonError(RuntimeError):
    """Raised for daemon startup, communication, or shutdown failures."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_blender() -> str:
    """Locate the Blender executable.

    Resolution order:

    1. `BLENDER_PATH` env var, if set and non-empty.
    2. `blender` on `$PATH`.
    3. The macOS default (`/Applications/Blender.app/Contents/MacOS/Blender`).
    """
    env_path = os.environ.get("BLENDER_PATH", "").strip()
    if env_path:
        if not os.path.exists(env_path):
            raise DaemonError(f"BLENDER_PATH points to a nonexistent file: {env_path}")
        return env_path

    on_path = shutil.which("blender")
    if on_path:
        return on_path

    if os.path.exists(MACOS_DEFAULT_BLENDER):
        return MACOS_DEFAULT_BLENDER

    raise DaemonError(
        "Could not locate the Blender executable. Set BLENDER_PATH or add `blender` to PATH."
    )


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Daemon handle
# ---------------------------------------------------------------------------


class DaemonHandle:
    """Client for a running Blender daemon process."""

    _id_counter = itertools.count(1)

    def __init__(self, port: int, process: subprocess.Popen) -> None:
        self.port = port
        self.process = process

    def call(self, method: str, /, *, _timeout: float | None = None, **params: Any) -> Any:
        """Send a JSON-RPC request and return the `result` field.

        `_timeout` caps how long we wait for the daemon to respond after the
        request is sent. None means "wait forever" — appropriate for renders
        and other long operations that can legitimately take minutes.
        """
        request = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": method,
            "params": params,
        }
        line = (json.dumps(request) + "\n").encode("utf-8")

        # Connection setup is always fast; only the response read should be slow.
        with socket.create_connection(("127.0.0.1", self.port), timeout=10.0) as s:
            s.sendall(line)
            s.settimeout(_timeout)  # None = no timeout
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    raise DaemonError("daemon closed connection before sending a response")
                buf += chunk

        response = json.loads(buf.split(b"\n", 1)[0])
        if "error" in response:
            raise DaemonError(f"daemon error on {method}: {response['error']}")
        return response.get("result")

    def shutdown(self, timeout: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


# ---------------------------------------------------------------------------
# Spawn + readiness
# ---------------------------------------------------------------------------


def start_daemon(
    *,
    blender_path: str | None = None,
    port: int | None = None,
    startup_timeout: float = 60.0,
    log_path: Path | None = None,
) -> DaemonHandle:
    """Spawn Blender with the daemon script and return a connected handle.

    Blocks until the daemon is accepting connections (or `startup_timeout`
    elapses). Blender's stdout/stderr is redirected to `log_path` if given,
    otherwise discarded.
    """
    blender = blender_path or find_blender()
    chosen_port = port or pick_free_port()

    if log_path is not None:
        log_file = open(log_path, "wb")
        stdout: Any = log_file
        stderr: Any = subprocess.STDOUT
    else:
        log_file = None
        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL

    process = subprocess.Popen(
        [
            blender,
            "--background",
            "--python",
            str(DAEMON_SCRIPT),
            "--",
            "--port",
            str(chosen_port),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if log_file is not None:
                log_file.close()
            raise DaemonError(
                f"Blender process exited before daemon was ready (exit code {process.returncode})"
            )
        if _ping(chosen_port):
            return DaemonHandle(port=chosen_port, process=process)
        time.sleep(0.25)

    # Timeout.
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
    if log_file is not None:
        log_file.close()
    raise DaemonError(f"daemon did not become ready within {startup_timeout:.1f}s")


def _ping(port: int) -> bool:
    """Best-effort `status` round-trip; True iff the daemon answered."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5) as s:
            s.sendall(b'{"jsonrpc":"2.0","id":0,"method":"status"}\n')
            buf = b""
            s.settimeout(2.0)
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    return False
                buf += chunk
            return b'"result"' in buf
    except (OSError, ConnectionError):
        return False


@contextmanager
def daemon(**kwargs: Any):
    """Context manager: spawn a daemon, yield the handle, ensure shutdown."""
    handle = start_daemon(**kwargs)
    try:
        yield handle
    finally:
        handle.shutdown()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """`python -m planner.daemon_runner` — start daemon, hit status, print, exit."""
    with daemon() as h:
        result = h.call("status")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
