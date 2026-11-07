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

from datetime import datetime, timedelta
from statistics import median

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
        hits: list[RuleHit] = []
        for trace in traces:
            baseline = [
                other.total_cost_usd
                for other in traces
                if other.id != trace.id
                and other.route == trace.route
                and cutoff <= other.start_time <= now
            ]
            cost = trace.total_cost_usd
            over_absolute = cost >= rule_cfg.per_trace_usd - _EPSILON
            over_median = False
            baseline_median: float | None = None
            if len(baseline) >= MIN_BASELINE_TRACES:
                baseline_median = median(baseline)
                over_median = baseline_median > 0 and cost >= rule_cfg.median_multiplier * baseline_median - _EPSILON
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
                    detail=_detail(cost, baseline_median, len(baseline), over_absolute, rule_cfg.per_trace_usd),
                )
            )
        return hits


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
        parts.append(f"baseline has {baseline_count} traces in the last hour (need 5 for a median check)")
    if over_absolute:
        parts.append(f"at or above the ${per_trace_usd:.2f} per-trace limit")
    return "; ".join(parts)
