"""The detector loop over the in-memory fakes and a fake clock. No network, no real sleep."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from tests.fakes.clock import DEFAULT_START, FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.switch import FakeSwitch
from tests.fakes.traces import make_trace
from tripwire import records
from tripwire.contracts.config import ConfigError, TripwireConfig, load_config_dict
from tripwire.contracts.models import Incident, RuleHit, Trace
from tripwire.detector.main import (
    Detector,
    default_rules,
    make_reader,
    resolve_langfuse_host,
    resolve_records_path,
    run,
)
from tripwire.langfuse_client import LangfuseError

ROUTE = "order-lookup"
SEARCH = ("tool", {"q": "Order 42"}, "ok", "DEFAULT", 0.01, "search_orders")
PAGE = ("tool", {"page": 1}, "ok", "DEFAULT", 0.0, "list_orders_page")


def build(
    cfg: TripwireConfig,
    clock: FakeClock,
    *,
    reader: object | None = None,
    rules: list | None = None,
    write_record=None,
    records_path: Path | None = None,
    containment: FakeContainment | None = None,
    switch: FakeSwitch | None = None,
) -> tuple[Detector, FakeLangfuse, FakeContainment, FakeSwitch]:
    """A detector over the fakes. With `records_path`, records go to a real JSONL file, as in production.

    Pass `containment` and `switch` to start a second detector over the same service and Switch, as a restart does.
    """
    langfuse = FakeLangfuse() if reader is None else reader
    containment = FakeContainment(clock, cfg) if containment is None else containment
    switch = FakeSwitch() if switch is None else switch
    if records_path is None:
        recorded = set
        default_write = lambda inc: f"record {inc.id}"
    else:
        recorded = lambda: records.recorded_ids(records_path)
        default_write = file_writer(records_path)
    detector = Detector(
        cfg=cfg,
        reader=langfuse,  # type: ignore[arg-type]
        containment=containment,
        switch=switch,
        clock=clock,
        rules=default_rules(cfg) if rules is None else rules,
        write_record=write_record or default_write,
        recorded_ids=recorded,
    )
    return detector, langfuse, containment, switch


def file_writer(path: Path):
    """The production record writer: append the record to the JSONL file, then return the thread text."""

    def write_record(inc: Incident) -> str:
        records.append(inc, path)
        return f"record {inc.id}"

    return write_record


def record_ids_in(path: Path) -> list[str]:
    """Incident ids in the record log, one per line, in file order."""
    return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()]


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


def test_restart_after_handoff_records_once(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path
) -> None:
    """The hand-off happened while the detector was down. The restarted detector writes its record once."""
    path = tmp_path / "incidents.log"
    detector, langfuse, containment, switch = build(cfg, clock, records_path=path)
    langfuse.put(
        make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now())
    )
    detector.poll()
    inc = loop_incident(containment)
    agent_asks_owner(containment, inc.id)
    containment.update(inc.id, state="handed_off")  # detector is down; no poll sees this

    restarted, _, _, _ = build(
        cfg, clock, reader=langfuse, containment=containment, switch=switch, records_path=path
    )
    restarted.poll()
    restarted.poll()

    assert record_ids_in(path) == [inc.id]
    assert [r["text"] for r in switch.replies].count(f"record {inc.id}") == 1


def test_restart_does_not_rewrite_recorded_handoff(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path
) -> None:
    """The record was written before the restart. Another start, and polls after it, add nothing."""
    path = tmp_path / "incidents.log"
    detector, langfuse, containment, switch = build(cfg, clock, records_path=path)
    langfuse.put(
        make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now())
    )
    detector.poll()
    inc = loop_incident(containment)
    agent_asks_owner(containment, inc.id)
    containment.update(inc.id, state="handed_off")
    detector.poll()
    assert record_ids_in(path) == [inc.id]

    for _ in range(2):
        restarted, _, _, _ = build(
            cfg, clock, reader=langfuse, containment=containment, switch=switch, records_path=path
        )
        restarted.poll()
        restarted.poll()

    assert record_ids_in(path) == [inc.id]
    assert [r["text"] for r in switch.replies].count(f"record {inc.id}") == 1


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


def test_langfuse_host_comes_from_config_without_env(cfg: TripwireConfig) -> None:
    assert resolve_langfuse_host(cfg, {}) == "http://localhost:3000"
    assert resolve_langfuse_host(cfg, {"LANGFUSE_HOST": ""}) == "http://localhost:3000"


def test_langfuse_host_env_overrides_config(cfg: TripwireConfig) -> None:
    assert resolve_langfuse_host(cfg, {"LANGFUSE_HOST": "http://langfuse:3000"}) == "http://langfuse:3000"


def test_records_flag_overrides_config_path(cfg: TripwireConfig) -> None:
    assert resolve_records_path(None, cfg) == "incident-records.md"
    assert resolve_records_path("/var/log/records.jsonl", cfg) == "/var/log/records.jsonl"


def test_config_refuses_empty_langfuse_host() -> None:
    with pytest.raises(ConfigError, match="langfuse_host"):
        load_config_dict({"langfuse_host": ""})


def test_config_file_sets_records_path_and_host(cfg: TripwireConfig) -> None:
    assert (cfg.langfuse_host, cfg.records_path) == ("http://localhost:3000", "incident-records.md")


class FlakyContainment(FakeContainment):
    """Fails reopen for one route and open for another. Every other call is the real fake."""

    def __init__(self, clock, cfg, *, reopen_fails_on: str | None = None, open_fails_on: str | None = None):
        super().__init__(clock, cfg)
        self._reopen_fails_on = reopen_fails_on
        self._open_fails_on = open_fails_on

    def reopen(self, incident_id: str) -> Incident:
        if self.get(incident_id).route == self._reopen_fails_on:
            raise RuntimeError(f"containment broke reopening {incident_id}")
        return super().reopen(incident_id)

    def open_incident(self, rule: str, route: str, opened_at) -> Incident:
        if route == self._open_fails_on:
            raise RuntimeError(f"containment broke opening on route {route}")
        return super().open_incident(rule, route, opened_at)


def test_failing_observe_does_not_stop_next_incident(
    cfg: TripwireConfig, clock: FakeClock, caplog
) -> None:
    """Two verifying incidents get new hits in one poll. The first one's reopen fails, the second still reopens."""
    containment = FlakyContainment(clock, cfg, reopen_fails_on=ROUTE)
    detector, langfuse, containment, _ = build(cfg, clock, containment=containment)
    other = "other-route"
    langfuse.put(make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()))
    detector.poll()
    first = loop_incident(containment)
    agent_asks_owner(containment, first.id)
    containment.apply(first.id, "cap_max_steps", "owner", "jason", 0.0)
    detector.poll()
    assert containment.get(first.id).state == "verifying"

    langfuse.put(make_trace(trace_id="loop-2", route=other, calls=[SEARCH] * 5, running=True, start=clock.now()))
    detector.poll()
    [second] = [i for i in containment.list(open_only=False) if i.route == other]
    agent_asks_owner(containment, second.id)
    containment.apply(second.id, "cap_max_steps", "owner", "jason", 0.0)
    detector.poll()
    assert containment.get(second.id).state == "verifying"

    langfuse.put(make_trace(trace_id="loop-3", calls=[SEARCH] * 5, running=True, start=clock.now()))
    langfuse.put(make_trace(trace_id="loop-4", route=other, calls=[SEARCH] * 5, running=True, start=clock.now()))
    with caplog.at_level(logging.ERROR):
        events = detector.poll()

    assert f"observe failed for {first.id}" in events
    assert containment.get(second.id).state == "awaiting_approval"
    assert containment.get(second.id).ask_round == 2
    assert "observe failed for " + first.id in caplog.text


