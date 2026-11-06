"""Silent-error rule (R02).

An observation is a silent error when its output matches any configured pattern (case-insensitive substring)
while its level is not ERROR. The rule fires once per route when `count` silent errors fall inside a sliding
window of `window_minutes` that ends at `now`. The window is measured on observation start times and spans all
traces passed in, so a burst split across several traces still fires.

The hit cites every silent-error observation in the window, `trace_id` is the trace of the newest one, and
`cost_usd` is the summed cost of the cited observations.
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
            newest_obs, newest_trace = matches[-1]
            cited = [obs for obs, _ in matches]
            hits.append(
                RuleHit(
                    rule="silent_error",
                    route=route,
                    trace_id=newest_trace.id,
                    observation_ids=[obs.id for obs in cited],
                    cost_usd=round(sum(obs.cost_usd for obs in cited), 6),
                    at=now,
                    detail=(
                        f"{len(cited)} silent errors on route {route} in the last "
                        f"{settings.window_minutes:g} minutes (threshold {settings.count})"
                    ),
                )
            )
        return hits


rule = SilentErrorRule()
