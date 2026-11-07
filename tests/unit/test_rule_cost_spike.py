from __future__ import annotations

from datetime import timedelta

from tests.fakes.clock import DEFAULT_START
from tests.fakes.traces import make_trace
from tripwire.rules.cost_spike import CostSpikeRule

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
