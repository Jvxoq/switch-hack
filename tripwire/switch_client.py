"""Switch HTTP client: the real `SwitchPoster` (section 3 and W01 of tasks.md).

Two posting paths, both selectable (docs/switch-api.md, "Alert path"):
- path "agent" (PREFERRED, `SwitchClient`): the detector registers as its own Switch agent and posts with its API key.
- path "slack" (FALLBACK, `SlackFallbackClient`): a Slack bot posts with `chat.postMessage`.
`build_poster()` picks one from the environment (`SWITCH_PATH`, default "agent").

`status_mode` picks how `set_status` works: "reply" (default, posts `Status: <state>` in the thread) or
"edit" (edits the first message). The docs document no edit operation, so "reply" is the default.

Provisional until H00 confirms:
- thread_ref: the agent path reads the thread id from the POST response (`thread_id`, then `message.thread_id`,
  then the message `id`). The response shape is not documented.
- replies: the agent path sends `thread_id` in the body of POST /agents/{id}/message to stay in the thread.
- `@tripwire` in content must address Tripwire (the `addressed` flag is not documented).
- edit mode: `POST /agents/{id}/ops/update_message` with `message_id` (UNCONFIRMED endpoint); Slack uses `chat.update`.
- Slack path: a bot post is treated as a human sender for addressing (UNCONFIRMED).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Literal

import httpx

from tripwire.contracts.models import Incident

log = logging.getLogger(__name__)

ADDRESS = "@tripwire"
StatusMode = Literal["reply", "edit"]
Path = Literal["agent", "slack"]

SLACK_API = "https://slack.com/api"


class SwitchError(RuntimeError):
    """Switch (or Slack) refused or failed a call, or the client is misconfigured."""


def format_alert_text(incident: Incident, trace_link: str | None = None) -> str:
    """The alert line: `INC-<n> · <rule> · route <route> · <hits> hits · $<cost> · <trace link> · @tripwire`."""
    link = trace_link or "no trace link"
    return (
        f"{incident.id} · {incident.rule} · route {incident.route} · {incident.hit_count} hits · "
        f"${incident.cost_usd:.2f} · {link} · {ADDRESS}"
    )


def _ensure_address(text: str) -> str:
    return text if ADDRESS in text else f"{text} {ADDRESS}"


def _status_text(text: str) -> str:
    return text if text.startswith("Status:") else f"Status: {text}"


class _Base:
    def __init__(
        self,
        *,
        dry_run: bool,
        status_mode: StatusMode,
        transport: httpx.BaseTransport | None,
        timeout: float,
    ) -> None:
        if status_mode not in ("reply", "edit"):
            raise ValueError(f"status_mode must be 'reply' or 'edit', not {status_mode!r}")
        self.dry_run = dry_run
        self.status_mode = status_mode
        self._http = httpx.Client(transport=transport, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _dry(self, action: str, detail: str) -> None:
        log.info("SWITCH_DRY_RUN: would %s: %s", action, detail)


class SwitchClient(_Base):
    """Path "agent": POST /agents/{agent_id}/message with the detector's agent key."""

    def __init__(
        self,
        base_url: str,
        agent_id: str,
        agent_key: str | None,
        room_id: str,
        *,
        dry_run: bool = False,
        status_mode: StatusMode = "reply",
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(dry_run=dry_run, status_mode=status_mode, transport=transport, timeout=timeout)
        if not dry_run and not agent_key:
            raise SwitchError("Switch agent key is required unless SWITCH_DRY_RUN=1")
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.agent_key = agent_key or ""
        self.room_id = room_id

    @classmethod
    def from_env(cls, environ: Mapping[str, str], transport: httpx.BaseTransport | None = None) -> SwitchClient:
        dry_run = environ.get("SWITCH_DRY_RUN", "") == "1"
        return cls(
            base_url=environ.get("SWITCH_BASE_URL", ""),
            agent_id=environ.get("SWITCH_AGENT_ID", ""),
            agent_key=environ.get("SWITCH_AGENT_KEY") or environ.get("SWITCH_TOKEN"),
            room_id=environ.get("SWITCH_ROOM_ID", ""),
            dry_run=dry_run,
            status_mode=environ.get("SWITCH_STATUS_MODE", "reply"),  # type: ignore[arg-type]
            transport=transport,
        )

    # SwitchPoster port -------------------------------------------------

    def post_alert(self, incident: Incident, text: str) -> str:
        content = _ensure_address(text)
        if self.dry_run:
            self._dry("post alert", content)
            return f"dry-run-{incident.id}"
        data = self._post(f"/agents/{self.agent_id}/message", {"room_id": self.room_id, "content": content})
        message = data.get("message") if isinstance(data.get("message"), dict) else {}
        thread_ref = data.get("thread_id") or message.get("thread_id") or data.get("id") or message.get("id")
        if not thread_ref:
            raise SwitchError("Switch accepted the alert but returned no thread id")
        return str(thread_ref)

    def set_status(self, thread_ref: str, text: str) -> None:
        if self.status_mode == "edit":
            body = {"room_id": self.room_id, "message_id": thread_ref, "content": _ensure_address(text)}
            if self.dry_run:
                self._dry("edit first message", str(body))
                return
            self._post(f"/agents/{self.agent_id}/ops/update_message", body)
            return
        self.reply(thread_ref, _status_text(text))

    def reply(self, thread_ref: str, text: str) -> None:
        body = {"room_id": self.room_id, "thread_id": thread_ref, "content": text}
        if self.dry_run:
            self._dry("reply", str(body))
            return
        self._post(f"/agents/{self.agent_id}/message", body)

    # HTTP --------------------------------------------------------------

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(
            f"{self.base_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self.agent_key}"},
        )
        if response.status_code >= 400:
            raise SwitchError(f"Switch {path} failed: HTTP {response.status_code}: {response.text[:200]}")
        return response.json() if response.content else {}


