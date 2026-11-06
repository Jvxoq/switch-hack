"""Trace fixture builder: `make_trace(route=..., calls=[...], running=True, start=...)`."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta

from tests.fakes.clock import DEFAULT_START
from tripwire.contracts.models import Observation, Trace

_counter = itertools.count(1)


def make_trace(
    *,
    route: str = "order-lookup",
    calls: list[tuple] | tuple = (),
    running: bool = True,
    start: datetime | None = None,
    trace_id: str | None = None,
    name: str = "order-lookup-run",
    thread_id: str | None = None,
) -> Trace:
    """Build a Trace. Each call is `(type, input, output, level, cost_usd)` or `(..., name)` as a 6th item.

    Observations start one second apart from `start`. A finished trace ends one second after its last observation.
    """
    start = start or DEFAULT_START
    trace_id = trace_id or f"trace-{next(_counter)}"
    observations: list[Observation] = []
    for index, call in enumerate(calls):
        if len(call) not in (5, 6):
            raise ValueError(f"call must be (type, input, output, level, cost[, name]), got {call!r}")
        obs_type, obs_input, obs_output, level, cost = call[:5]
        obs_name = call[5] if len(call) == 6 else obs_type
        observations.append(
            Observation(
                id=f"{trace_id}-o{index}",
                trace_id=trace_id,
                type=obs_type,
                name=obs_name,
                input=obs_input,
                output=obs_output,
                level=level,
                start_time=start + timedelta(seconds=index),
                cost_usd=float(cost),
            )
        )
    end_time = None if running else start + timedelta(seconds=len(calls) + 1)
    return Trace(
        id=trace_id,
        name=name,
        route=route,
        thread_id=thread_id,
        start_time=start,
        end_time=end_time,
        total_cost_usd=round(sum(o.cost_usd for o in observations), 6),
        observations=observations,
    )
