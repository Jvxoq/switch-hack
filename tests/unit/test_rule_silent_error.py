from __future__ import annotations

from datetime import timedelta

from tests.fakes.clock import DEFAULT_START
from tests.fakes.traces import make_trace
from tripwire.contracts.ports import Rule
from tripwire.rules.silent_error import SilentErrorRule

NOW = DEFAULT_START + timedelta(minutes=10)
SILENT = ("span", {"q": "x"}, "Error: order not found", "DEFAULT", 0.01)


def _at(minutes_before_now: float) -> object:
    return NOW - timedelta(minutes=minutes_before_now)


def _evaluate(traces, cfg):
    return SilentErrorRule().evaluate(traces, cfg.rules, NOW)


def test_T3_three_silent_errors_in_five_minutes_fire(cfg):
    traces = [make_trace(calls=[SILENT], start=_at(m), running=False) for m in (4, 2, 0)]
    hits = _evaluate(traces, cfg)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.rule == "silent_error" and hit.route == "order-lookup" and hit.at == NOW
    assert len(hit.observation_ids) == 3
    assert hit.cost_usd == round(0.03, 6)


def test_T3_two_silent_errors_do_not_fire(cfg):
    traces = [make_trace(calls=[SILENT], start=_at(m), running=False) for m in (2, 0)]
    assert _evaluate(traces, cfg) == []


def test_T3_three_silent_errors_spread_over_six_minutes_do_not_fire(cfg):
    traces = [make_trace(calls=[SILENT], start=_at(m), running=False) for m in (6, 3, 0)]
    assert _evaluate(traces, cfg) == []


def test_T3_error_level_does_not_count(cfg):
    error_level = ("span", {}, "Error: order not found", "ERROR", 0.01)
    traces = [make_trace(calls=[error_level], start=_at(m), running=False) for m in (2, 1, 0)]
    assert _evaluate(traces, cfg) == []


def test_T3_three_silent_errors_across_three_traces_fire(cfg):
    traces = [make_trace(route="order-lookup", calls=[SILENT], start=_at(m), running=True) for m in (3, 2, 1)]
    hits = _evaluate(traces, cfg)
    assert len(hits) == 1
    assert len(hits[0].observation_ids) == 3
    assert hits[0].trace_id == traces[-1].id


def test_T3_matching_is_case_insensitive_and_checks_every_pattern(cfg):
    upper_not_found = ("span", {}, "NOT FOUND", "WARNING", 0.0)
    no_pattern = ("span", {}, "all good here", "DEFAULT", 0.0)
    mixed_error = ("span", {}, "Some ERROR text", "DEFAULT", 0.0)
    traces = [
        make_trace(calls=[upper_not_found], start=_at(2), running=False),
        make_trace(calls=[no_pattern], start=_at(1), running=False),
        make_trace(calls=[upper_not_found], start=_at(0), running=False),
    ]
    # Only two observations match the default patterns, so no hit yet.
    assert _evaluate(traces, cfg) == []
    # A third match, using the other default pattern in mixed case, fires.
    traces.append(make_trace(calls=[mixed_error], start=_at(0.5), running=False))
    assert len(_evaluate(traces, cfg)) == 1


def test_T3_ignores_observations_outside_window_and_after_now(cfg):
    future = make_trace(calls=[SILENT], start=NOW + timedelta(minutes=1), running=False)
    old = make_trace(calls=[SILENT], start=_at(5.5), running=False)
    recent = [make_trace(calls=[SILENT], start=_at(m), running=False) for m in (2, 1)]
    assert _evaluate([future, old, *recent], cfg) == []


def test_T3_one_hit_per_route_and_routes_are_counted_separately(cfg):
    a = [make_trace(route="order-lookup", calls=[SILENT], start=_at(m), running=False) for m in (2, 1, 0)]
    b = [make_trace(route="refunds", calls=[SILENT], start=_at(m), running=False) for m in (2, 1)]
    hits = _evaluate([*a, *b], cfg)
    assert [h.route for h in hits] == ["order-lookup"]


def test_T3_rule_satisfies_rule_protocol():
    assert isinstance(SilentErrorRule(), Rule)
