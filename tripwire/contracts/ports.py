"""Ports (Protocols) that the detector and Tripwire depend on, plus the shared refusal exception."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from tripwire.contracts.config import RulesConfig
from tripwire.contracts.models import (
    Action,
    ActionSource,
    Incident,
    RuleHit,
    Trace,
)


class ContainmentRefused(Exception):
    """The containment service refused a request (HTTP 409/422 with a `reason`)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class LangfuseReader(Protocol):
    def recent_traces(self, since: datetime) -> list[Trace]:
        """Traces that started at or after `since`, observations loaded."""
        ...

    def get_trace(self, trace_id: str) -> Trace:
        """Fresh copy of one trace (used to refresh running traces)."""
        ...


@runtime_checkable
class SwitchPoster(Protocol):
    def post_alert(self, incident: Incident, text: str) -> str:
        """Post the alert and return the thread_ref."""
        ...

    def set_status(self, thread_ref: str, text: str) -> None:
        """Edit the thread's first message if Switch allows it, else post a status reply (see docs/switch-api.md)."""
        ...

    def reply(self, thread_ref: str, text: str) -> None: ...


@runtime_checkable
class ContainmentClient(Protocol):
    """One method per HTTP route of the containment service (section 3 of tasks.md)."""

    def open_incident(self, rule: str, route: str, opened_at: datetime) -> Incident: ...

    def get(self, incident_id: str) -> Incident: ...

    def list(self, open_only: bool = True) -> list[Incident]: ...

    def update(self, incident_id: str, **fields: Any) -> Incident: ...

    def reopen(self, incident_id: str) -> Incident: ...

    def apply(
        self,
        incident_id: str,
        action: Action,
        source: ActionSource,
        approver: str | None,
        spend_usd: float,
    ) -> dict[str, Any]: ...

    def revert(self, incident_id: str, by: str) -> dict[str, Any]: ...

    def flags(self) -> dict[str, Any]: ...


@runtime_checkable
class Rule(Protocol):
    """Pure function: the detector always passes the full rolling window (last 60 minutes, running traces refreshed)."""

    def evaluate(self, traces: list[Trace], cfg: RulesConfig, now: datetime) -> list[RuleHit]: ...
