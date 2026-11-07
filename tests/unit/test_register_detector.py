"""The detector registration helper (scripts/register_detector.py). Every HTTP call goes through httpx.MockTransport."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from tests.conftest import REPO_ROOT


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("register_detector", REPO_ROOT / "scripts" / "register_detector.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


register_detector = _load()
BASE = "https://switch.example.test"
REG_KEY = "reg_secret_value"
AGENT_KEY = "agk_secret_value"


def _transport(response: httpx.Response, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    return httpx.MockTransport(handler)


def test_register_sends_passive_profile_with_registration_key() -> None:
    """The detector only posts, so it registers as session_passive and authenticates with the registration key."""
    seen: list[httpx.Request] = []
    transport = _transport(httpx.Response(200, json={"id": "agt_1", "api_key": AGENT_KEY}), seen)

    result = register_detector.register(BASE, REG_KEY, transport=transport)

    request = seen[0]
    assert result == {"id": "agt_1", "api_key": AGENT_KEY}
    assert str(request.url) == f"{BASE}/agents"
    assert request.headers["Authorization"] == f"Bearer {REG_KEY}"
    body = json.loads(request.content)
    assert body["name"] == "tripwire-detector"
    assert body["integration_profile"]["connection_model"] == "session_passive"
    assert "overwrite" not in body


def test_register_name_conflict_asks_for_overwrite() -> None:
    """A 409 means the name exists. The message says how to rotate the key, not just that it failed."""
    transport = _transport(httpx.Response(409, json={"detail": "exists"}), [])

    with pytest.raises(register_detector.RegisterError, match=r"--overwrite"):
        register_detector.register(BASE, REG_KEY, transport=transport)


def test_register_server_error_names_status() -> None:
    """Any other refusal raises with the HTTP status, so the human sees what Switch said."""
    transport = _transport(httpx.Response(500, text="boom"), [])

    with pytest.raises(register_detector.RegisterError, match=r"HTTP 500"):
        register_detector.register(BASE, REG_KEY, transport=transport)


def test_register_answer_without_key_is_refused() -> None:
    """An answer with no api_key would leave the detector unable to post, so it is an error, not a success."""
    transport = _transport(httpx.Response(200, json={"id": "agt_1"}), [])

    with pytest.raises(register_detector.RegisterError, match=r"without an id and api_key"):
        register_detector.register(BASE, REG_KEY, transport=transport)


def test_overwrite_flag_rotates_key_in_body() -> None:
    """--overwrite adds `overwrite: true`, the only way Switch rotates an existing key."""
    assert register_detector.registration_body(overwrite=True)["overwrite"] is True


def test_main_writes_credentials_and_hides_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """The key goes into .env and never onto the terminal, because Switch returns it once."""
    env_file = tmp_path / ".env"
    env_file.write_text("SWITCH_DRY_RUN=1\nSWITCH_TOKEN=\n", encoding="utf-8")
    monkeypatch.setattr(
        register_detector, "register", lambda *args, **kwargs: {"id": "agt_9", "api_key": AGENT_KEY}
    )

    code = register_detector.main(
        ["--env-file", str(env_file)],
        environ={"SWITCH_BASE_URL": BASE, "SWITCH_REGISTRATION_KEY": REG_KEY},
    )

    text = env_file.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert code == 0
    assert "SWITCH_AGENT_ID=agt_9" in text.splitlines()
    assert f"SWITCH_TOKEN={AGENT_KEY}" in text.splitlines()
    assert "SWITCH_DRY_RUN=1" in text.splitlines()
    assert AGENT_KEY not in out
    assert "agt_9" in out


def test_main_without_inputs_exits_two(capsys) -> None:
    """Missing inputs stop before any request, with exit code 2."""
    assert register_detector.main([], environ={}) == 2


def test_dry_run_prints_body_without_sending(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run shows the request and makes no call."""

    def boom(*args, **kwargs):
        raise AssertionError("dry run must not call Switch")

    monkeypatch.setattr(register_detector, "register", boom)

    code = register_detector.main(
        ["--dry-run"], environ={"SWITCH_BASE_URL": BASE, "SWITCH_REGISTRATION_KEY": REG_KEY}
    )

    assert code == 0
    assert f"POST {BASE}/agents" in capsys.readouterr().out
