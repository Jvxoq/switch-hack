from __future__ import annotations

import logging
from datetime import timedelta

from tests.fakes.clock import DEFAULT_START, FakeClock
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.traces import make_trace
from tripwire.detector.window import TraceWindow
from tripwire.langfuse_client import LangfuseError

CALL = ("span", {"q": 1}, {"ok": True}, "DEFAULT", 0.01, "lookup")


class SpyLangfuse(FakeLangfuse):
    """FakeLangfuse that records every recent_traces `since` and every get_trace id."""

    def __init__(self, traces=()) -> None:
        super().__init__(traces)
        self.since_calls: list = []
        self.get_calls: list[str] = []

    def recent_traces(self, since):
        self.since_calls.append(since)
        return super().recent_traces(since)

    def get_trace(self, trace_id):
        self.get_calls.append(trace_id)
        return super().get_trace(trace_id)


class FailingLangfuse(SpyLangfuse):
    """SpyLangfuse that raises `errors[trace_id]` on every get_trace for that id."""

    def __init__(self, traces=(), errors=None) -> None:
        super().__init__(traces)
        self.errors: dict[str, Exception] = errors or {}

    def get_trace(self, trace_id):
        self.get_calls.append(trace_id)
        if trace_id in self.errors:
            raise self.errors[trace_id]
        return FakeLangfuse.get_trace(self, trace_id)


def test_running_trace_picks_up_new_observations_on_next_refresh():
    clock = FakeClock()
    reader = FakeLangfuse()
    start = clock.now()
    reader.put(make_trace(calls=[CALL] * 4, running=True, start=start, trace_id="t1"))
    window = TraceWindow(reader, clock)

    first = window.refresh()
    assert [len(t.observations) for t in first] == [4]

    clock.advance(seconds=15)
    reader.put(make_trace(calls=[CALL] * 5, running=True, start=start, trace_id="t1"))
    second = window.refresh()

    assert len(second) == 1
    assert len(second[0].observations) == 5


def test_trace_that_started_before_last_poll_is_seen_on_next_refresh():
    clock = FakeClock()
    reader = FakeLangfuse()
    window = TraceWindow(reader, clock)
    window.refresh()

    # Started 10 s before the next poll, so it is inside the 30 s overlap.
    clock.advance(seconds=5)
    reader.put(make_trace(calls=[CALL], running=True, start=clock.now() - timedelta(seconds=10), trace_id="late"))
    clock.advance(seconds=15)

    assert [t.id for t in window.refresh()] == ["late"]


def test_traces_older_than_the_window_are_dropped():
    clock = FakeClock()
    reader = FakeLangfuse()
    reader.put(make_trace(calls=[CALL], running=True, start=clock.now(), trace_id="old-running"))
    window = TraceWindow(reader, clock, minutes=60)
    assert [t.id for t in window.refresh()] == ["old-running"]

    clock.advance(minutes=61)
    assert window.refresh() == []


def test_trace_exactly_at_the_window_edge_is_kept():
    clock = FakeClock()
    reader = FakeLangfuse()
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now() - timedelta(minutes=60), trace_id="edge"))
    window = TraceWindow(reader, clock, minutes=60)

    assert [t.id for t in window.refresh()] == ["edge"]


def test_finished_trace_is_not_refetched():
    clock = FakeClock()
    reader = SpyLangfuse()
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="done"))
    window = TraceWindow(reader, clock)

    window.refresh()
    clock.advance(seconds=15)
    window.refresh()
    clock.advance(seconds=15)
    window.refresh()

    assert "done" not in reader.get_calls


def test_running_trace_is_refetched_each_refresh_until_it_finishes():
    clock = FakeClock()
    reader = SpyLangfuse()
    start = clock.now()
    reader.put(make_trace(calls=[CALL], running=True, start=start, trace_id="live"))
    window = TraceWindow(reader, clock)
    window.refresh()

    clock.advance(seconds=15)
    window.refresh()
    assert reader.get_calls == ["live"]

    reader.put(make_trace(calls=[CALL], running=False, start=start, trace_id="live"))
    clock.advance(seconds=15)
    final = window.refresh()
    assert final[0].end_time is not None

    clock.advance(seconds=15)
    window.refresh()
    assert reader.get_calls == ["live", "live"]


def test_first_refresh_asks_for_the_full_window_then_polls_with_overlap():
    clock = FakeClock()
    reader = SpyLangfuse()
    window = TraceWindow(reader, clock, minutes=60)

    window.refresh()
    clock.advance(seconds=15)
    window.refresh()

    assert reader.since_calls[0] == DEFAULT_START - timedelta(minutes=60)
    # last_poll is the first refresh's time (DEFAULT_START), so the second poll asks from 30 s before it.
    assert reader.since_calls[1] == DEFAULT_START - timedelta(seconds=30)


def test_refresh_returns_the_full_window_not_only_new_traces():
    clock = FakeClock()
    reader = FakeLangfuse()
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="first"))
    window = TraceWindow(reader, clock)
    window.refresh()

    clock.advance(minutes=2)
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="second"))
    traces = window.refresh()

    assert [t.id for t in traces] == ["first", "second"]


def test_custom_window_length_is_respected():
    clock = FakeClock()
    reader = FakeLangfuse()
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="t"))
    window = TraceWindow(reader, clock, minutes=10)
    window.refresh()

    clock.advance(minutes=11)
    assert window.refresh() == []


def test_deleted_running_trace_is_dropped(caplog):
    clock = FakeClock()
    reader = FailingLangfuse()
    reader.put(make_trace(calls=[CALL], running=True, start=clock.now() - timedelta(seconds=60), trace_id="gone"))
    window = TraceWindow(reader, clock)
    window.refresh()

    # The old trace starts before the poll overlap, so recent_traces skips it and only get_trace can reach it.
    clock.advance(seconds=60)
    reader.errors["gone"] = LangfuseError("trace not found", status_code=404)
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="new"))

    with caplog.at_level(logging.WARNING, logger="tripwire.detector.window"):
        traces = window.refresh()

    assert [t.id for t in traces] == ["new"]
    records = [r for r in caplog.records if r.name == "tripwire.detector.window"]
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (logging.WARNING, "trace gone is gone from Langfuse; dropped from the window"),
    ]

    clock.advance(seconds=15)
    assert [t.id for t in window.refresh()] == ["new"]
    assert reader.get_calls.count("gone") == 1


def test_refresh_error_keeps_cached_trace(caplog):
    clock = FakeClock()
    reader = FailingLangfuse()
    reader.put(make_trace(calls=[CALL], running=True, start=clock.now() - timedelta(seconds=60), trace_id="live"))
    window = TraceWindow(reader, clock)
    window.refresh()

    # The old trace starts before the poll overlap, so recent_traces skips it and only get_trace can reach it.
    clock.advance(seconds=60)
    reader.errors["live"] = LangfuseError("langfuse unavailable", status_code=503)
    reader.put(make_trace(calls=[CALL], running=False, start=clock.now(), trace_id="new"))

    with caplog.at_level(logging.WARNING, logger="tripwire.detector.window"):
        traces = window.refresh()

    assert [t.id for t in traces] == ["live", "new"]
    records = [r for r in caplog.records if r.name == "tripwire.detector.window"]
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (logging.WARNING, "could not refresh running trace live; keeping the cached copy"),
    ]

    clock.advance(seconds=15)
    window.refresh()
    assert reader.get_calls == ["live", "live"]
