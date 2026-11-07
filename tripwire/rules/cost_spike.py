"""Cost-spike rule (R03).

Per route, the baseline is the rolling median of `total_cost_usd` over traces that started in the last hour,
excluding the candidate trace itself. A trace fires when either:

- its cost is >= `median_multiplier` x median, and there are at least 5 baseline traces (the median is
  meaningless on fewer), and the median is above zero (a zero baseline would make every paid trace a "spike");
- or its cost is >= `per_trace_usd`, regardless of the baseline.

Running traces are judged on the cost they have accrued so far. The rule is a pure function of its inputs:
the detector passes the full rolling window and `now`.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

from tripwire.contracts.config import RulesConfig
from tripwire.contracts.models import RuleHit, Trace

BASELINE_WINDOW = timedelta(hours=1)
MIN_BASELINE_TRACES = 5
# Float tolerance so that exactly k x median fires even when the product is not exact in binary.
_EPSILON = 1e-9


class CostSpikeRule:
    name = "cost_spike"

    def evaluate(self, traces: list[Trace], cfg: RulesConfig, now: datetime) -> list[RuleHit]:
        rule_cfg = cfg.cost_spike
        cutoff = now - BASELINE_WINDOW
        sorted_costs_by_route = _sorted_baseline_costs(traces, cutoff, now)
        hits: list[RuleHit] = []
        for trace in traces:
            route_costs = sorted_costs_by_route.get(trace.route, [])
            cost = trace.total_cost_usd
            # A candidate inside the window is one of route_costs, so its baseline drops one copy of its cost.
            eligible = cutoff <= trace.start_time <= now
            skip_index = bisect.bisect_left(route_costs, cost) if eligible else None
            baseline_count = len(route_costs) - (1 if eligible else 0)
            over_absolute = cost >= rule_cfg.per_trace_usd - _EPSILON
            over_median = False
            baseline_median: float | None = None
            if baseline_count >= MIN_BASELINE_TRACES:
                baseline_median = _median_excluding(route_costs, skip_index)
                over_median = (
                    baseline_median is not None
                    and baseline_median > 0
                    and cost >= rule_cfg.median_multiplier * baseline_median - _EPSILON
                )
            if not (over_absolute or over_median):
                continue
            hits.append(
                RuleHit(
                    rule="cost_spike",
                    route=trace.route,
                    trace_id=trace.id,
                    observation_ids=[o.id for o in trace.observations if o.cost_usd > 0],
                    cost_usd=cost,
                    at=now,
                    detail=_detail(cost, baseline_median, baseline_count, over_absolute, rule_cfg.per_trace_usd),
                )
            )
        return hits


def _sorted_baseline_costs(traces: list[Trace], cutoff: datetime, now: datetime) -> dict[str, list[float]]:
    """Per route, the sorted costs of the traces that are inside the baseline window."""
    by_route: dict[str, list[float]] = {}
    for trace in traces:
        if cutoff <= trace.start_time <= now:
            by_route.setdefault(trace.route, []).append(trace.total_cost_usd)
    for costs in by_route.values():
        costs.sort()
    return by_route


def _median_excluding(sorted_costs: list[float], skip_index: int | None) -> float | None:
    """Median of `sorted_costs` with the item at `skip_index` left out. None when nothing is left."""
    size = len(sorted_costs) - (0 if skip_index is None else 1)
    if size <= 0:
        return None

    def at(position: int) -> float:
        # Read the list as if the item at skip_index were not there. No copy is made.
        if skip_index is not None and position >= skip_index:
            return sorted_costs[position + 1]
        return sorted_costs[position]

    middle = size // 2
    if size % 2:
        return at(middle)
    return (at(middle - 1) + at(middle)) / 2


def _detail(
    cost: float,
    baseline_median: float | None,
    baseline_count: int,
    over_absolute: bool,
    per_trace_usd: float,
) -> str:
    parts = [f"trace cost ${cost:.2f}"]
    if baseline_median is not None:
        parts.append(f"baseline median ${baseline_median:.2f} over {baseline_count} traces in the last hour")
    else:
        parts.append(f"baseline has {baseline_count} traces in the last hour (need {MIN_BASELINE_TRACES} for a median check)")
    if over_absolute:
        parts.append(f"at or above the ${per_trace_usd:.2f} per-trace limit")
    return "; ".join(parts)
