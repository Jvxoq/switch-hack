"""Live check of the Switch client against a real Switch server (H00-sim, docs/switch-api.md).

Skipped unless the four env vars below are set. Each run posts real messages into the room, so point it at a test room:
  SWITCH_BASE_URL=http://127.0.0.1:8000  SWITCH_AGENT_ID=<detector id>  SWITCH_AGENT_KEY=<detector key>
  SWITCH_ROOM_ID=<room id>               uv run pytest -q -m live tests/integration/test_switch_client_live.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from tripwire.contracts.models import Incident
from tripwire.switch_client import SwitchClient, SwitchError, format_alert_text

REQUIRED = ("SWITCH_BASE_URL", "SWITCH_AGENT_ID", "SWITCH_AGENT_KEY", "SWITCH_ROOM_ID")

pytestmark = [pytest.mark.live, pytest.mark.switch]


def _client() -> SwitchClient:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip(f"live Switch test needs {', '.join(missing)}")
    return SwitchClient.from_env(os.environ)


def _incident() -> Incident:
    return Incident(
        id="INC-LIVE",
        rule="loop",
        route="order-lookup",
        opened_at=datetime.now(timezone.utc),
        hit_count=1,
        cost_usd=0.01,
    )


def test_live_post_alert_returns_event_id_and_status_reply_posts():
    client = _client()
    text = format_alert_text(_incident(), "https://langfuse.example.test/trace/live")

    thread_ref = client.post_alert(_incident(), text)
    assert thread_ref.startswith("sw_"), thread_ref

    client.set_status(thread_ref, "live test status")


def test_live_edit_mode_is_refused_because_switch_has_no_edit_op():
    """Switch 0.31 answers 404 for ops/update_message (verified 2026-11-07). Reply is the only status mode."""
    client = _client()
    client.status_mode = "edit"
    thread_ref = client.post_alert(_incident(), format_alert_text(_incident()))

    with pytest.raises(SwitchError, match="HTTP 404"):
        client.set_status(thread_ref, "live test edit")
