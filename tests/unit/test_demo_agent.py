"""Offline tests for the demo agent: each bug must leave the trace pattern its rule expects.

Everything runs through httpx.MockTransport or the scripted model. The autouse fixture refuses any socket.
"""

from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from demo_agent import cli
from demo_agent.agent import (
    COST_SPIKE_PAD,
    DEFAULT_MAX_STEPS,
    ContainmentFlags,
    RouteFlags,
    run_order_lookup,
)
from demo_agent.llm import AnthropicModel, Prices, ScriptedModel
from demo_agent.recording import LangfuseSink, TraceRecorder
from demo_agent.tools import execute_tool
from tripwire.contracts.config import TripwireConfig
from tripwire.contracts.models import Trace
from tripwire.rules.cost_spike import CostSpikeRule
from tripwire.rules.loop import LoopRule
from tripwire.rules.silent_error import SilentErrorRule

QUESTION = "Where is order A-1001?"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Refuse every socket. Each attempt is recorded and fails the test at teardown."""
    attempts: list[str] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        attempts.append(repr(args[1:2]))
        raise OSError("network is blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    yield attempts
    assert attempts == [], f"real network attempted: {attempts}"


class StaticFlags:
    def __init__(self, flags: RouteFlags | None = None) -> None:
        self._flags = flags or RouteFlags()

    def route_flags(self, route: str) -> RouteFlags:
        return self._flags


class RecordingModel:
    """Wraps the scripted model and keeps every call's model name."""

    def __init__(self, bug: str) -> None:
        self._inner = ScriptedModel(bug)
        self.model_names: list[str] = []

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.model_names.append(kwargs["model"])
        return self._inner.create(**kwargs)


def run_offline(bug: str, flags: StaticFlags | None = None, model: Any = None) -> tuple[Any, Trace]:
    recorder = TraceRecorder(prices=Prices())
    result = run_order_lookup(
        QUESTION,
        bug=bug,
        model=model or ScriptedModel(bug),
        model_name="scripted",
        flags=flags or StaticFlags(),
        recorder=recorder,
    )
    return result, result.trace


def end_of(trace: Trace) -> datetime:
    return max(obs.start_time for obs in trace.observations) + timedelta(seconds=1)


def tool_names(trace: Trace) -> list[str]:
    return [obs.name for obs in trace.observations if obs.type == "tool"]


def test_loop_bug_repeats_identical_get_order(cfg: TripwireConfig) -> None:
    result, trace = run_offline("loop")

    assert tool_names(trace) == ["get_order"] * DEFAULT_MAX_STEPS
    inputs = {json.dumps(obs.input, sort_keys=True) for obs in trace.observations if obs.type == "tool"}
    assert inputs == {json.dumps({"order_id": "A-1001"}, sort_keys=True)}
    outputs = [obs.output for obs in trace.observations if obs.type == "tool"]
    assert outputs == [{"status": "pending", "hint": "call get_order again with the same order_id"}] * DEFAULT_MAX_STEPS
    assert result.status == "step cap reached"


def test_loop_rule_fires_on_loop_bug(cfg: TripwireConfig) -> None:
    _, trace = run_offline("loop")

    hits = LoopRule().evaluate([trace], cfg.rules, end_of(trace))

    assert [hit.rule for hit in hits] == ["loop"]
    assert "near-identical repeated calls" in hits[0].detail


def test_loop_rule_quiet_on_healthy_run(cfg: TripwireConfig) -> None:
    result, trace = run_offline("none")

    hits = LoopRule().evaluate([trace], cfg.rules, end_of(trace))

    assert hits == []
    assert result.answer == "Your order A-1001 has shipped."


def test_silent_error_bug_leaves_default_level_error_body(cfg: TripwireConfig) -> None:
    _, trace = run_offline("silent_error")

    search = [obs for obs in trace.observations if obs.name == "search_customer"]

    assert [(obs.level, obs.output) for obs in search] == [
        ("DEFAULT", {"error": "customer not found"}),
    ]


def test_silent_error_rule_fires_over_ten_runs(cfg: TripwireConfig) -> None:
    traces = [run_offline("silent_error")[1] for _ in range(10)]
    now = max(end_of(trace) for trace in traces)

    hits = SilentErrorRule().evaluate(traces, cfg.rules, now)

    assert [hit.route for hit in hits] == ["order-lookup"]
    assert len(hits[0].observation_ids) == 10


def test_silent_error_rule_quiet_on_healthy_search(cfg: TripwireConfig) -> None:
    output, level = execute_tool("search_customer", {"name": "Ada Lovelace"}, "none")
    recorder = TraceRecorder(prices=Prices())
    recorder.tool(name="search_customer", input={"name": "Ada Lovelace"}, output=output, level=level)
    trace = recorder.finish()

    hits = SilentErrorRule().evaluate([trace], cfg.rules, end_of(trace))

    assert (output, level) == ({"customer_id": "C-1", "name": "Ada Lovelace"}, "DEFAULT")
    assert hits == []


def test_unknown_customer_is_an_honest_error_level() -> None:
    output, level = execute_tool("search_customer", {"name": "Nobody"}, "none")

    assert (output, level) == ({"error": "customer not found"}, "ERROR")


