"""In-memory LangfuseReader. `put` adds a trace or a new version of one; reads return the latest version."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from tripwire.contracts.models import Trace


class FakeLangfuse:
    def __init__(self, traces: list[Trace] | tuple[Trace, ...] = ()) -> None:
        self._order: list[str] = []
        self._versions: dict[str, list[Trace]] = {}
        for trace in traces:
            self.put(trace)

    def put(self, trace: Trace) -> None:
        if trace.id not in self._versions:
            self._order.append(trace.id)
            self._versions[trace.id] = []
        self._versions[trace.id].append(deepcopy(trace))

    def recent_traces(self, since: datetime) -> list[Trace]:
        return [
            deepcopy(self._versions[tid][-1])
            for tid in self._order
            if self._versions[tid][-1].start_time >= since
        ]

    def get_trace(self, trace_id: str) -> Trace:
        if trace_id not in self._versions:
            raise KeyError(f"unknown trace {trace_id}")
        return deepcopy(self._versions[trace_id][-1])
