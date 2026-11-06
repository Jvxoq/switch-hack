"""Data models shared by every Tripwire component (section 3 of tasks.md)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Literal

RuleName = Literal["loop", "silent_error", "cost_spike", "hourly_ceiling"]
IncidentState = Literal[
    "detected",
    "investigating",
    "queued",
    "awaiting_approval",
    "auto_paused",
    "contained",
    "verifying",
    "resolved",
    "handed_off",
]
Action = Literal["disable_route", "cap_max_steps", "fallback_model"]
ActionSource = Literal["owner", "auto_pause"]

ACTIONS: tuple[str, ...] = ("disable_route", "cap_max_steps", "fallback_model")

# PATCH /incidents/{id} transitions (section 3). `contained` and `auto_paused` are set only by /actions,
# `verifying` after a revert only by /revert. The extra `contained -> verifying` condition (active action is
# cap_max_steps or fallback_model) is enforced by the service, not by this table.
TRANSITIONS: dict[str, frozenset[str]] = {
    "detected": frozenset({"investigating", "queued"}),
    "queued": frozenset({"investigating"}),
    "investigating": frozenset({"awaiting_approval", "handed_off"}),
    "awaiting_approval": frozenset({"investigating", "handed_off"}),
    "auto_paused": frozenset({"investigating"}),
    "contained": frozenset({"verifying"}),
    "verifying": frozenset({"resolved"}),
}


@dataclass
class Observation:
    id: str
    trace_id: str
    type: str
    name: str
    input: Any
    output: Any
    level: str
    start_time: datetime
    cost_usd: float


@dataclass
class Trace:
    """`route` comes from a `route:<name>` tag; `end_time is None` means the trace is still running."""

    id: str
    name: str
    route: str
    thread_id: str | None
    start_time: datetime
    end_time: datetime | None
    total_cost_usd: float
    observations: list[Observation] = field(default_factory=list)


@dataclass
class RuleHit:
    rule: RuleName
    route: str
    trace_id: str
    observation_ids: list[str]
    cost_usd: float
    at: datetime
    detail: str


@dataclass
class Incident:
    """One incident. Lives only in the containment service's `incidents.json`.

    `action` is the action active right now (`None` after a revert).
    """

    id: str  # "INC-<n>", assigned by the containment service
    rule: RuleName
    route: str
    opened_at: datetime
    state: IncidentState = "detected"
    hit_count: int = 0
    trace_ids: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    thread_ref: str | None = None
    action: Action | None = None
    action_source: ActionSource | None = None
    ask_round: int = 1
    auto_paused: bool = False
    approver: str | None = None
    approved_at: datetime | None = None
    contained_at: datetime | None = None
    quiet_since: datetime | None = None
    resolved_at: datetime | None = None
    pr_url: str | None = None
    root_cause: str | None = None
    rejections: int = 0


_DATETIME_FIELDS = {"opened_at", "approved_at", "contained_at", "quiet_since", "resolved_at"}


def incident_to_dict(incident: Incident) -> dict[str, Any]:
    """JSON-safe dict for `incidents.json` and HTTP bodies (datetimes as ISO 8601)."""
    out: dict[str, Any] = {}
    for f in fields(Incident):
        value = getattr(incident, f.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, list):
            value = list(value)
        out[f.name] = value
    return out


def incident_from_dict(data: dict[str, Any]) -> Incident:
    kwargs = dict(data)
    for name in _DATETIME_FIELDS:
        if kwargs.get(name) is not None:
            kwargs[name] = datetime.fromisoformat(kwargs[name])
    known = {f.name for f in fields(Incident)}
    return Incident(**{k: v for k, v in kwargs.items() if k in known})
