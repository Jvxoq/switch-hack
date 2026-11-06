"""The detector loop over the in-memory fakes and a fake clock. No network, no real sleep."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from tests.fakes.clock import DEFAULT_START, FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.switch import FakeSwitch
from tests.fakes.traces import make_trace
from tripwire.contracts.config import TripwireConfig, load_config_dict
from tripwire.contracts.models import Incident, RuleHit, Trace
from tripwire.detector.main import Detector, default_rules, main, run

ROUTE = "order-lookup"
REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH = ("tool", {"q": "Order 42"}, "ok", "DEFAULT", 0.01, "search_orders")
PAGE = ("tool", {"page": 1}, "ok", "DEFAULT", 0.0, "list_orders_page")


def build(
    cfg: TripwireConfig,
    clock: FakeClock,
    *,
    reader: object | None = None,
    rules: list | None = None,
    write_record=None,
) -> tuple[Detector, FakeLangfuse, FakeContainment, FakeSwitch]:
    langfuse = FakeLangfuse() if reader is None else reader
    containment = FakeContainment(clock, cfg)
    switch = FakeSwitch()
    detector = Detector(
        cfg=cfg,
        reader=langfuse,  # type: ignore[arg-type]
        containment=containment,
        switch=switch,
        clock=clock,
        rules=default_rules(cfg) if rules is None else rules,
        write_record=write_record or (lambda inc: f"record {inc.id}"),
    )
    return detector, langfuse, containment, switch


def loop_incident(containment: FakeContainment) -> Incident:
    [inc] = [i for i in containment.list(open_only=False) if i.rule == "loop"]
    return inc


def agent_asks_owner(containment: FakeContainment, incident_id: str) -> None:
    """Stands in for the Tripwire agent: investigate, then ask the owner."""
    containment.update(incident_id, state="investigating")
    containment.update(incident_id, state="awaiting_approval")


def test_owner_cap_resolves_after_quiet_period(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    detector, langfuse, containment, switch = build(cfg, clock)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 4, running=True, start=clock.now()
        )
    )
    detector.poll()
    assert containment.list(open_only=False) == []

    clock.advance(seconds=15)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=DEFAULT_START
        )
    )
    detector.poll()
    inc = loop_incident(containment)
    assert (inc.rule, inc.route) == ("loop", ROUTE)
    agent_asks_owner(containment, inc.id)

    clock.advance(seconds=15)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    clock.advance(seconds=15)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=False, start=DEFAULT_START
        )
    )
    detector.poll()
    assert containment.get(inc.id).state == "verifying"

    for _ in range(19):
        clock.advance(seconds=15)
        detector.poll()
    assert containment.get(inc.id).state == "verifying"

    clock.advance(seconds=15)
    detector.poll()
    assert containment.get(inc.id).state == "resolved"
    assert switch.replies[-1]["text"] == f"record {inc.id}"


def test_no_owner_reply_auto_pauses_at_ten_minutes(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    detector, langfuse, containment, _ = build(cfg, clock)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()
        )
    )
    detector.poll()
    inc = loop_incident(containment)
    opened = inc.opened_at
    limit = opened + timedelta(minutes=10)

    clock.advance(seconds=60)
    detector.poll()
    assert containment.get(inc.id).state != "auto_paused"

    while clock.now() < limit - timedelta(seconds=15):
        clock.advance(seconds=15)
        detector.poll()
        assert containment.get(inc.id).state != "auto_paused"
    clock.advance(seconds=15)
    detector.poll()

    paused = containment.get(inc.id)
    assert (paused.state, paused.auto_paused) == ("auto_paused", True)
    assert containment.flags()["routes"][ROUTE]["disabled"] is True


def test_budget_fraction_pauses_before_ten_minutes(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    detector, langfuse, containment, _ = build(cfg, clock)
    expensive = ("tool", {"q": "x"}, "ok", "DEFAULT", 5.0, "search_orders")
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[expensive] * 5, running=True, start=clock.now()
        )
    )

    detector.poll()

    inc = loop_incident(containment)
    assert inc.state == "auto_paused"
    assert clock.now() - inc.opened_at < timedelta(minutes=10)


def test_hourly_ceiling_incident_pauses_route(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    detector, langfuse, containment, _ = build(cfg, clock)
    spend = ("tool", {"q": "y"}, "ok", "DEFAULT", 30.0, "search_orders")
    langfuse.put(
        make_trace(trace_id="spend-1", calls=[spend], running=False, start=clock.now())
    )
    langfuse.put(
        make_trace(trace_id="spend-2", calls=[spend], running=False, start=clock.now())
    )

    detector.poll()

    [ceiling] = [
        i for i in containment.list(open_only=False) if i.rule == "hourly_ceiling"
    ]
    assert ceiling.state == "auto_paused"
    assert containment.flags()["routes"][ROUTE]["disabled"] is True


def test_ceiling_pause_refused_before_ten_minutes_is_retried(
    clock: FakeClock, caplog
) -> None:
    """A ceiling below half the loss budget: the detector says due, the service refuses until 10 minutes."""
    cfg = load_config_dict(
        {"routes": {ROUTE: {"loss_budget_usd": 50, "hourly_ceiling_usd": 10}}}
    )
    detector, langfuse, containment, _ = build(cfg, clock)
    spend = ("tool", {"q": "y"}, "ok", "DEFAULT", 12.0, "search_orders")
    langfuse.put(
        make_trace(trace_id="spend-1", calls=[spend], running=False, start=clock.now())
    )

    with caplog.at_level(logging.WARNING, logger="tripwire.detector.autopause"):
        detector.poll()

    [ceiling] = [
        i for i in containment.list(open_only=False) if i.rule == "hourly_ceiling"
    ]
    assert ceiling.state != "auto_paused"
    assert (
        f"auto-pause refused for {ceiling.id}: auto-pause thresholds not reached"
        in caplog.text
    )

    clock.advance(seconds=600)
    detector.poll()

    assert containment.get(ceiling.id).state == "auto_paused"


def test_reopens_when_loop_fires_again_while_verifying(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    detector, langfuse, containment, _ = build(cfg, clock)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()
        )
    )
    detector.poll()
    inc = loop_incident(containment)
    agent_asks_owner(containment, inc.id)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    clock.advance(seconds=15)
    detector.poll()
    assert containment.get(inc.id).state == "verifying"

    clock.advance(seconds=15)
    langfuse.put(
        make_trace(
            trace_id="loop-2", calls=[SEARCH] * 5, running=True, start=clock.now()
        )
    )
    detector.poll()

    reopened = containment.get(inc.id)
    assert (reopened.state, reopened.ask_round) == ("awaiting_approval", 2)


def test_handed_off_incident_recorded_once(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    written: list[str] = []

    def write_record(inc: Incident) -> str:
        written.append(inc.id)
        return f"record {inc.id}"

    detector, langfuse, containment, switch = build(
        cfg, clock, write_record=write_record
    )
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()
        )
    )
    detector.poll()
    inc = loop_incident(containment)
    agent_asks_owner(containment, inc.id)
    containment.update(inc.id, state="handed_off")

    detector.poll()
    detector.poll()

    assert written == [inc.id]
    assert [r["text"] for r in switch.replies].count(f"record {inc.id}") == 1


def test_handed_off_before_start_not_recorded(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    written: list[str] = []
    containment_probe = FakeContainment(clock, cfg)
    old = containment_probe.open_incident("loop", ROUTE, clock.now())
    containment_probe.update(old.id, state="investigating")
    containment_probe.update(old.id, state="awaiting_approval")
    containment_probe.update(old.id, state="handed_off")

    langfuse = FakeLangfuse()
    switch = FakeSwitch()
    detector = Detector(
        cfg=cfg,
        reader=langfuse,  # type: ignore[arg-type]
        containment=containment_probe,
        switch=switch,
        clock=clock,
        rules=default_rules(cfg),
        write_record=lambda inc: written.append(inc.id) or "record",
    )

    detector.poll()
    detector.poll()

    assert written == []


def test_failing_rule_does_not_stop_other_rules(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    class BrokenRule:
        name = "broken"

        def evaluate(self, traces: list[Trace], rules_cfg, now) -> list[RuleHit]:
            raise RuntimeError("rule broke")

    rules = [BrokenRule(), *default_rules(cfg)]
    detector, langfuse, containment, _ = build(cfg, clock, rules=rules)
    langfuse.put(
        make_trace(
            trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()
        )
    )

    events = detector.poll()

    assert "rule broken failed" in events
    assert loop_incident(containment).rule == "loop"


def test_failing_langfuse_is_logged_and_loop_keeps_polling(
    cfg: TripwireConfig, clock: FakeClock, caplog
) -> None:
    class DownLangfuse:
        def recent_traces(self, since):
            raise ConnectionError("langfuse down")

        def get_trace(self, trace_id):
            raise ConnectionError("langfuse down")

    detector, _, containment, _ = build(cfg, clock, reader=DownLangfuse())
    polls: list[float] = []

    with caplog.at_level(logging.ERROR):
        run(
            detector,
            poll_seconds=15,
            sleep=lambda s: (polls.append(s), clock.advance(seconds=s)),
            polls=3,
        )

    assert polls == [15, 15, 15]
    assert "trace refresh failed" in caplog.text
    assert containment.list(open_only=False) == []


def test_loop_survives_a_poll_that_raises(
    cfg: TripwireConfig, clock: FakeClock, caplog
) -> None:
    class FlakyDetector:
        def __init__(self) -> None:
            self.calls = 0

        def poll(self) -> list[str]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            return []

    flaky = FlakyDetector()
    sleeps: list[float] = []

    with caplog.at_level(logging.ERROR):
        run(flaky, poll_seconds=15, sleep=sleeps.append, polls=2)  # type: ignore[arg-type]

    assert flaky.calls == 2
    assert sleeps == [15, 15]
    assert "detector poll failed" in caplog.text


def test_loop_allow_list_comes_from_config(clock: FakeClock) -> None:
    page_trace = make_trace(calls=[PAGE] * 5, start=clock.now())
    default_cfg = load_config_dict({})
    free_cfg = load_config_dict({"allow_list_tools": []})

    def loop_hits(cfg: TripwireConfig) -> list[RuleHit]:
        return [
            h
            for rule in default_rules(cfg)
            for h in rule.evaluate([page_trace], cfg.rules, clock.now())
            if h.rule == "loop"
        ]

    assert loop_hits(default_cfg) == []
    assert len(loop_hits(free_cfg)) == 1


def test_main_refuses_to_start_without_langfuse_host(clock: FakeClock, caplog) -> None:
    environ = {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}

    with caplog.at_level(logging.ERROR):
        code = main(["--config", str(REPO_ROOT / "tripwire.yaml")], environ=environ)

    assert code == 2
    assert "LANGFUSE_HOST" in caplog.text
