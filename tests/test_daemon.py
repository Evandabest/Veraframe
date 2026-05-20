"""Pure-Python tests for `blender_daemon.daemon`'s JSON-RPC layer and arg parsing.

No Blender required — these exercise the protocol with `bpy` unavailable.
"""

import json

import pytest

from blender_daemon import daemon

# --- handle_request -----------------------------------------------------------


def _send(req: dict) -> dict:
    return json.loads(daemon.handle_request(json.dumps(req)))


def test_status_returns_blender_version() -> None:
    response = _send({"jsonrpc": "2.0", "id": 1, "method": "status"})
    assert response["id"] == 1
    assert response["result"]["ok"] is True
    assert "blender_version" in response["result"]


def test_reset_returns_ok() -> None:
    response = _send({"jsonrpc": "2.0", "id": 2, "method": "reset"})
    # When bpy is unavailable (unit tests), reset is a no-op but should still succeed.
    assert response["result"] == {"ok": True}


def test_malformed_json_returns_parse_error() -> None:
    response = json.loads(daemon.handle_request("not json {"))
    assert response["error"]["code"] == -32700
    assert response["id"] is None


def test_missing_method_returns_invalid_request() -> None:
    response = _send({"jsonrpc": "2.0", "id": 1})
    assert response["error"]["code"] == -32600


def test_non_string_method_returns_invalid_request() -> None:
    response = _send({"jsonrpc": "2.0", "id": 1, "method": 42})
    assert response["error"]["code"] == -32600


def test_unknown_method_returns_method_not_found() -> None:
    response = _send({"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert response["error"]["code"] == -32601
    assert "nope" in response["error"]["message"]


def test_handler_typeerror_returns_invalid_params() -> None:
    response = _send({"jsonrpc": "2.0", "id": 1, "method": "status", "params": {"unexpected": 1}})
    assert response["error"]["code"] == -32602


def test_handler_exception_returns_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise RuntimeError("kaboom")

    monkeypatch.setitem(daemon.HANDLERS, "boom", boom)
    response = _send({"jsonrpc": "2.0", "id": 9, "method": "boom"})
    assert response["error"]["code"] == -32603
    assert "kaboom" in response["error"]["message"]


# --- parse_port ---------------------------------------------------------------


def test_parse_port_after_double_dash() -> None:
    # Mimics how Blender invokes us: blender ... --python daemon.py -- --port 8000
    argv = ["daemon.py", "--", "--port", "8000"]
    assert daemon.parse_port(argv) == 8000


def test_parse_port_without_double_dash() -> None:
    argv = ["daemon.py", "--port", "9090"]
    assert daemon.parse_port(argv) == 9090


def test_parse_port_missing_raises() -> None:
    with pytest.raises(SystemExit):
        daemon.parse_port(["daemon.py"])
