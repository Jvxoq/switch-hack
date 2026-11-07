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
    traces = [
        make_trace(trace_id=tid, calls=[SILENT], start=_at(m), running=False)
        for tid, m in (("a", 4), ("b", 2), ("c", 0))
    ]
    hits = _evaluate(traces, cfg)
    assert [h.trace_id for h in hits] == ["a", "b", "c"]
    assert [h.observation_ids for h in hits] == [["a-o0"], ["b-o0"], ["c-o0"]]
    assert all(h.rule == "silent_error" and h.route == "order-lookup" and h.at == NOW for h in hits)
    assert [h.cost_usd for h in hits] == [0.01, 0.01, 0.01]
    assert hits[0].detail == (
        "3 silent errors on route order-lookup in the last 5 minutes (threshold 3)"
    )


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
    traces = [
        make_trace(trace_id=tid, route="order-lookup", calls=[SILENT], start=_at(m), running=True)
        for tid, m in (("t0", 3), ("t1", 2), ("t2", 1))
    ]
    hits = _evaluate(traces, cfg)
    assert [h.trace_id for h in hits] == ["t0", "t1", "t2"]
    assert all(len(h.observation_ids) == 1 for h in hits)
    assert [h.cost_usd for h in hits] == [0.01, 0.01, 0.01]


def test_T3_one_trace_with_three_silent_errors_is_one_hit_with_all_three(cfg):
    burst = ("span", {}, "order not found", "DEFAULT", 0.02)
    trace = make_trace(trace_id="burst", calls=[burst, burst, burst], start=_at(2), running=False)
    other = make_trace(trace_id="other", calls=[SILENT], start=_at(0), running=False)
    hits = _evaluate([trace, other], cfg)
    assert [h.trace_id for h in hits] == ["burst", "other"]
    assert hits[0].observation_ids == ["burst-o0", "burst-o1", "burst-o2"]
    assert hits[0].cost_usd == round(0.06, 6)
    assert hits[1].observation_ids == ["other-o0"]
    assert hits[1].cost_usd == round(0.01, 6)


def test_T3_matching_is_case_insensitive_and_checks_every_pattern(cfg):
    upper_not_found = ("span", {}, "NOT FOUND", "WARNING", 0.0)
    no_pattern = ("span", {}, "all good here", "DEFAULT", 0.0)
    mixed_error = ("span", {}, "Some ERROR text", "DEFAULT", 0.0)
    traces = [
        make_trace(trace_id="m2", calls=[upper_not_found], start=_at(2), running=False),
        make_trace(trace_id="ok", calls=[no_pattern], start=_at(1), running=False),
        make_trace(trace_id="m0", calls=[upper_not_found], start=_at(0), running=False),
    ]
    # Only two observations match the default patterns, so no hit yet.
    assert _evaluate(traces, cfg) == []
    # A third match, using the other default pattern in mixed case, fires one hit per matching trace.
    traces.append(make_trace(trace_id="m05", calls=[mixed_error], start=_at(0.5), running=False))
    assert [h.trace_id for h in _evaluate(traces, cfg)] == ["m2", "m05", "m0"]


def test_T3_ignores_observations_outside_window_and_after_now(cfg):
    future = make_trace(calls=[SILENT], start=NOW + timedelta(minutes=1), running=False)
    old = make_trace(calls=[SILENT], start=_at(5.5), running=False)
    recent = [make_trace(calls=[SILENT], start=_at(m), running=False) for m in (2, 1)]
    assert _evaluate([future, old, *recent], cfg) == []


def test_T3_hits_per_trace_and_routes_are_counted_separately(cfg):
    a = [
        make_trace(trace_id=f"a{m}", route="order-lookup", calls=[SILENT], start=_at(m), running=False)
        for m in (2, 1, 0)
    ]
    b = [
        make_trace(trace_id=f"b{m}", route="refunds", calls=[SILENT], start=_at(m), running=False)
        for m in (2, 1)
    ]
    hits = _evaluate([*a, *b], cfg)
    assert [(h.route, h.trace_id) for h in hits] == [
        ("order-lookup", "a2"),
        ("order-lookup", "a1"),
        ("order-lookup", "a0"),
    ]


def test_T3_rule_satisfies_rule_protocol():
    assert isinstance(SilentErrorRule(), Rule)
