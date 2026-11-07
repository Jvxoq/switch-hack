from __future__ import annotations

import random
import statistics
from datetime import timedelta

import pytest

from tests.fakes.clock import DEFAULT_START
from tests.fakes.traces import make_trace
from tripwire.rules.cost_spike import CostSpikeRule, _median_excluding

NOW = DEFAULT_START
RECENT = NOW - timedelta(minutes=10)


def _cost_trace(cost: float, *, start=RECENT, route: str = "order-lookup", running: bool = False, trace_id=None):
    return make_trace(
        route=route,
        calls=[("generation", {}, {}, "DEFAULT", cost)],
        running=running,
        start=start,
        trace_id=trace_id,
    )


def _baseline(cost: float, count: int = 5, *, start=RECENT, route: str = "order-lookup"):
    return [_cost_trace(cost, start=start, route=route, trace_id=f"base-{route}-{start.isoformat()}-{i}")
            for i in range(count)]


def _fired_ids(hits):
    return {hit.trace_id for hit in hits}


def test_T4_five_x_median_fires(cfg):
    candidate = _cost_trace(0.50, trace_id="candidate")
    hits = CostSpikeRule().evaluate(_baseline(0.10) + [candidate], cfg.rules, NOW)
    assert _fired_ids(hits) == {"candidate"}
    hit = hits[0]
    assert hit.rule == "cost_spike" and hit.route == "order-lookup"
    assert hit.cost_usd == 0.50 and hit.at == NOW


def test_T4_four_point_nine_x_median_does_not_fire(cfg):
    candidate = _cost_trace(0.49, trace_id="candidate")
    hits = CostSpikeRule().evaluate(_baseline(0.10) + [candidate], cfg.rules, NOW)
    assert hits == []


def test_T4_one_dollar_fires_with_no_baseline(cfg):
    candidate = _cost_trace(1.00, trace_id="candidate")
    hits = CostSpikeRule().evaluate([candidate], cfg.rules, NOW)
    assert _fired_ids(hits) == {"candidate"}


def test_T4_under_one_dollar_with_no_baseline_does_not_fire(cfg):
    candidate = _cost_trace(0.99, trace_id="candidate")
    assert CostSpikeRule().evaluate([candidate], cfg.rules, NOW) == []


def test_T4_multiplier_needs_five_baseline_traces(cfg):
    # Four baseline traces at $0.10 and a $0.60 candidate: 6x the median, but no median check on fewer than 5.
    candidate = _cost_trace(0.60, trace_id="candidate")
    assert CostSpikeRule().evaluate(_baseline(0.10, count=4) + [candidate], cfg.rules, NOW) == []


def test_T4_candidate_is_excluded_from_its_own_baseline(cfg):
    # Five traces at $0.10 plus one $0.50 trace: median of the other five is still $0.10, so the $0.50 fires.
    candidate = _cost_trace(0.50, trace_id="candidate")
    hits = CostSpikeRule().evaluate(_baseline(0.10) + [candidate], cfg.rules, NOW)
    assert "candidate" in _fired_ids(hits)


def test_T4_baseline_only_counts_the_last_hour(cfg):
    old = NOW - timedelta(hours=2)
    # Five old $0.01 traces are outside the hour, so the baseline is empty and $0.50 does not fire.
    candidate = _cost_trace(0.50, trace_id="candidate")
    assert CostSpikeRule().evaluate(_baseline(0.01, start=old) + [candidate], cfg.rules, NOW) == []


def test_T4_baseline_is_per_route(cfg):
    other_route = _baseline(0.01, route="other-route")
    candidate = _cost_trace(0.50, trace_id="candidate")
    # The five cheap traces belong to another route, so this route has no baseline.
    assert CostSpikeRule().evaluate(other_route + [candidate], cfg.rules, NOW) == []


