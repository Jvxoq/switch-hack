from __future__ import annotations

from tests.fakes.clock import DEFAULT_START
from tests.fakes.traces import make_trace
from tripwire.rules.loop import LoopRule

NOW = DEFAULT_START
SEARCH = ("tool", {"q": "Order 42"}, "ok", "DEFAULT", 0.01, "search_orders")
LIST_PAGE = ("tool", {"page": 1}, "ok", "DEFAULT", 0.0, "list_orders_page")


def _evaluate(traces, cfg):
    return LoopRule().evaluate(traces, cfg.rules, NOW)


def test_T1_loop_fires_at_5_not_4(cfg):
    four = make_trace(calls=[SEARCH] * 4, running=True)
    assert _evaluate([four], cfg) == []

    five = make_trace(calls=[SEARCH] * 5, running=True)
    hits = _evaluate([five], cfg)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.rule == "loop" and hit.route == "order-lookup" and hit.trace_id == five.id
    assert hit.observation_ids == [o.id for o in five.observations]
    assert hit.cost_usd == round(0.05, 6)


def test_T1_repeat_check_ignores_case_whitespace_and_key_order(cfg):
    variants = [
        ("tool", {"q": "Order 42", "limit": 3}, "ok", "DEFAULT", 0.0, "search_orders"),
        ("tool", {"limit": 3, "q": "order   42"}, "ok", "DEFAULT", 0.0, "search_orders"),
        ("tool", '{"q": "ORDER 42", "limit": 3}', "ok", "DEFAULT", 0.0, "search_orders"),
        ("tool", {"q": "order\n42", "limit": 3}, "ok", "DEFAULT", 0.0, "search_orders"),
        ("tool", {"limit": 3, "q": "order 42"}, "ok", "DEFAULT", 0.0, "search_orders"),
    ]
    hits = _evaluate([make_trace(calls=variants)], cfg)
    assert len(hits) == 1
    assert len(hits[0].observation_ids) == 5


def test_T1_different_inputs_or_tool_names_do_not_count_as_repeats(cfg):
    calls = [
        ("tool", {"q": f"Order {i}"}, "ok", "DEFAULT", 0.0, "search_orders") for i in range(10)
    ] + [
        ("tool", {"q": "Order 1"}, "ok", "DEFAULT", 0.0, "other_tool") for _ in range(4)
    ]
    assert _evaluate([make_trace(calls=calls)], cfg) == []


def test_T2_allow_listed_list_orders_page_does_not_fire(cfg):
    trace = make_trace(calls=[LIST_PAGE] * 10)
    assert _evaluate([trace], cfg) == []


def test_T2_allow_list_is_configurable_through_the_constructor(cfg):
    trace = make_trace(calls=[LIST_PAGE] * 5)
    hits = LoopRule(allow_list_tools=()).evaluate([trace], cfg.rules, NOW)
    assert len(hits) == 1


def test_26_reworded_calls_fire_through_observation_cap(cfg):
    reworded = [
        ("tool", {"q": f"find order number {i} please"}, "ok", "DEFAULT", 0.0, "search_orders")
        for i in range(26)
    ]
    trace = make_trace(calls=reworded)
    hits = _evaluate([trace], cfg)
    assert len(hits) == 1
    assert len(hits[0].observation_ids) == 26
    assert "cap 25" in hits[0].detail


def test_25_reworded_calls_do_not_fire(cfg):
    reworded = [
        ("tool", {"q": f"find order number {i} please"}, "ok", "DEFAULT", 0.0, "search_orders")
        for i in range(25)
    ]
    assert _evaluate([make_trace(calls=reworded)], cfg) == []


def test_repeats_are_judged_per_trace_not_across_traces(cfg):
    traces = [make_trace(calls=[SEARCH] * 3) for _ in range(3)]
    assert _evaluate(traces, cfg) == []


def test_hit_cost_covers_only_repeated_observations(cfg):
    calls = [SEARCH] * 5 + [("tool", {"q": "other"}, "ok", "DEFAULT", 9.0, "search_orders")]
    hits = _evaluate([make_trace(calls=calls)], cfg)
    assert len(hits) == 1
    assert hits[0].cost_usd == round(0.05, 6)
