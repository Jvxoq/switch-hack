from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from tests.fakes.clock import DEFAULT_START
from tests.fakes.containment import FakeContainment
from tests.fakes.switch import FakeSwitch
from tests.fakes.traces import make_trace
from tripwire.contracts.config import RouteConfig, TripwireConfig
from tripwire.contracts.models import Incident, RuleHit
from tripwire.contracts.ports import ContainmentRefused
from tripwire.detector.autopause import AutoPause, run_autopause

ROUTE = "order-lookup"
MODULE_LOGGER = "tripwire.detector.autopause"


class SpyContainment(FakeContainment):
    """Records every apply call, accepted or refused, and can refuse on demand."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.apply_calls: list[dict] = []
        self.refuse_with: str | None = None

    def apply(self, incident_id, action, source, approver, spend_usd):
        self.apply_calls.append(
            {"incident_id": incident_id, "action": action, "source": source, "spend_usd": spend_usd}
        )
        if self.refuse_with is not None:
            raise ContainmentRefused(self.refuse_with)
        return super().apply(incident_id, action, source, approver, spend_usd)

    def auto_pause_calls(self) -> list[dict]:
        return [call for call in self.apply_calls if call["source"] == "auto_pause"]


class FlakySwitch(FakeSwitch):
    """Fails the reply on the first thread, as Switch would when its API is down."""

    def reply(self, thread_ref: str, text: str) -> None:
        if thread_ref == "thread-1":
            raise RuntimeError("Switch is down")
        super().reply(thread_ref, text)


class IngestFake:
    """Stands in for IncidentManager.ingest: opens the incident, posts its alert, stores the thread."""

    def __init__(self, containment: FakeContainment, switch: FakeSwitch, clock) -> None:
        self._containment = containment
        self._switch = switch
        self._clock = clock
        self.hits: list[RuleHit] = []

    def __call__(self, hit: RuleHit) -> Incident:
        self.hits.append(hit)
        inc = self._containment.open_incident(hit.rule, hit.route, hit.at)
        thread = self._switch.post_alert(inc, f"{hit.rule} on {hit.route}")
        return self._containment.update(
            inc.id, thread_ref=thread, trace_ids=[hit.trace_id], cost_usd=hit.cost_usd
        )


@pytest.fixture
def spy(clock, cfg: TripwireConfig) -> SpyContainment:
    return SpyContainment(clock, cfg)


def _trace(cost: float, *, trace_id: str = "t1", start=DEFAULT_START, route: str = ROUTE):
    return make_trace(
        route=route,
        calls=[("span", {}, {}, "DEFAULT", cost)],
        running=False,
        start=start,
        trace_id=trace_id,
    )


def _open_incident(containment, switch, clock, *, rule: str = "loop", trace_ids=("t1",)) -> Incident:
    """An open incident with its Switch thread, as the IncidentManager leaves it after ingest."""
    inc = containment.open_incident(rule, ROUTE, clock.now())
    thread = switch.post_alert(inc, f"{rule} on {ROUTE}")
    return containment.update(inc.id, trace_ids=list(trace_ids), thread_ref=thread)


def test_T8_fires_at_half_budget(spy, switch, clock, cfg, caplog) -> None:
    """Spend at half the $50 loss budget pauses the route before the incident is 10 minutes old."""
    caplog.set_level(logging.DEBUG, logger=MODULE_LOGGER)
    inc = _open_incident(spy, switch, clock, trace_ids=["t1"])

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(25.0)], ingest=IngestFake(spy, switch, clock)
    )

    assert paused == [AutoPause(incident_id=inc.id, route=ROUTE, spend_usd=25.0)]
    assert spy.get(inc.id).state == "auto_paused"
    assert spy.flags()["routes"][ROUTE]["disabled"] is True
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == []


def test_T8_fires_at_ten_minutes(spy, switch, clock, cfg) -> None:
    """An incident that is 10 minutes old is paused even with no spend."""
    inc = _open_incident(spy, switch, clock, trace_ids=())
    clock.advance(minutes=10)

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[], ingest=IngestFake(spy, switch, clock)
    )

    assert paused == [AutoPause(incident_id=inc.id, route=ROUTE, spend_usd=0.0)]
    assert spy.auto_pause_calls() == [
        {"incident_id": inc.id, "action": "disable_route", "source": "auto_pause", "spend_usd": 0.0}
    ]


def test_T8_not_at_9m59s_or_24_99(spy, switch, clock, cfg) -> None:
    """Just under both thresholds, nothing is paused and no apply is sent."""
    inc = _open_incident(spy, switch, clock, trace_ids=["t1"])
    clock.advance(minutes=9, seconds=59)

    paused = run_autopause(
        containment=spy,
        switch=switch,
        clock=clock,
        cfg=cfg,
        traces=[_trace(24.99)],
        ingest=IngestFake(spy, switch, clock),
    )

    assert paused == []
    assert spy.auto_pause_calls() == []
    assert spy.get(inc.id).state == "detected"


def test_T8_owner_action_skips_incident(spy, switch, clock, cfg) -> None:
    """An incident with an owner's action in force is not auto-paused, even far over budget."""
    inc = _open_incident(spy, switch, clock, trace_ids=["t1"])
    spy.update(inc.id, state="investigating")
    spy.update(inc.id, state="awaiting_approval")
    spy.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    clock.advance(minutes=30)

    paused = run_autopause(
        containment=spy,
        switch=switch,
        clock=clock,
        cfg=cfg,
        traces=[_trace(40.0)],
        ingest=IngestFake(spy, switch, clock),
    )

    assert paused == []
    assert spy.auto_pause_calls() == []
    assert spy.get(inc.id).action_source == "owner"


