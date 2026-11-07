"""IncidentManager: one incident per (rule, route), alerts, and the queue. Uses the containment and Switch fakes."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from tests.fakes.clock import DEFAULT_START
from tests.fakes.containment import FakeContainment
from tests.fakes.switch import FakeSwitch
from tripwire.contracts.models import Observation, RuleHit, Trace
from tripwire.detector.incidents import IncidentManager
from tripwire.rules.silent_error import SilentErrorRule


def make_hit(trace_id: str, *, rule: str = "loop", route: str = "order-lookup", cost: float = 0.5) -> RuleHit:
    return RuleHit(
        rule=rule,
        route=route,
        trace_id=trace_id,
        observation_ids=[f"{trace_id}-o0"],
        cost_usd=cost,
        at=DEFAULT_START,
        detail="test hit",
    )


@pytest.fixture
def env(cfg, clock):
    containment = FakeContainment(clock, cfg)
    switch = FakeSwitch()
    manager = IncidentManager(containment, switch, clock)
    return containment, switch, manager, clock


def test_T5_fifty_looping_traces_one_incident_count_50(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit(f"t{i}") for i in range(50)])

    incidents = containment.list(open_only=True)
    assert len(incidents) == 1
    assert incidents[0].hit_count == 50
    assert incidents[0].cost_usd == pytest.approx(25.0)
    assert len(switch.alerts) == 1


def test_T5_rolling_window_repeated_each_poll_is_not_double_counted(env):
    containment, switch, manager, clock = env
    window = [make_hit(f"t{i}") for i in range(5)]
    manager.ingest(window)
    clock.advance(seconds=15)
    manager.ingest(window)
    manager.ingest(window)

    incident = containment.list(open_only=True)[0]
    assert incident.hit_count == 5
    assert len(switch.alerts) == 1
    assert len(switch.status_updates) == 0


def test_T5_new_traces_on_open_incident_update_status_not_a_new_thread(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("t0")])
    manager.ingest([make_hit("t0"), make_hit("t1")])

    incident = containment.list(open_only=True)[0]
    assert incident.hit_count == 2
    assert incident.trace_ids == ["t0", "t1"]
    assert len(switch.alerts) == 1
    assert len(switch.status_updates) == 1
    assert switch.status_updates[0]["thread_ref"] == incident.thread_ref


def test_T6_different_rule_on_same_route_gets_separate_incident(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("t0", rule="loop"), make_hit("t1", rule="silent_error")])

    incidents = containment.list(open_only=True)
    assert sorted(i.rule for i in incidents) == ["loop", "silent_error"]
    assert all(i.route == "order-lookup" for i in incidents)
    assert len(switch.alerts) == 2


def test_T6_closed_incident_does_not_absorb_new_hits(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("t0")])
    first = containment.list(open_only=True)[0]
    containment.update(first.id, state="investigating")
    containment.update(first.id, state="handed_off")

    manager.ingest([make_hit("t9")])

    open_now = containment.list(open_only=True)
    assert len(open_now) == 1
    assert open_now[0].id != first.id
    assert open_now[0].trace_ids == ["t9"]


def test_T7_alert_has_incident_rule_trace_cost_and_tripwire(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("trace-abc", cost=2.25)])

    text = switch.alerts[0]["text"]
    incident = containment.list(open_only=True)[0]
    assert switch.alerts[0]["incident_id"] == "INC-1"
    assert "INC-1" in text
    assert "loop" in text
    assert "trace-abc" in text
    assert "$2.25" in text
    assert "@tripwire" in text
    assert incident.thread_ref == switch.alerts[0]["thread_ref"]


def test_queued_second_incident_waits_behind_busy_one(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("t0", rule="loop")])
    containment.update("INC-1", state="investigating")

    manager.ingest([make_hit("t1", rule="silent_error")])

    queued = {i.id: i for i in containment.list(open_only=True)}["INC-2"]
    assert queued.state == "queued"
    assert "INC-1" in switch.alerts[1]["text"]
    assert "Queued" in switch.alerts[1]["text"]
    # Queued incidents are still the same thread: the alert is the one place they say so.
    assert queued.thread_ref == switch.alerts[1]["thread_ref"]


def test_queued_oldest_is_nudged_once_when_busy_incident_clears(env):
    containment, switch, manager, clock = env
    manager.ingest([make_hit("t0", rule="loop")])
    containment.update("INC-1", state="investigating")

    manager.ingest([make_hit("t1", rule="silent_error")])
    clock.advance(minutes=1)
    manager.ingest([make_hit("t2", rule="cost_spike")])
    assert {i.id: i.state for i in containment.list(open_only=True)} == {
        "INC-1": "investigating",
        "INC-2": "queued",
        "INC-3": "queued",
    }

    containment.update("INC-1", state="handed_off")
    manager.ingest([])
    manager.ingest([])

    assert len(switch.replies) == 1
    assert switch.replies[0]["thread_ref"] == containment.get("INC-2").thread_ref
    assert "@tripwire" in switch.replies[0]["text"]
    assert "INC-2" in switch.replies[0]["text"]


def test_queued_nudge_waits_while_another_incident_is_awaiting_approval(env):
    containment, switch, manager, _ = env
    manager.ingest([make_hit("t0", rule="loop")])
    containment.update("INC-1", state="investigating")
    containment.update("INC-1", state="awaiting_approval")
    manager.ingest([make_hit("t1", rule="silent_error")])

    manager.ingest([])
    assert switch.replies == []

    containment.update("INC-1", state="handed_off")
    manager.ingest([])
    assert len(switch.replies) == 1
    assert switch.replies[0]["thread_ref"] == containment.get("INC-2").thread_ref


def test_queued_nudge_goes_to_oldest_first(env):
    containment, switch, manager, clock = env
    manager.ingest([make_hit("t0", rule="loop")])
    containment.update("INC-1", state="investigating")
    manager.ingest([make_hit("t1", rule="silent_error")])
    clock.advance(minutes=2)
    manager.ingest([make_hit("t2", rule="cost_spike")])

    containment.update("INC-1", state="handed_off")
    manager.ingest([])

    assert [r["thread_ref"] for r in switch.replies] == [containment.get("INC-2").thread_ref]


class NoThreadIdSwitch(FakeSwitch):
    """Switch posts the alert but returns no thread id."""

    def post_alert(self, incident, text):
        super().post_alert(incident, text)
        return None


def test_missing_thread_id_alerts_once(cfg, clock):
    containment = FakeContainment(clock, cfg)
    switch = NoThreadIdSwitch()
    manager = IncidentManager(containment, switch, clock)

    for poll in range(1, 5):
        manager.ingest([make_hit(f"t{i}") for i in range(poll)])
        clock.advance(seconds=15)

    assert len(switch.alerts) == 1
    incident = containment.list(open_only=True)[0]
    assert incident.hit_count == 4


class FlakyAlertSwitch(FakeSwitch):
    """Switch fails the first alert post, then works."""

    def __init__(self) -> None:
        super().__init__()
        self._failed_once = False

    def post_alert(self, incident, text):
        if not self._failed_once:
            self._failed_once = True
            raise RuntimeError("switch unavailable")
        return super().post_alert(incident, text)


def test_failed_alert_retries_next_poll(cfg, clock):
    containment = FakeContainment(clock, cfg)
    switch = FlakyAlertSwitch()
    manager = IncidentManager(containment, switch, clock)

    assert manager.ingest([make_hit("t0")]) == ["ingest failed for loop on order-lookup"]
    clock.advance(seconds=15)
    manager.ingest([make_hit("t0"), make_hit("t1")])

    assert len(switch.alerts) == 1
    incident = containment.list(open_only=True)[0]
    assert incident.thread_ref == "thread-1"
    assert incident.thread_ref == switch.alerts[0]["thread_ref"]


def test_silent_error_cost_counted_once(cfg, env):
    containment, switch, manager, clock = env
    rule = SilentErrorRule()
    traces: list[Trace] = []
    for i in range(5):
        start = DEFAULT_START + timedelta(seconds=i)
        obs = Observation(
            id=f"t{i}-o0",
            trace_id=f"t{i}",
            type="span",
            name="lookup_order",
            input={"order_id": f"D-{i}"},
            output="order not found",
            level="DEFAULT",
            start_time=start,
            cost_usd=1.0,
        )
        traces.append(
            Trace(
                id=f"t{i}",
                name="order-lookup-run",
                route="order-lookup",
                thread_id=None,
                start_time=start,
                end_time=start + timedelta(seconds=1),
                total_cost_usd=1.0,
                observations=[obs],
            )
        )
        clock.set(start)
        manager.ingest(rule.evaluate(traces, cfg.rules, start))

    incidents = containment.list(open_only=True)
    assert len(incidents) == 1
    assert incidents[0].cost_usd == 5.0
    assert incidents[0].trace_ids == ["t0", "t1", "t2", "t3", "t4"]


class LoopOpenFailsContainment(FakeContainment):
    """Opening an incident for rule "loop" raises. Every other call is the real fake."""

    def open_incident(self, rule, route, opened_at):
        if rule == "loop":
            raise RuntimeError("boom")
        return super().open_incident(rule, route, opened_at)


def test_failing_group_does_not_stop_others(cfg, clock, caplog):
    containment = LoopOpenFailsContainment(clock, cfg)
    switch = FakeSwitch()
    manager = IncidentManager(containment, switch, clock)

    with caplog.at_level(logging.ERROR):
        events = manager.ingest([make_hit("t0", rule="loop"), make_hit("t1", rule="silent_error")])

    assert events == ["ingest failed for loop on order-lookup"]
    [incident] = containment.list(open_only=True)
    assert incident.rule == "silent_error"
    assert incident.route == "order-lookup"
    assert len(switch.alerts) == 1
    assert switch.alerts[0]["incident_id"] == incident.id
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.getMessage() for r in error_records] == ["ingest failed for loop on order-lookup"]
