"""Tests for the Tripwire agent's tool server and its Switch room template (A01).

The tools run against a fake containment service and a fake clock. No test opens a socket.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp import Client

from tripwire.contracts.models import Incident, Observation, Trace
from tripwire.contracts.ports import ContainmentRefused
from tripwire_agent.server import (
    APPROVAL_APPROVER,
    BUDGET_SPENT,
    CUT_MARK,
    MAX_TOOL_TEXT_CHARS,
    TripwireTools,
    build_server,
    register,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TOOL_NAMES = {
    "langfuse_read",
    "flags_read",
    "incident_read",
    "update_incident",
    "request_containment",
    "revert_containment",
}


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


class YieldingClock(FakeClock):
    """Sleeps inside the guard's critical section, so threads without the lock read the same count.

    The guard calls the clock between reading and writing the call count. The sleep lets other
    threads run there. With the lock in place they wait their turn; without it they all read 0.
    """

    def now(self) -> datetime:
        time.sleep(0.001)
        return super().now()


class FakeContainment:
    """Records every write and can refuse updates or actions with a given reason."""

    def __init__(self, *incidents: Incident) -> None:
        self.incidents = {incident.id: incident for incident in incidents}
        self.writes: list[tuple[str, str, dict[str, Any]]] = []
        self.refuse_update: ContainmentRefused | None = None
        self.refuse_apply: ContainmentRefused | None = None

    def get(self, incident_id: str) -> Incident:
        try:
            return self.incidents[incident_id]
        except KeyError:
            raise ContainmentRefused(f"unknown incident {incident_id}") from None

    def update(self, incident_id: str, **fields: Any) -> Incident:
        self.writes.append(("update", incident_id, fields))
        if self.refuse_update is not None:
            raise self.refuse_update
        incident = self.get(incident_id)
        for name, value in fields.items():
            setattr(incident, name, value)
        return incident

    def apply(
        self,
        incident_id: str,
        action: str,
        source: str,
        approver: str | None,
        spend_usd: float,
    ) -> dict[str, Any]:
        self.writes.append(
            ("apply", incident_id, {"action": action, "source": source, "approver": approver, "spend_usd": spend_usd})
        )
        if self.refuse_apply is not None:
            raise self.refuse_apply
        return {"routes": {"order-lookup": {"disabled": True}}}

    def revert(self, incident_id: str, by: str) -> dict[str, Any]:
        self.writes.append(("revert", incident_id, {"by": by}))
        return {"routes": {"order-lookup": {"disabled": False}}}

    def flags(self) -> dict[str, Any]:
        return {"routes": {"order-lookup": {"disabled": False}}}


class FakeTraces:
    def __init__(self, trace: Trace) -> None:
        self._trace = trace

    def get_trace(self, trace_id: str) -> Trace:
        return self._trace


def make_incident(incident_id: str = "INC-1") -> Incident:
    return Incident(id=incident_id, rule="loop", route="order-lookup", opened_at=T0, state="investigating", cost_usd=12.5)


def make_trace(output: str = "ok") -> Trace:
    observation = Observation(
        id="obs-1",
        trace_id="trace-1",
        type="GENERATION",
        name="model",
        input="lookup",
        output=output,
        level="DEFAULT",
        start_time=T0,
        cost_usd=0.1,
    )
    return Trace(
        id="trace-1",
        name="order-lookup",
        route="order-lookup",
        thread_id=None,
        start_time=T0,
        end_time=None,
        total_cost_usd=0.1,
        observations=[observation],
    )


@pytest.fixture
def wall_clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def service() -> FakeContainment:
    return FakeContainment(make_incident())


@pytest.fixture
def tools(service: FakeContainment, wall_clock: FakeClock) -> TripwireTools:
    return TripwireTools(service, FakeTraces(make_trace()), wall_clock)


def hand_offs(service: FakeContainment) -> list[tuple[str, str, dict[str, Any]]]:
    return [write for write in service.writes if write[2] == {"state": "handed_off"}]


def test_reads_never_write(tools: TripwireTools, service: FakeContainment) -> None:
    """Read-only tools leave the containment service untouched."""
    tools.langfuse_read("INC-1", "trace-1")
    tools.flags_read("INC-1")
    tools.incident_read("INC-1")

    assert service.writes == []


def test_unknown_incident_refusal_is_verbatim(tools: TripwireTools) -> None:
    """A read against an unknown incident returns the service's reason unchanged."""
    assert tools.flags_read("INC-9") == "unknown incident INC-9"