def test_cost_spike_bug_crosses_per_trace_limit(cfg: TripwireConfig) -> None:
    result, trace = run_offline("cost_spike")

    hits = CostSpikeRule().evaluate([trace], cfg.rules, end_of(trace))

    assert trace.total_cost_usd >= 1.0
    assert [hit.rule for hit in hits] == ["cost_spike"]
    assert result.status == "completed"


def test_healthy_run_stays_under_cost_limit(cfg: TripwireConfig) -> None:
    _, trace = run_offline("none")

    assert trace.total_cost_usd < 0.01
    assert CostSpikeRule().evaluate([trace], cfg.rules, end_of(trace)) == []


def test_disabled_flag_stops_before_first_model_call() -> None:
    model = RecordingModel("none")

    result, trace = run_offline("none", StaticFlags(RouteFlags(disabled=True)), model=model)

    assert (result.status, model.model_names, trace.observations) == ("route disabled", [], [])


def test_max_steps_flag_lowers_the_cap() -> None:
    result, trace = run_offline("loop", StaticFlags(RouteFlags(max_steps=3)))

    assert (result.status, len(tool_names(trace))) == ("step cap reached", 3)


def test_max_steps_flag_cannot_raise_the_cap() -> None:
    result, trace = run_offline("loop", StaticFlags(RouteFlags(max_steps=999)))

    assert len(tool_names(trace)) == DEFAULT_MAX_STEPS


def test_model_flag_overrides_model_name() -> None:
    model = RecordingModel("none")

    run_offline("none", StaticFlags(RouteFlags(model="cheap-model")), model=model)

    assert set(model.model_names) == {"cheap-model"}


def test_containment_flags_parse_route_entry() -> None:
    payload = {"routes": {"order-lookup": {"disabled": False, "max_steps": 4, "model": "m-2"}}}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as http:
        flags = ContainmentFlags("http://containment.test", http=http).route_flags("order-lookup")

    assert flags == RouteFlags(disabled=False, max_steps=4, model="m-2")


def test_unreachable_containment_runs_with_no_flags() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("containment down", request=request)

    with httpx.Client(transport=httpx.MockTransport(refuse)) as http:
        flags = ContainmentFlags("http://containment.test", http=http).route_flags("order-lookup")
        result, _ = run_offline("none", StaticFlags(flags))

    assert (flags, result.status) == (RouteFlags(), "completed")


def test_anthropic_request_carries_padded_cost_spike_body() -> None:
    sent: list[httpx.Request] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        body = {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5}}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        model = AnthropicModel("test-key", http=http)
        result, trace = run_offline("cost_spike", model=model)

    body = json.loads(sent[0].content)
    assert sent[0].headers["x-api-key"] == "test-key"
    assert (body["model"], body["max_tokens"]) == ("scripted", 32_000)
    assert len(body["system"]) >= len(COST_SPIKE_PAD)
    assert "test-key" not in json.dumps(trace.observations, default=str)
    assert result.status == "completed"


def test_anthropic_http_error_becomes_error_run() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream down"})
    recorder = TraceRecorder(prices=Prices())

    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        result = run_order_lookup(
            QUESTION, bug="none", model=AnthropicModel("test-key", http=http), model_name="m",
            flags=StaticFlags(), recorder=recorder,
        )

    last = result.trace.observations[-1]
    assert (result.status, last.level, last.cost_usd) == ("error", "ERROR", 0.0)
    assert "test-key" not in json.dumps([result.trace, recorder.details], default=str)


def test_langfuse_batch_tags_route_and_omits_key() -> None:
    _, trace = run_offline("silent_error")
    recorder = TraceRecorder(prices=Prices())
    recorder.generation(name="model_call", model="m", input="q", output="a", usage={"input_tokens": 1})
    recorder.tool(name="get_order", input={}, output={"status": "shipped"}, level="DEFAULT")
    sent: list[httpx.Request] = []

    def accept(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(207, json={"successes": [], "errors": []})

    with httpx.Client(transport=httpx.MockTransport(accept)) as http:
        sink = LangfuseSink("http://langfuse.test", "pk-test", "sk-secret", http=http)
        sink.send(recorder.finish(), recorder.details)

    body = json.loads(sent[0].content)
    events = [event["type"] for event in body["batch"]]
    assert events == ["trace-create", "generation-create", "span-create"]
    assert body["batch"][0]["body"]["tags"] == ["route:order-lookup"]
    assert sent[0].headers["authorization"].startswith("Basic ")
    assert "sk-secret" not in sent[0].content.decode()


def test_cli_rejects_zero_runs_before_any_network() -> None:
    assert cli.main(["run", "--bug", "loop", "--n", "0", "--offline"], env={}) == 2


def test_cli_online_run_needs_api_key() -> None:
    assert cli.main(["run", "--bug", "none", "--n", "1"], env={}) == 2


def test_prices_cost_uses_per_million_rates() -> None:
    assert Prices(input_per_mtok=3.0, output_per_mtok=15.0).cost(
        {"input_tokens": 300_000, "output_tokens": 20_000}
    ) == pytest.approx(1.2)