def test_T4_zero_median_does_not_make_every_paid_trace_a_spike(cfg):
    candidate = _cost_trace(0.20, trace_id="candidate")
    assert CostSpikeRule().evaluate(_baseline(0.0) + [candidate], cfg.rules, NOW) == []


def test_T4_running_trace_judged_on_cost_so_far(cfg):
    running = _cost_trace(1.20, running=True, trace_id="running")
    hits = CostSpikeRule().evaluate([running], cfg.rules, NOW)
    assert _fired_ids(hits) == {"running"}
    assert hits[0].cost_usd == 1.20


_MEDIAN_LISTS = [
    [],
    [1.0],
    [1.0, 2.0],
    [1.0, 2.0, 3.0],
    [0.1, 0.2, 0.3, 0.4],
    [0.1, 0.1, 0.1, 0.5, 0.5],
    [0.0, 0.0, 0.2, 0.2, 0.2, 0.9],
]


@pytest.mark.parametrize(
    "costs,skip_index",
    [(costs, skip) for costs in _MEDIAN_LISTS for skip in [None, *range(len(costs))]],
)
def test_median_excluding_matches_statistics(costs, skip_index):
    remaining = costs if skip_index is None else costs[:skip_index] + costs[skip_index + 1:]
    expected = statistics.median(remaining) if remaining else None
    assert _median_excluding(costs, skip_index) == expected


def _brute_force_detail(cost, baseline_median, count, over_absolute, per_trace_usd):
    # Same text as the rule's _detail, with the old hardcoded "need 5".
    parts = [f"trace cost ${cost:.2f}"]
    if baseline_median is not None:
        parts.append(f"baseline median ${baseline_median:.2f} over {count} traces in the last hour")
    else:
        parts.append(f"baseline has {count} traces in the last hour (need 5 for a median check)")
    if over_absolute:
        parts.append(f"at or above the ${per_trace_usd:.2f} per-trace limit")
    return "; ".join(parts)


def _brute_force_hits(traces, cfg, now):
    # The old algorithm: rescan every trace for each candidate.
    rule_cfg = cfg.cost_spike
    cutoff = now - timedelta(hours=1)
    out = []
    for trace in traces:
        baseline = [
            other.total_cost_usd
            for other in traces
            if other.id != trace.id
            and other.route == trace.route
            and cutoff <= other.start_time <= now
        ]
        cost = trace.total_cost_usd
        over_absolute = cost >= rule_cfg.per_trace_usd - 1e-9
        over_median = False
        baseline_median = None
        if len(baseline) >= 5:
            baseline_median = statistics.median(baseline)
            over_median = baseline_median > 0 and cost >= rule_cfg.median_multiplier * baseline_median - 1e-9
        if not (over_absolute or over_median):
            continue
        detail = _brute_force_detail(cost, baseline_median, len(baseline), over_absolute, rule_cfg.per_trace_usd)
        out.append((trace.id, cost, detail))
    return out


def test_rule_matches_bruteforce_on_random_window(cfg):
    rng = random.Random(1234)
    cost_choices = [0.02, 0.05, 0.10, 0.10, 0.10, 0.25, 0.30, 0.50, 0.60, 0.90]
    traces = []
    for i in range(300):
        route = rng.choice(["route-a", "route-b"])
        if rng.random() < 0.7:
            cost = rng.choice(cost_choices)
        else:
            cost = round(rng.uniform(0.0, 1.5), 2)
        # Up to 150 minutes old, so some traces fall outside the one-hour window.
        start = NOW - timedelta(minutes=rng.randint(0, 150))
        traces.append(_cost_trace(cost, start=start, route=route, trace_id=f"t{i}"))

    expected = _brute_force_hits(traces, cfg.rules, NOW)
    assert expected, "random window should fire at least one hit"
    hits = CostSpikeRule().evaluate(traces, cfg.rules, NOW)
    assert [(h.trace_id, h.cost_usd, h.detail) for h in hits] == expected
