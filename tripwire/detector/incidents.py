"""Incident manager: turns rule hits into one incident per (rule, route) and posts the Switch alerts. Owned by E01.

The containment service is the only incident store. This module keeps no incident state of its own, except the
set of queued incidents it has already nudged (in memory; a restart may repeat one nudge, never a state change).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from tripwire.contracts.models import Incident, RuleHit
from tripwire.contracts.ports import Clock, ContainmentClient, ContainmentRefused, SwitchPoster

_CLOSED = frozenset({"resolved", "handed_off"})
# An incident in one of these states is using Tripwire's attention; others queue behind it (decision #25).
_BUSY = frozenset({"investigating", "awaiting_approval"})
_SHOWN_TRACES = 3


class IncidentManager:
    def __init__(self, containment: ContainmentClient, switch: SwitchPoster, clock: Clock) -> None:
        self._containment = containment
        self._switch = switch
        self._clock = clock
        self._nudged: set[str] = set()

    def ingest(self, hits: Iterable[RuleHit]) -> None:
        """Fold one evaluation of the rolling window into the open incidents.

        The detector passes the full window on every poll, so a trace already counted is never counted twice.
        """
        groups: dict[tuple[str, str], list[RuleHit]] = defaultdict(list)
        for hit in hits:
            groups[(hit.rule, hit.route)].append(hit)
        for (rule, route), group in groups.items():
            self._ingest_group(rule, route, _cost_by_trace(group))
        self._nudge_next_queued()

    # ---- one (rule, route) group ----------------------------------------

    def _ingest_group(self, rule: str, route: str, costs: dict[str, float]) -> None:
        incident = self._find_open(rule, route)
        if incident is None:
            incident = self._open(rule, route)
            incident = self._count_traces(incident, costs)
            self._alert(incident)
            return

        new = {tid: cost for tid, cost in costs.items() if tid not in incident.trace_ids}
        if not new:
            return
        incident = self._count_traces(incident, new)
        if incident.thread_ref is None:
            self._alert(incident)
        else:
            self._switch.set_status(incident.thread_ref, _status_text(incident))

    def _count_traces(self, incident: Incident, costs: dict[str, float]) -> Incident:
        """Count the traces not yet on the incident. `costs` maps trace id to its cost in this window."""
        new = {tid: cost for tid, cost in costs.items() if tid not in incident.trace_ids}
        trace_ids = list(incident.trace_ids) + list(new)
        return self._containment.update(
            incident.id,
            trace_ids=trace_ids,
            hit_count=len(trace_ids),
            cost_usd=round(incident.cost_usd + sum(new.values()), 6),
        )

    def _open(self, rule: str, route: str) -> Incident:
        try:
            return self._containment.open_incident(rule, route, self._clock.now())
        except ContainmentRefused:
            # Another poll (or process) opened it between our list and our open. Use that one.
            existing = self._find_open(rule, route)
            if existing is None:
                raise
            return existing

    def _find_open(self, rule: str, route: str) -> Incident | None:
        for incident in self._containment.list(open_only=True):
            if incident.rule == rule and incident.route == route and incident.state not in _CLOSED:
                return incident
        return None

    # ---- alerts and queue ------------------------------------------------

    def _alert(self, incident: Incident) -> None:
        """Post the alert for a new incident. If another incident is using Tripwire, queue this one and say so."""
        blocker = self._busy_incident(exclude=incident.id)
        thread_ref = self._switch.post_alert(incident, _alert_text(incident, blocker))
        fields: dict[str, object] = {"thread_ref": thread_ref}
        if blocker is not None and incident.state == "detected":
            fields["state"] = "queued"
        self._containment.update(incident.id, **fields)

    def _busy_incident(self, exclude: str) -> Incident | None:
        for incident in self._containment.list(open_only=True):
            if incident.id != exclude and incident.state in _BUSY:
                return incident
        return None

    def _nudge_next_queued(self) -> None:
        """When nothing is using Tripwire, tell the oldest queued incident's thread to address @tripwire, once."""
        open_incidents = self._containment.list(open_only=True)
        if any(incident.state in _BUSY for incident in open_incidents):
            return
        queued = sorted((i for i in open_incidents if i.state == "queued"), key=lambda i: i.opened_at)
        if not queued:
            return
        oldest = queued[0]
        if oldest.id in self._nudged or oldest.thread_ref is None:
            return
        self._switch.reply(
            oldest.thread_ref,
            f"@tripwire {oldest.id} ({oldest.rule} on {oldest.route}) is next in line. Nothing else is open.",
        )
        self._nudged.add(oldest.id)


def _cost_by_trace(hits: Iterable[RuleHit]) -> dict[str, float]:
    costs: dict[str, float] = {}
    for hit in hits:
        costs[hit.trace_id] = costs.get(hit.trace_id, 0.0) + hit.cost_usd
    return costs


def _status_text(incident: Incident) -> str:
    return (
        f"{incident.id} ({incident.rule}) on {incident.route}: "
        f"{incident.hit_count} traces, ${incident.cost_usd:.2f} so far."
    )


def _alert_text(incident: Incident, blocker: Incident | None) -> str:
    shown = ", ".join(incident.trace_ids[:_SHOWN_TRACES]) or "none"
    lines = [
        f"{incident.id} ({incident.rule}) on route {incident.route}",
        f"{incident.hit_count} traces, ${incident.cost_usd:.2f} so far",
        f"Trace: {shown}",
    ]
    if blocker is None:
        lines.append("@tripwire please investigate.")
    else:
        lines.append(f"Queued behind {blocker.id} ({blocker.state}). @tripwire will take it when that clears.")
    return "\n".join(lines)
