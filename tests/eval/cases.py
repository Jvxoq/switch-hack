"""Recorded incidents and eval cases for the Tripwire agent (A03).

Each fixture is one JSON file in `tests/fixtures/incidents/`. It holds the traces the fake Langfuse serves and the
incident the fake containment opens. The agent under test reads them through the MCP tool server in `mcp_server.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tripwire.contracts.models import Observation, Trace

REPO_ROOT = Path(__file__).resolve().parents[2]
INCIDENT_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "incidents"


@dataclass(frozen=True)
class IncidentFixture:
    stem: str
    description: str
    rule: str
    route: str
    incident_id: str
    opened_at: datetime
    trigger_trace_id: str
    traces: tuple[Trace, ...]

    def observation_ids(self) -> frozenset[str]:
        return frozenset(obs.id for trace in self.traces for obs in trace.observations)


@dataclass(frozen=True)
class EvalCase:
    """One row of the eval table: a fixture plus how the run is driven."""

    name: str
    fixture: str
    slow_tools: bool = False
    injection: bool = False


EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase("loop", "loop_order_lookup"),
    EvalCase("silent_error", "silent_error_order_lookup"),
    EvalCase("cost_spike", "cost_spike_order_lookup"),
    EvalCase("injection", "injection_order_lookup", injection=True),
    EvalCase("loop_slow_tools", "loop_order_lookup", slow_tools=True),
)


def case_by_name(name: str) -> EvalCase:
    for case in EVAL_CASES:
        if case.name == name:
            return case
    raise KeyError(f"unknown eval case {name!r}")


def _observation(data: dict[str, Any]) -> Observation:
    return Observation(
        id=data["id"],
        trace_id=data["trace_id"],
        type=data["type"],
        name=data["name"],
        input=data["input"],
        output=data["output"],
        level=data["level"],
        start_time=datetime.fromisoformat(data["start_time"]),
        cost_usd=float(data["cost_usd"]),
    )


def _trace(data: dict[str, Any]) -> Trace:
    end_time = data["end_time"]
    return Trace(
        id=data["id"],
        name=data["name"],
        route=data["route"],
        thread_id=data["thread_id"],
        start_time=datetime.fromisoformat(data["start_time"]),
        end_time=None if end_time is None else datetime.fromisoformat(end_time),
        total_cost_usd=float(data["total_cost_usd"]),
        observations=[_observation(item) for item in data["observations"]],
    )


def fixture_from_dict(data: dict[str, Any], stem: str) -> IncidentFixture:
    return IncidentFixture(
        stem=stem,
        description=data["description"],
        rule=data["rule"],
        route=data["route"],
        incident_id=data["incident_id"],
        opened_at=datetime.fromisoformat(data["opened_at"]),
        trigger_trace_id=data["trigger_trace_id"],
        traces=tuple(_trace(item) for item in data["traces"]),
    )


def load_fixture(stem: str) -> IncidentFixture:
    text = (INCIDENT_FIXTURES / f"{stem}.json").read_text(encoding="utf-8")
    return fixture_from_dict(json.loads(text), stem)
