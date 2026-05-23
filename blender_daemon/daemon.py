"""Long-lived Blender daemon — JSON-RPC over local TCP.

Run via `blender --background --python blender_daemon/daemon.py -- --port <N>`.
Arguments after `--` are passed to this script by Blender.

The daemon listens on `127.0.0.1:<port>` and dispatches line-delimited
JSON-RPC 2.0 requests to handlers registered in `HANDLERS`. Step 6 ships only
`status` and `reset`; later steps will register `load_scene`, `load_character`,
`execute_timeline`, and `render`.

Only the Python standard library is used here so we don't have to install
external packages into Blender's bundled Python.
"""

import json
import socket
import sys
import traceback
from pathlib import Path

# Blender invokes this file as `--python /abs/path/to/blender_daemon/daemon.py`,
# which doesn't add the project root to sys.path. Insert it so `from
# blender_daemon.<x>` imports resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from actions import idle as idle_action  # noqa: E402
from actions import play_clip as play_clip_action  # noqa: E402
from actions import walk_to as walk_to_action  # noqa: E402
from blender_daemon.action_executor import execute_timeline  # noqa: E402
from blender_daemon.character_loader import load_character  # noqa: E402
from blender_daemon.render_manager import render  # noqa: E402
from blender_daemon.scene_loader import load_scene  # noqa: E402

try:
    import bpy

    _BLENDER_VERSION = bpy.app.version_string
except ImportError:
    # Allows importing this module outside Blender for unit tests.
    bpy = None
    _BLENDER_VERSION = "unavailable"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def status() -> dict:
    return {"ok": True, "blender_version": _BLENDER_VERSION}


def reset() -> dict:
    """Clear loaded scene data without going through the homefile-read operator.

    `bpy.ops.wm.read_factory_settings()` tears down UI regions and crashes in
    background mode. Direct `bpy.data` removal does the same logical work and
    stays on the Python main thread cleanly.
    """
    if bpy is not None:
        for collection_name in (
            "objects",
            "meshes",
            "materials",
            "armatures",
            "cameras",
            "lights",
            "images",
            "actions",
            "node_groups",
            "collections",
        ):
            collection = getattr(bpy.data, collection_name, None)
            if collection is None:
                continue
            bpy.data.batch_remove(list(collection))
    # Drop Python-side caches that hold references to the now-freed Actions.
    # Without this, the next walk_to/idle dispatch returns a dead StructRNA and
    # raises "StructRNA of type Action has been removed".
    idle_action.clear_cache()
    walk_to_action.clear_cache()
    play_clip_action.clear_cache()
    return {"ok": True}


HANDLERS: dict[str, callable] = {
    "status": status,
    "reset": reset,
    "load_scene": load_scene,
    "load_character": load_character,
    "execute_timeline": execute_timeline,
    "render": render,
}


# ---------------------------------------------------------------------------
# JSON-RPC dispatch
# ---------------------------------------------------------------------------


def handle_request(line: str) -> str:
    """Process one JSON-RPC request line, return one response line."""
    try:
        request = json.loads(line)
    except json.JSONDecodeError as e:
        return _error_response(None, -32700, f"parse error: {e}")

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if not isinstance(method, str):
        return _error_response(request_id, -32600, "missing or non-string 'method'")

    handler = HANDLERS.get(method)
    if handler is None:
        return _error_response(request_id, -32601, f"method not found: {method}")

    try:
        result = handler(**params) if isinstance(params, dict) else handler(*params)
    except TypeError as e:
        return _error_response(request_id, -32602, f"invalid params: {e}")
    except Exception as e:  # noqa: BLE001 — daemon must never crash on a handler error
        traceback.print_exc()
        return _error_response(request_id, -32603, f"internal error: {e}")

    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error_response(request_id, code: int, message: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


# ---------------------------------------------------------------------------
# TCP server
# ---------------------------------------------------------------------------


def _serve_client(conn: socket.socket) -> None:
    buf = b""
    with conn:
        while True:
            try:
                chunk = conn.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                response = handle_request(line.decode("utf-8", errors="replace"))
                try:
                    conn.sendall((response + "\n").encode("utf-8"))
                except OSError:
                    return


def serve(port: int, host: str = "127.0.0.1") -> None:
    """Single-threaded accept loop.

    Blender's Python API is not thread-safe — operators and `bpy.data` mutation
    must happen on the main thread (the thread the script runs on under
    `blender --background --python`). Handling clients serially on this thread
    keeps every handler call on the main thread; concurrent clients queue.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(5)
    print(f"VERAFRAME_DAEMON_READY host={host} port={port}", flush=True)

    while True:
        try:
            conn, _addr = sock.accept()
        except (KeyboardInterrupt, OSError):
            sock.close()
            return
        _serve_client(conn)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_port(argv: list[str]) -> int:
    """Extract `--port N` from argv. Blender prepends its own args before `--`."""
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            return int(argv[i + 1])
    raise SystemExit("daemon: --port <N> is required")


if __name__ == "__main__":
    port = parse_port(sys.argv)
    serve(port)
