"""Switch HTTP client tests (T7, client half). Every call goes through httpx.MockTransport: no real network."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from tripwire.contracts.models import Incident
from tripwire.contracts.ports import SwitchPoster
from tripwire.switch_client import (
    SlackFallbackClient,
    SwitchClient,
    SwitchError,
    build_poster,
)

BASE = "https://switch.example.test/api"
AGENT_ID = "agt_detector"
ROOM_ID = "room_123"
KEY = "sk_agent_secret"
TRACE_LINK = "https://langfuse.example.test/trace/tr_42"
ALERT_TEXT = f"INC-7 · loop · route order-lookup · 3 hits · $12.50 · {TRACE_LINK} · @tripwire"


def _incident() -> Incident:
    return Incident(
        id="INC-7",
        rule="loop",
        route="order-lookup",
        opened_at=datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
        hit_count=3,
        cost_usd=12.5,
        trace_ids=["tr_42"],
    )


class Recorder:
    """A MockTransport handler that records each request and answers with canned JSON."""

    def __init__(self, responses: list[httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = list(responses or [])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._responses:
            return self._responses.pop(0)
        return httpx.Response(200, json={"id": "msg_default", "thread_id": "thr_default"})

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def _agent(transport, **kwargs) -> SwitchClient:
    return SwitchClient(BASE, AGENT_ID, KEY, ROOM_ID, transport=httpx.MockTransport(transport), **kwargs)


def _slack(transport, **kwargs) -> SlackFallbackClient:
    return SlackFallbackClient(
        "xoxb-test",
        "C0INCIDENTS",
        base_url="https://slack.example.test/api",
        transport=httpx.MockTransport(transport),
        **kwargs,
    )


def test_T7_agent_post_alert_sends_every_field_with_bearer_auth():
    recorder = Recorder([httpx.Response(200, json={"id": "msg_1", "thread_id": "thr_1"})])
    poster = _agent(recorder)

    thread_ref = poster.post_alert(_incident(), ALERT_TEXT)

    assert thread_ref == "thr_1"
    request = recorder.requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE}/agents/{AGENT_ID}/message"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    body = recorder.body()
    assert body["room_id"] == ROOM_ID
    for field in ("INC-7", "loop", "order-lookup", "3 hits", "$12.50", TRACE_LINK):
        assert field in body["content"]
    assert "@tripwire" in body["content"]


def test_T7_agent_post_alert_adds_missing_address():
    recorder = Recorder()
    _agent(recorder).post_alert(_incident(), "INC-7 plain text")
    assert recorder.body()["content"].endswith("@tripwire")


def test_T7_agent_thread_ref_falls_back_to_message_id():
    recorder = Recorder([httpx.Response(200, json={"message": {"id": "msg_9"}})])
    assert _agent(recorder).post_alert(_incident(), "x") == "msg_9"


def test_T7_agent_post_alert_without_thread_id_returns_none_and_posts_once():
    recorder = Recorder([httpx.Response(200, json={"ok": True, "event_id": "sw_1"})])

    assert _agent(recorder).post_alert(_incident(), "x") is None
    assert len(recorder.requests) == 1


def test_T7_agent_set_status_reply_mode_posts_status_in_thread():
    recorder = Recorder()
    poster = _agent(recorder, status_mode="reply")

    poster.set_status("thr_1", "investigating")

    body = recorder.body()
    assert body["thread_id"] == "thr_1"
    assert body["content"] == "Status: investigating"
    assert str(recorder.requests[0].url) == f"{BASE}/agents/{AGENT_ID}/message"


def test_T7_agent_set_status_edit_mode_calls_update_message():
    recorder = Recorder()
    poster = _agent(recorder, status_mode="edit")

    poster.set_status("msg_first", "INC-7 · now contained @tripwire")

    assert str(recorder.requests[0].url) == f"{BASE}/agents/{AGENT_ID}/ops/update_message"
    body = recorder.body()
    assert body["message_id"] == "msg_first"
    assert body["content"] == "INC-7 · now contained @tripwire"


def test_T7_agent_reply_posts_text_into_thread():
    recorder = Recorder()
    _agent(recorder).reply("thr_1", "Fix PR opened")
    assert recorder.body() == {"room_id": ROOM_ID, "thread_id": "thr_1", "content": "Fix PR opened"}


def test_T7_agent_http_error_raises_switch_error():
    recorder = Recorder([httpx.Response(401, text="bad key")])
    with pytest.raises(SwitchError, match="HTTP 401"):
        _agent(recorder).reply("thr_1", "hi")


def test_T7_dry_run_logs_and_never_calls_network(caplog):
    recorder = Recorder()
    poster = _agent(recorder, dry_run=True)
    caplog.set_level("INFO")

    thread_ref = poster.post_alert(_incident(), ALERT_TEXT)
    poster.set_status(thread_ref, "investigating")
    poster.reply(thread_ref, "hi")

    assert thread_ref == "dry-run-INC-7"
    assert recorder.requests == []
    assert "SWITCH_DRY_RUN" in caplog.text


def test_T7_missing_agent_key_fails_unless_dry_run():
    with pytest.raises(SwitchError):
        SwitchClient(BASE, AGENT_ID, None, ROOM_ID)
    SwitchClient(BASE, AGENT_ID, None, ROOM_ID, dry_run=True)


def test_T7_invalid_status_mode_is_rejected():
    with pytest.raises(ValueError):
        SwitchClient(BASE, AGENT_ID, KEY, ROOM_ID, status_mode="rewrite")  # type: ignore[arg-type]


def test_T7_slack_post_alert_uses_chat_postmessage_and_returns_ts():
    recorder = Recorder([httpx.Response(200, json={"ok": True, "ts": "1700000000.000200"})])
    poster = _slack(recorder)

    ts = poster.post_alert(_incident(), ALERT_TEXT)

    assert ts == "1700000000.000200"
    request = recorder.requests[0]
    assert str(request.url) == "https://slack.example.test/api/chat.postMessage"
    assert request.headers["Authorization"] == "Bearer xoxb-test"
    body = recorder.body()
    assert body["channel"] == "C0INCIDENTS"
    for field in ("INC-7", "loop", "order-lookup", "3 hits", "$12.50", TRACE_LINK, "@tripwire"):
        assert field in body["text"]


def test_T7_slack_ok_false_raises():
    recorder = Recorder([httpx.Response(200, json={"ok": False, "error": "channel_not_found"})])
    with pytest.raises(SwitchError, match="channel_not_found"):
        _slack(recorder).reply("1700000000.000200", "hi")


def test_T7_slack_set_status_reply_mode_threads_under_alert():
    recorder = Recorder([httpx.Response(200, json={"ok": True, "ts": "2"})])
    _slack(recorder, status_mode="reply").set_status("1700000000.000200", "queued")
    body = recorder.body()
    assert body["thread_ts"] == "1700000000.000200"
    assert body["text"] == "Status: queued"


def test_T7_slack_set_status_edit_mode_calls_chat_update():
    recorder = Recorder([httpx.Response(200, json={"ok": True})])
    _slack(recorder, status_mode="edit").set_status("1700000000.000200", "INC-7 · contained @tripwire")
    assert str(recorder.requests[0].url) == "https://slack.example.test/api/chat.update"
    body = recorder.body()
    assert body["ts"] == "1700000000.000200"
    assert body["text"] == "INC-7 · contained @tripwire"


def test_T7_slack_dry_run_never_calls_network():
    recorder = Recorder()
    poster = _slack(recorder, dry_run=True)
    assert poster.post_alert(_incident(), "x") == "dry-run-INC-7"
    assert recorder.requests == []


def test_T7_both_clients_satisfy_switch_poster_port():
    recorder = Recorder()
    assert isinstance(_agent(recorder), SwitchPoster)
    assert isinstance(_slack(recorder), SwitchPoster)


def test_T7_build_poster_selects_path_from_env():
    env = {"SWITCH_PATH": "slack", "SLACK_BOT_TOKEN": "xoxb-x", "SLACK_CHANNEL": "C1", "SWITCH_DRY_RUN": "1"}
    assert isinstance(build_poster(env), SlackFallbackClient)

    env = {
        "SWITCH_BASE_URL": BASE,
        "SWITCH_AGENT_ID": AGENT_ID,
        "SWITCH_AGENT_KEY": KEY,
        "SWITCH_ROOM_ID": ROOM_ID,
    }
    assert isinstance(build_poster(env), SwitchClient)

    with pytest.raises(SwitchError):
        build_poster({"SWITCH_PATH": "carrier-pigeon"})


def test_T7_build_poster_uses_env_status_mode():
    env = {"SWITCH_DRY_RUN": "1", "SWITCH_STATUS_MODE": "edit"}
    assert build_poster(env).status_mode == "edit"


def test_status_defaults_to_reply_without_env() -> None:
    """Edit is undocumented in Switch, so a plain setup posts status replies and never calls the edit endpoint."""
    assert build_poster({"SWITCH_DRY_RUN": "1"}).status_mode == "reply"
    assert SlackFallbackClient("xoxb-test", "C0", dry_run=True).status_mode == "reply"


def test_default_status_posts_reply_not_edit() -> None:
    """With the default mode, a status update is a new reply in the thread and no edit request is sent."""
    recorder = Recorder()
    poster = _agent(recorder)

    poster.set_status("thr_1", "awaiting_approval")

    assert [str(request.url) for request in recorder.requests] == [f"{BASE}/agents/{AGENT_ID}/message"]
    assert recorder.body() == {"room_id": ROOM_ID, "thread_id": "thr_1", "content": "Status: awaiting_approval"}


def test_every_switch_request_carries_timeout() -> None:
    """A Switch call that never answers must end at the client's timeout, not hang the detector."""
    timeouts: list[float | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"thread_id": "th-1"})

    client = SwitchClient(BASE, AGENT_ID, KEY, ROOM_ID, transport=httpx.MockTransport(handler))
    client.post_alert(_incident(), "alert")

    assert timeouts == [10.0]