def test_T8_auto_pauses_once_per_incident(spy, switch, clock, cfg) -> None:
    """After an auto-pause is reverted, the same incident is not auto-paused again."""
    inc = _open_incident(spy, switch, clock, trace_ids=["t1"])
    run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(25.0)], ingest=IngestFake(spy, switch, clock)
    )
    spy.revert(inc.id, "jason")

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(40.0)], ingest=IngestFake(spy, switch, clock)
    )

    assert paused == []
    assert len(spy.auto_pause_calls()) == 1


def test_T8_refusal_logs_reason_and_stops(spy, switch, clock, cfg, caplog) -> None:
    """A refused auto-pause is logged with the reason and then nothing else happens."""
    caplog.set_level(logging.WARNING, logger=MODULE_LOGGER)
    inc = _open_incident(spy, switch, clock, rule="loop", trace_ids=["t1"])
    spy.refuse_with = "auto-pause thresholds not reached"

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(25.0)], ingest=IngestFake(spy, switch, clock)
    )

    assert paused == []
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "auto-pause refused for INC-1: auto-pause thresholds not reached")
    ]
    assert switch.replies == []
    assert spy.get(inc.id).state == "detected"


def test_T8_one_failed_reply_keeps_other_pauses(clock, cfg, caplog) -> None:
    """A Switch failure on one incident's reply does not stop the other incident's pause."""
    caplog.set_level(logging.ERROR, logger=MODULE_LOGGER)
    containment = FakeContainment(clock, cfg)
    switch = FlakySwitch()
    _open_incident(containment, switch, clock, rule="loop", trace_ids=["t1"])
    _open_incident(containment, switch, clock, rule="silent_error", trace_ids=["t1"])

    paused = run_autopause(
        containment=containment,
        switch=switch,
        clock=clock,
        cfg=cfg,
        traces=[_trace(25.0)],
        ingest=IngestFake(containment, switch, clock),
    )

    assert [p.incident_id for p in paused] == ["INC-1", "INC-2"]
    assert [containment.get(i).state for i in ("INC-1", "INC-2")] == ["auto_paused", "auto_paused"]
    assert [r["thread_ref"] for r in switch.replies] == ["thread-2"]
    assert [(r.levelname, r.getMessage(), r.exc_info is not None) for r in caplog.records] == [
        ("ERROR", "revert offer failed for INC-1; the route stays paused", True)
    ]