def test_update_refusal_is_verbatim(tools: TripwireTools, service: FakeContainment) -> None:
    """A transition the service refuses comes back word for word."""
    service.refuse_update = ContainmentRefused("illegal transition: investigating -> resolved")

    assert tools.update_incident("INC-1", state="resolved") == "illegal transition: investigating -> resolved"


def test_apply_refusal_is_verbatim(tools: TripwireTools, service: FakeContainment) -> None:
    """A containment action the service refuses comes back word for word."""
    service.refuse_apply = ContainmentRefused("a round allows one owner action")

    assert tools.request_containment("INC-1", "disable_route") == "a round allows one owner action"


def test_update_without_fields_is_refused(tools: TripwireTools, service: FakeContainment) -> None:
    """An update with nothing to set writes nothing."""
    assert (tools.update_incident("INC-1"), service.writes) == ("refused: no field to update", [])


def test_off_menu_action_is_refused_locally(tools: TripwireTools, service: FakeContainment) -> None:
    """An action outside the menu never reaches the service."""
    result = tools.request_containment("INC-1", "delete_everything")

    assert (result, service.writes) == ("refused: 'delete_everything' is not on the action menu", [])


def test_request_containment_sends_owner_source(tools: TripwireTools, service: FakeContainment) -> None:
    """The owner's click is recorded as source owner, with the server's approver and the incident's cost."""
    tools.request_containment("INC-1", "disable_route")

    assert service.writes == [
        (
            "apply",
            "INC-1",
            {"action": "disable_route", "source": "owner", "approver": APPROVAL_APPROVER, "spend_usd": 12.5},
        )
    ]


def test_revert_sends_server_approver(tools: TripwireTools, service: FakeContainment) -> None:
    """The revert is recorded with the server's approver, never a name from the model."""
    tools.revert_containment("INC-1")

    assert service.writes == [("revert", "INC-1", {"by": APPROVAL_APPROVER})]


def test_approver_is_never_a_tool_argument(tools: TripwireTools) -> None:
    """A model that types an approver gets a TypeError, not a recorded name."""
    with pytest.raises(TypeError, match="approver"):
        tools.request_containment("INC-1", "disable_route", approver="jason")  # type: ignore[call-arg]


def test_langfuse_read_caps_huge_output(service: FakeContainment, wall_clock: FakeClock) -> None:
    """A trace with a huge observation returns at most the cap, with the cut mark."""
    tools = TripwireTools(service, FakeTraces(make_trace(output="x" * 500_000)), wall_clock)

    result = tools.langfuse_read("INC-1", "trace-1")

    assert (len(result) <= MAX_TOOL_TEXT_CHARS, result.endswith(CUT_MARK)) == (True, True)


def test_T16_server_cap_returns_budget_spent(tools: TripwireTools) -> None:
    """The 21st call in one round returns BUDGET SPENT and the first 20 do not."""
    results = [tools.flags_read("INC-1") for _ in range(21)]

    assert [r == BUDGET_SPENT for r in results] == [False] * 20 + [True]


def test_T16_server_cap_hands_off_incident(tools: TripwireTools, service: FakeContainment) -> None:
    """Spending the budget moves the incident to handed_off on the service."""
    for _ in range(21):
        tools.flags_read("INC-1")

    assert service.incidents["INC-1"].state == "handed_off"


def test_T16_time_cap_at_three_minutes(tools: TripwireTools, wall_clock: FakeClock) -> None:
    """A call at 2m59s is allowed, and a call at exactly 3 minutes returns BUDGET SPENT."""
    results = [tools.flags_read("INC-1")]
    wall_clock.advance(minutes=2, seconds=59)
    results.append(tools.flags_read("INC-1"))
    wall_clock.advance(seconds=1)
    results.append(tools.flags_read("INC-1"))

    assert [r == BUDGET_SPENT for r in results] == [False, False, True]


def test_T16_hand_off_written_once(tools: TripwireTools, service: FakeContainment) -> None:
    """Calls after the budget is spent keep refusing, and write handed_off only once."""
    for _ in range(25):
        tools.flags_read("INC-1")

    assert len(hand_offs(service)) == 1


