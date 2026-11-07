"""Rolling trace window: the full last-N-minutes view that every rule judges (decision #2)."""

from __future__ import annotations

from datetime import timedelta

from tripwire.contracts.models import Trace
from tripwire.contracts.ports import Clock, LangfuseReader

# Overlap between polls so a trace that started just before the last poll is not missed.
POLL_OVERLAP = timedelta(seconds=30)


class TraceWindow:
    """Keeps the traces of the last `minutes` and refreshes them on every call to `refresh()`.

    - New traces come from `reader.recent_traces(last_poll - 30 s)`.
    - Cached running traces are re-fetched with `reader.get_trace(id)`, so a trace that was running at the
      last poll is judged with its latest observations.
    - Finished traces are never re-fetched.
    - Traces that started more than `minutes` ago are dropped.
    """

    def __init__(self, reader: LangfuseReader, clock: Clock, minutes: float = 60) -> None:
        self._reader = reader
        self._clock = clock
        self._window = timedelta(minutes=minutes)
        self._last_poll = None
        self._traces: dict[str, Trace] = {}

    def refresh(self) -> list[Trace]:
        now = self._clock.now()
        cutoff = now - self._window

        since = cutoff if self._last_poll is None else self._last_poll - POLL_OVERLAP
        fresh = [t for t in self._reader.recent_traces(since) if t.start_time >= cutoff]

        for trace_id, cached in list(self._traces.items()):
            if cached.end_time is None:
                self._traces[trace_id] = self._reader.get_trace(trace_id)

        for trace in fresh:
            self._traces[trace.id] = trace

        for trace_id, trace in list(self._traces.items()):
            if trace.start_time < cutoff:
                del self._traces[trace_id]

        self._last_poll = now
        return sorted(self._traces.values(), key=lambda t: t.start_time)
