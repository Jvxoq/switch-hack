"""Auto-pause and the hourly ceiling (E02). Runs once per detector poll, after the rules have run.

Auto-pause: each open incident with no active action and no earlier auto-pause gets `disable_route` when its
spend reaches `budget_fraction` of the route's loss budget, or when it is `auto_pause.minutes` old. The
containment service checks the same thresholds and refuses otherwise.

Hourly ceiling: when a route spends at least its `hourly_ceiling_usd` in the last hour, a `hourly_ceiling` hit
goes to the IncidentManager (so the incident gets a thread and an alert like any other). That incident is paused
in the same poll, with no rule hit needed.

Incident state lives only in the containment service. Nothing here is remembered between polls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from tripwire.contracts.config import TripwireConfig
from tripwire.contracts.models import Incident, RuleHit, Trace
from tripwire.contracts.ports import Clock, ContainmentClient, ContainmentRefused, SwitchPoster

log = logging.getLogger(__name__)

CEILING_RULE = "hourly_ceiling"
HOUR = timedelta(hours=1)

IngestHit = Callable[[RuleHit], object]


@dataclass(frozen=True)
class AutoPause:
    incident_id: str
    route: str
    spend_usd: float


def run_autopause(
    *,
    containment: ContainmentClient,
    switch: SwitchPoster,
    clock: Clock,
    cfg: TripwireConfig,
    traces: list[Trace],
    ingest: IngestHit,
) -> list[AutoPause]:
    """One poll of auto-pause. `traces` is the full rolling window. Returns the incidents paused in this poll."""
    now = clock.now()
    _emit_ceiling_hits(containment, cfg, traces, now, ingest)

    paused: list[AutoPause] = []
    for inc in containment.list(open_only=True):
        if inc.route not in cfg.routes:
            log.warning("auto-pause skipped for %s: route %r is not configured", inc.id, inc.route)
            continue
        if inc.action is not None or inc.auto_paused:
            continue
        spend = _incident_spend(inc, traces, now)
        if not _due(inc, spend, cfg, now):
            continue
        try:
            containment.apply(inc.id, "disable_route", "auto_pause", None, spend)
        except ContainmentRefused as refused:
            log.warning("auto-pause refused for %s: %s", inc.id, refused.reason)
            continue
        paused.append(AutoPause(incident_id=inc.id, route=inc.route, spend_usd=spend))
        try:
            _offer_revert(switch, inc, spend)
        except Exception:
            log.exception("revert offer failed for %s; the route stays paused", inc.id)
    return paused


def _emit_ceiling_hits(
    containment: ContainmentClient,
    cfg: TripwireConfig,
    traces: list[Trace],
    now: datetime,
    ingest: IngestHit,
) -> None:
    """Send one `hourly_ceiling` hit per route that has none open and is at or over its ceiling."""
    open_ceiling_routes = {inc.route for inc in containment.list(open_only=True) if inc.rule == CEILING_RULE}
    for route, route_cfg in cfg.routes.items():
        if route in open_ceiling_routes:
            continue
        hour = [t for t in traces if t.route == route and t.start_time >= now - HOUR]
        if not hour:
            continue
        spend = _route_hour_spend(traces, route, now)
        if spend < route_cfg.hourly_ceiling_usd:
            continue
        newest = max(hour, key=lambda t: t.start_time)
        ingest(
            RuleHit(
                rule=CEILING_RULE,
                route=route,
                trace_id=newest.id,
                observation_ids=[],
                cost_usd=spend,
                at=now,
                detail=f"route spent ${spend:.2f} in the last hour, ceiling ${route_cfg.hourly_ceiling_usd:.2f}",
            )
        )


def _route_hour_spend(traces: list[Trace], route: str, now: datetime) -> float:
    return sum((t.total_cost_usd for t in traces if t.route == route and t.start_time >= now - HOUR), 0.0)


def _incident_spend(inc: Incident, traces: list[Trace], now: datetime) -> float:
    """Spend of the incident's traces in the window. A ceiling incident's spend is its route's last-hour spend."""
    if inc.rule == CEILING_RULE:
        return _route_hour_spend(traces, inc.route, now)
    ids = set(inc.trace_ids)
    return sum((t.total_cost_usd for t in traces if t.id in ids), 0.0)


def _due(inc: Incident, spend: float, cfg: TripwireConfig, now: datetime) -> bool:
    route_cfg = cfg.routes[inc.route]
    if spend >= cfg.auto_pause.budget_fraction * route_cfg.loss_budget_usd:
        return True
    if now - inc.opened_at >= timedelta(minutes=cfg.auto_pause.minutes):
        return True
    return inc.rule == CEILING_RULE and spend >= route_cfg.hourly_ceiling_usd


def _offer_revert(switch: SwitchPoster, inc: Incident, spend: float) -> None:
    if inc.thread_ref is None:
        log.warning("no Switch thread to offer revert on for %s", inc.id)
        return
    switch.reply(
        inc.thread_ref,
        f"Route {inc.route} auto-paused at ${spend:.2f} spend. Reply `revert {inc.id}` to resume it.",
    )