def test_T16_reopen_resets_budget(tools: TripwireTools, service: FakeContainment, wall_clock: FakeClock) -> None:
    """A reopened incident starts a fresh call count and a fresh clock."""
    for _ in range(20):
        tools.flags_read("INC-1")
    wall_clock.advance(minutes=5)
    service.incidents["INC-1"].ask_round = 2
    service.incidents["INC-1"].state = "awaiting_approval"

    results = [tools.flags_read("INC-1") for _ in range(20)]

    assert BUDGET_SPENT not in results


def test_T16_concurrent_calls_admit_exactly_twenty(service: FakeContainment) -> None:
    """Thirty calls at once admit exactly the 20 the budget allows."""
    tools = TripwireTools(service, FakeTraces(make_trace()), YieldingClock(T0))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: tools.flags_read("INC-1"), range(30)))

    assert sum(r != BUDGET_SPENT for r in results) == 20


def test_hand_off_refusal_is_logged(
    tools: TripwireTools, service: FakeContainment, caplog: pytest.LogCaptureFixture
) -> None:
    """A hand-off the service refuses is logged as a warning, and the tool still returns BUDGET SPENT."""
    service.refuse_update = ContainmentRefused("illegal transition: detected -> handed_off")
    caplog.set_level(logging.WARNING, logger="tripwire_agent.server")

    results = [tools.flags_read("INC-1") for _ in range(21)]

    assert (results[-1], [(r.levelname, r.getMessage()) for r in caplog.records]) == (
        BUDGET_SPENT,
        [("WARNING", "could not hand off INC-1 after budget spent: illegal transition: detected -> handed_off")],
    )


class _Recorder:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.functions: list[Any] = []

    def tool(self) -> Any:
        def decorate(fn: Any) -> Any:
            self.names.append(fn.__name__)
            self.functions.append(fn)
            return fn

        return decorate


def test_register_exposes_the_six_tools(tools: TripwireTools) -> None:
    """The server exposes exactly the tools instructions.md names."""
    recorder = _Recorder()

    register(recorder, tools)

    assert set(recorder.names) == TOOL_NAMES


def test_no_registered_tool_takes_an_approver(tools: TripwireTools) -> None:
    """No tool signature has an approver or by parameter."""
    import inspect

    recorder = _Recorder()
    register(recorder, tools)
    parameters = {name for fn in recorder.functions for name in inspect.signature(fn).parameters}

    assert parameters.isdisjoint({"approver", "by"})


def test_template_keeps_auto_mode_and_bypass_off() -> None:
    """The room template runs Claude Code in Auto mode with Bypass permissions off."""
    template = yaml.safe_load((REPO_ROOT / "tripwire_agent" / "room_template.yaml").read_text())

    assert (template["agent"]["auto_mode"], template["agent"]["auto_approve"]) == (True, False)


def test_template_instructions_match_instructions_file() -> None:
    """The template's instructions are the instructions.md text, so the two cannot drift."""
    template = yaml.safe_load((REPO_ROOT / "tripwire_agent" / "room_template.yaml").read_text())
    instructions = (REPO_ROOT / "tripwire_agent" / "instructions.md").read_text()

    assert template["agent"]["instructions"].strip() == instructions.strip()


async def _list_tool_names(tools: TripwireTools) -> set[str]:
    async with Client(build_server(tools)) as client:
        listed = await client.list_tools()
    return {tool.name for tool in listed.tools}


async def _call_flags_read(tools: TripwireTools, calls: int) -> list[str]:
    async with Client(build_server(tools)) as client:
        return [
            (await client.call_tool("flags_read", {"incident_id": "INC-1"})).content[0].text  # type: ignore[union-attr]
            for _ in range(calls)
        ]


def test_mcp_lists_the_six_tools_in_process(tools: TripwireTools) -> None:
    """An in-process MCP client sees exactly the six tools, with no subprocess or socket."""
    assert asyncio.run(_list_tool_names(tools)) == TOOL_NAMES


def test_mcp_call_hits_server_budget(tools: TripwireTools) -> None:
    """Calls made through MCP hit the server-side budget: the 21st returns BUDGET_SPENT."""
    results = asyncio.run(_call_flags_read(tools, 21))

    assert [r == BUDGET_SPENT for r in results] == [False] * 20 + [True]