class SlackFallbackClient(_Base):
    """Path "slack": chat.postMessage with a Slack bot token. The thread_ref is the message `ts`."""

    def __init__(
        self,
        bot_token: str | None,
        channel: str,
        *,
        base_url: str = SLACK_API,
        dry_run: bool = False,
        status_mode: StatusMode = "reply",
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(dry_run=dry_run, status_mode=status_mode, transport=transport, timeout=timeout)
        if not dry_run and not bot_token:
            raise SwitchError("SLACK_BOT_TOKEN is required unless SWITCH_DRY_RUN=1")
        self.bot_token = bot_token or ""
        self.channel = channel
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_env(cls, environ: Mapping[str, str], transport: httpx.BaseTransport | None = None) -> SlackFallbackClient:
        return cls(
            environ.get("SLACK_BOT_TOKEN"),
            environ.get("SLACK_CHANNEL", ""),
            dry_run=environ.get("SWITCH_DRY_RUN", "") == "1",
            status_mode=environ.get("SWITCH_STATUS_MODE", "reply"),  # type: ignore[arg-type]
            transport=transport,
        )

    # SwitchPoster port -------------------------------------------------

    def post_alert(self, incident: Incident, text: str) -> str:
        content = _ensure_address(text)
        if self.dry_run:
            self._dry("post alert", content)
            return f"dry-run-{incident.id}"
        data = self._call("chat.postMessage", {"channel": self.channel, "text": content})
        return str(data["ts"])

    def set_status(self, thread_ref: str, text: str) -> None:
        if self.status_mode == "edit":
            body = {"channel": self.channel, "ts": thread_ref, "text": _ensure_address(text)}
            if self.dry_run:
                self._dry("chat.update", str(body))
                return
            self._call("chat.update", body)
            return
        self.reply(thread_ref, _status_text(text))

    def reply(self, thread_ref: str, text: str) -> None:
        body = {"channel": self.channel, "text": text, "thread_ts": thread_ref}
        if self.dry_run:
            self._dry("reply", str(body))
            return
        self._call("chat.postMessage", body)

    # HTTP --------------------------------------------------------------

    def _call(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(
            f"{self.base_url}/{method}",
            json=body,
            headers={"Authorization": f"Bearer {self.bot_token}"},
        )
        if response.status_code >= 400:
            raise SwitchError(f"Slack {method} failed: HTTP {response.status_code}")
        data = response.json()
        if not data.get("ok"):
            raise SwitchError(f"Slack {method} failed: {data.get('error', 'unknown error')}")
        return data


def build_poster(
    environ: Mapping[str, str],
    transport: httpx.BaseTransport | None = None,
) -> SwitchClient | SlackFallbackClient:
    """Choose the posting path from `SWITCH_PATH` ("agent" by default, or "slack")."""
    path: Path = environ.get("SWITCH_PATH", "agent").lower()  # type: ignore[assignment]
    if path == "agent":
        return SwitchClient.from_env(environ, transport=transport)
    if path == "slack":
        return SlackFallbackClient.from_env(environ, transport=transport)
    raise SwitchError(f"SWITCH_PATH must be 'agent' or 'slack', not {path!r}")
