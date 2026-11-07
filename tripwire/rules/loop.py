"""Loop rule (R01).

Judged within one trace, running or finished. The rule fires for a trace when either:

- the same tool name with near-identical input appears `max_repeats` times (default 5). Near-identical means
  equal after lowercasing, whitespace collapse and JSON key sorting. Tools in `allow_list_tools` are ignored
  for this check (for example a paginated `list_orders_page` called ten times is not a loop); or
- the trace has more than `max_observations` observations (default 25).

The hit cites the repeated observation IDs (for the repeat check) or every observation of the trace (for the
observation cap), `trace_id` is the trace, and `cost_usd` is the summed cost of the cited observations.

MVP limitation: reworded (paraphrased) calls are not recognised as repeats. They are caught only by the
`max_observations` cap.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from tripwire.contracts.config import RulesConfig
from tripwire.contracts.models import Observation, RuleHit, Trace


def _collapse(text: str) -> str:
    return " ".join(text.lower().split())


def _normalise_value(value: Any) -> Any:
    """Lowercase and collapse whitespace in every string, recursively, so escapes like \\n do not hide a repeat."""
    if isinstance(value, str):
        return _collapse(value)
    if isinstance(value, dict):
        return {_collapse(str(k)): _normalise_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise_value(v) for v in value]
    return value


def _normalise_input(value: Any) -> str:
    """Canonical text for near-identical comparison: JSON with sorted keys, lowercased, whitespace collapsed."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return _collapse(value)
    try:
        return json.dumps(_normalise_value(value), sort_keys=True, default=str, ensure_ascii=False,
                          separators=(",", ":"))
    except (TypeError, ValueError):
        return _collapse(str(value))


class LoopRule:
    """Implements the `Rule` protocol from `tripwire.contracts.ports`. Pure: no I/O, no clock reads.

    `allow_list_tools` is a constructor argument because `RulesConfig` does not carry it; the detector wires it
    from `TripwireConfig.allow_list_tools`.
    """

    name = "loop"

    def __init__(self, allow_list_tools: Iterable[str]) -> None:
        self._allow_list = frozenset(allow_list_tools)

    def evaluate(self, traces: list[Trace], cfg: RulesConfig, now: datetime) -> list[RuleHit]:
        settings = cfg.loop
        hits: list[RuleHit] = []
        for trace in traces:
            reasons: list[str] = []
            cited: list[Observation] = []

            repeated = self._repeated_observations(trace, settings.max_repeats)
            if repeated:
                reasons.append(
                    f"{len(repeated)} near-identical repeated calls (threshold {settings.max_repeats})"
                )
                cited.extend(repeated)

            if len(trace.observations) > settings.max_observations:
                reasons.append(
                    f"{len(trace.observations)} observations in one trace (cap {settings.max_observations})"
                )
                cited = list(trace.observations)

            if not reasons:
                continue
            hits.append(
                RuleHit(
                    rule="loop",
                    route=trace.route,
                    trace_id=trace.id,
                    observation_ids=[obs.id for obs in cited],
                    cost_usd=round(sum(obs.cost_usd for obs in cited), 6),
                    at=now,
                    detail="; ".join(reasons),
                )
            )
        return hits

    def _repeated_observations(self, trace: Trace, max_repeats: int) -> list[Observation]:
        """Observations of every tool/input group that reaches `max_repeats`, in trace order."""
        groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
        for obs in trace.observations:
            if obs.name in self._allow_list:
                continue
            groups[(obs.name, _normalise_input(obs.input))].append(obs)
        repeated = [obs for group in groups.values() if len(group) >= max_repeats for obs in group]
        return sorted(repeated, key=lambda obs: (obs.start_time, obs.id))
