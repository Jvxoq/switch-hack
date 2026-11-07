"""The repo-root `.mcp.json` that Claude Code reads when the Tripwire agent runs in this repo (H-PREP)."""

from __future__ import annotations

import importlib.util
import json

from tests.conftest import REPO_ROOT

MCP_CONFIG = REPO_ROOT / ".mcp.json"


def _server() -> dict:
    data = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    return data["mcpServers"]["tripwire"]


def test_mcp_json_parses_with_tripwire_server() -> None:
    """Claude Code finds the tool server under the name the instructions expect."""
    assert set(json.loads(MCP_CONFIG.read_text(encoding="utf-8"))["mcpServers"]) == {"tripwire"}


def test_mcp_command_runs_an_importable_module() -> None:
    """The stdio command names a module that exists, so Claude Code can start it from the repo root."""
    server = _server()
    args = server["args"]
    module = args[args.index("-m") + 1]

    assert server["command"] == "uv"
    assert module == "tripwire_agent.server"
    assert importlib.util.find_spec(module) is not None


def test_mcp_file_holds_no_secret_values() -> None:
    """Secrets reach the tool server from the environment, never from the committed file."""
    env = _server().get("env", {})

    assert not any(key.endswith(("_KEY", "_SECRET", "_TOKEN")) for key in env)
    assert all(value.startswith("${") for value in env.values())
    assert "sk-" not in MCP_CONFIG.read_text(encoding="utf-8")
