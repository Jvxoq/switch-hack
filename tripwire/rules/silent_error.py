"""Silent-error rule.

An observation is a silent error when its output matches any configured pattern (case-insensitive substring)
while its level is not ERROR. A route fires when `count` silent errors fall inside a sliding window of
`window_minutes` that ends at `now`. The window is measured on observation start times and spans all traces
passed in, so a burst split across several traces still fires.

Once a route reaches the threshold, the rule emits one hit per trace that has silent errors in the window.
Each hit cites only that trace's silent-error observations, and `cost_usd` is their summed cost. Cost is
counted once per trace, so the incident manager (which dedupes cost by trace id) never adds the same window
cost twice as the window moves. `detail` carries the route-level count for the whole window.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from tripwire.contracts.config import RulesConfig
from tripwire.contracts.models import Observation, RuleHit, Trace


def _output_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(output)


def _is_silent_error(obs: Observation, patterns: list[str]) -> bool:
    if str(obs.level).upper() == "ERROR":
        return False
    text = _output_text(obs.output).lower()
    if not text:
        return False
    return any(pattern.lower() in text for pattern in patterns if pattern)


class SilentErrorRule:
    """Implements the `Rule` protocol from `tripwire.contracts.ports`. Pure: no I/O, no clock reads."""

    name = "silent_error"

    def evaluate(self, traces: list[Trace], cfg: RulesConfig, now: datetime) -> list[RuleHit]:
        settings = cfg.silent_error
        window_start = now - timedelta(minutes=settings.window_minutes)

        # route -> {observation id: (observation, trace)}; dict keeps one entry per observation even if a
        # trace shows up twice in the input.
        by_route: dict[str, dict[str, tuple[Observation, Trace]]] = {}
        for trace in traces:
            for obs in trace.observations:
                if not (window_start <= obs.start_time <= now):
                    continue
                if not _is_silent_error(obs, settings.patterns):
                    continue
                by_route.setdefault(trace.route, {})[obs.id] = (obs, trace)

        hits: list[RuleHit] = []
        for route in sorted(by_route):
            matches = sorted(by_route[route].values(), key=lambda pair: (pair[0].start_time, pair[0].id))
            if len(matches) < settings.count:
                continue
            detail = (
                f"{len(matches)} silent errors on route {route} in the last "
                f"{settings.window_minutes:g} minutes (threshold {settings.count})"
            )
            route_hits = [
                _trace_hit(route, trace_observations, now, detail)
                for trace_observations in _group_by_trace(matches)
            ]
            hits.extend(route_hits)
        return hits


def _group_by_trace(matches: list[tuple[Observation, Trace]]) -> list[list[tuple[Observation, Trace]]]:
    """Split one route's matches by trace. Each group keeps start-time order and groups are ordered by newest."""
    groups: dict[str, list[tuple[Observation, Trace]]] = {}
    for pair in matches:
        groups.setdefault(pair[1].id, []).append(pair)
    # `matches` is already sorted oldest first, so the last entry in each group is that trace's newest.
    return sorted(groups.values(), key=lambda group: (group[-1][0].start_time, group[-1][0].id))


def _trace_hit(route: str, group: list[tuple[Observation, Trace]], now: datetime, detail: str) -> RuleHit:
    trace = group[-1][1]
    observations = [obs for obs, _ in group]
    return RuleHit(
        rule="silent_error",
        route=route,
        trace_id=trace.id,
        observation_ids=[obs.id for obs in observations],
        cost_usd=round(sum(obs.cost_usd for obs in observations), 6),
        at=now,
        detail=detail,
    )