def test_failing_ingest_does_not_stop_next_incident(
    cfg: TripwireConfig, clock: FakeClock, caplog
) -> None:
    """The broken route's trace comes first in the window. Its open fails, and the healthy route still opens."""
    containment = FlakyContainment(clock, cfg, open_fails_on="broken-route")
    detector, langfuse, containment, _ = build(cfg, clock, containment=containment)
    langfuse.put(make_trace(trace_id="broken-1", route="broken-route", calls=[SEARCH] * 5, running=True, start=clock.now()))
    langfuse.put(make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()))

    with caplog.at_level(logging.ERROR):
        events = detector.poll()

    assert "ingest failed for loop on broken-route" in events
    assert loop_incident(containment).route == ROUTE
    assert "ingest failed for loop on broken-route" in caplog.text


def test_failing_ingest_leaves_verify_running(
    cfg: TripwireConfig, clock: FakeClock
) -> None:
    """A failing ingest does not stop verify: the contained incident still advances to verifying."""
    containment = FlakyContainment(clock, cfg, open_fails_on="broken-route")
    detector, langfuse, containment, _ = build(cfg, clock, containment=containment)
    langfuse.put(make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=True, start=clock.now()))
    detector.poll()
    inc = loop_incident(containment)
    agent_asks_owner(containment, inc.id)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    langfuse.put(make_trace(trace_id="broken-1", route="broken-route", calls=[SEARCH] * 5, running=True, start=clock.now()))
    langfuse.put(make_trace(trace_id="loop-1", calls=[SEARCH] * 5, running=False, start=DEFAULT_START))

    events = detector.poll()

    assert "ingest failed for loop on broken-route" in events
    assert containment.get(inc.id).state == "verifying"


def test_default_page_cap_comes_from_config(cfg: TripwireConfig) -> None:
    assert cfg.langfuse_max_pages == 100


def test_page_cap_must_be_positive() -> None:
    with pytest.raises(ConfigError, match="langfuse_max_pages"):
        load_config_dict({"langfuse_max_pages": 0})


def test_configured_page_cap_reaches_langfuse_client() -> None:
    """The reader the detector builds reads at most `langfuse_max_pages` pages, then fails loudly."""
    cfg = load_config_dict({"langfuse_max_pages": 2})
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.params["page"])
        return httpx.Response(200, json={"data": [], "meta": {"totalPages": 1000}})

    reader = make_reader(
        cfg, "https://langfuse.test", "pk", "sk", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LangfuseError, match="more than 2 pages"):
        reader.recent_traces(DEFAULT_START)

    assert requested == ["1", "2"]