def test_T9_ceiling_pauses_with_zero_hits(spy, switch, clock, cfg) -> None:
    """A route at its $50 hourly ceiling is paused with no rule hit, on the incident ingest opened."""
    ingest = IngestFake(spy, switch, clock)

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(50.0)], ingest=ingest
    )

    assert [(h.rule, h.route, h.cost_usd) for h in ingest.hits] == [("hourly_ceiling", ROUTE, 50.0)]
    assert paused == [AutoPause(incident_id="INC-1", route=ROUTE, spend_usd=50.0)]
    assert spy.get("INC-1").state == "auto_paused"
    assert spy.flags()["routes"][ROUTE]["disabled"] is True


def test_T9_ceiling_alert_has_revert_offer(spy, switch, clock, cfg) -> None:
    """The ceiling incident gets an alert thread, and the revert offer goes on that thread."""
    run_autopause(
        containment=spy,
        switch=switch,
        clock=clock,
        cfg=cfg,
        traces=[_trace(50.0)],
        ingest=IngestFake(spy, switch, clock),
    )

    assert [a["incident_id"] for a in switch.alerts] == ["INC-1"]
    assert [r["thread_ref"] for r in switch.replies] == [switch.alerts[0]["thread_ref"]]
    assert "`revert INC-1`" in switch.replies[0]["text"]


def test_T9_below_ceiling_no_hit(spy, switch, clock, cfg) -> None:
    """Spend just under the $50 ceiling raises no hit and pauses nothing."""
    ingest = IngestFake(spy, switch, clock)

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[_trace(49.99)], ingest=ingest
    )

    assert ingest.hits == []
    assert paused == []
    assert spy.auto_pause_calls() == []


def test_T9_ceiling_hit_once_while_open(spy, switch, clock, cfg) -> None:
    """While the ceiling incident is open, later polls in the same hour send no new hit."""
    ingest = IngestFake(spy, switch, clock)
    traces = [_trace(50.0)]
    run_autopause(containment=spy, switch=switch, clock=clock, cfg=cfg, traces=traces, ingest=ingest)

    run_autopause(containment=spy, switch=switch, clock=clock, cfg=cfg, traces=traces, ingest=ingest)

    assert len(ingest.hits) == 1


def test_T9_spend_older_than_hour_ignored(spy, switch, clock, cfg) -> None:
    """A $50 trace from over an hour ago does not count toward the $50 ceiling next to a $10 fresh trace."""
    ingest = IngestFake(spy, switch, clock)
    old = _trace(50.0, trace_id="old", start=DEFAULT_START - timedelta(minutes=61))
    fresh = _trace(10.0, trace_id="fresh")

    paused = run_autopause(
        containment=spy, switch=switch, clock=clock, cfg=cfg, traces=[old, fresh], ingest=ingest
    )

    assert ingest.hits == []
    assert paused == []


def test_T8_spend_counts_only_incident_traces(spy, switch, clock, cfg) -> None:
    """An incident's spend is its own traces only: another trace on the route does not push it over half budget."""
    inc = _open_incident(spy, switch, clock, trace_ids=["t1"])

    paused = run_autopause(
        containment=spy,
        switch=switch,
        clock=clock,
        cfg=cfg,
        traces=[_trace(10.0, trace_id="t1"), _trace(30.0, trace_id="t2")],
        ingest=IngestFake(spy, switch, clock),
    )

    assert paused == []
    assert spy.get(inc.id).state == "detected"


def test_T9_ceiling_applies_below_half_budget(spy, switch, clock, cfg) -> None:
    """A ceiling under half the loss budget is itself the trigger: the pause is sent at the ceiling's spend."""
    low = cfg.model_copy(update={"routes": {ROUTE: RouteConfig(loss_budget_usd=50, hourly_ceiling_usd=10)}})
    ingest = IngestFake(spy, switch, clock)

    run_autopause(containment=spy, switch=switch, clock=clock, cfg=low, traces=[_trace(10.0)], ingest=ingest)

    assert [h.cost_usd for h in ingest.hits] == [10.0]
    assert spy.auto_pause_calls() == [
        {"incident_id": "INC-1", "action": "disable_route", "source": "auto_pause", "spend_usd": 10.0}
    ]
