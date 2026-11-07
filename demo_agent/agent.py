"""The order-lookup agent loop. Reads the route's flags from the containment service before every step."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from demo_agent.llm import ModelCallError, ModelClient
from demo_agent.recording import ROUTE, TraceRecorder
from demo_agent.tools import TOOL_SPECS, execute_tool
from tripwire.contracts.models import Trace

logger = logging.getLogger(__name__)

BUGS: tuple[str, ...] = ("none", "loop", "silent_error", "cost_spike")
DEFAULT_MAX_STEPS = 12
NORMAL_MAX_TOKENS = 1024
COST_SPIKE_MAX_TOKENS = 32_000
FLAGS_TIMEOUT_SECONDS = 5.0

BASE_SYSTEM = (
    "You are an order-lookup assistant. Use the tools to answer questions about orders and customers. "
    "Answer in one or two sentences."
)
# The cost_spike bug pads the system prompt (about 170k tokens) and asks for a long answer, so one run
# costs over $1 at default prices. Real-model cost depends on the model's prices and output length.
COST_SPIKE_PAD = "Policy note: orders ship within two business days and refunds follow the return window. " * 8_000
COST_SPIKE_REQUEST = " Write the full order history report, at least twenty pages, with every order."

QUESTIONS: tuple[str, ...] = (
    "Where is order A-1001?",
    "Has order A-1002 been delivered?",
    "Is Ada Lovelace a customer, and what did she order?",
)


@dataclass(frozen=True)
class RouteFlags:
    disabled: bool = False
    max_steps: int | None = None
    model: str | None = None


class FlagSource(Protocol):
    def route_flags(self, route: str) -> RouteFlags: ...


class ContainmentFlags:
    """Reads GET /flags from the containment service. If the service cannot be read, the run goes on with no
    flags and logs a warning. The demo agent is the thing being contained, not the containment gate."""

    def __init__(self, url: str, *, http: httpx.Client) -> None:
        self._url = url.rstrip("/")
        self._http = http

    def route_flags(self, route: str) -> RouteFlags:
        try:
            response = self._http.get(f"{self._url}/flags", timeout=FLAGS_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            entry = data["routes"].get(route) or {}
        except (httpx.HTTPError, ValueError, KeyError, AttributeError) as exc:
            logger.warning("could not read flags from containment, running without them: %s", exc)
            return RouteFlags()
        return RouteFlags(
            disabled=bool(entry.get("disabled", False)),
            max_steps=entry.get("max_steps"),
            model=entry.get("model"),
        )


@dataclass
class RunResult:
    status: str  # "completed" | "route disabled" | "step cap reached" | "error"
    answer: str
    trace: Trace
    error: str | None = None


def run_order_lookup(
    question: str,
    *,
    bug: str,
    model: ModelClient,
    model_name: str,
    flags: FlagSource,
    recorder: TraceRecorder,
) -> RunResult:
    if bug not in BUGS:
        raise ValueError(f"unknown bug {bug!r}; expected one of {', '.join(BUGS)}")

    system = BASE_SYSTEM + ("\n\n" + COST_SPIKE_PAD if bug == "cost_spike" else "")
    max_tokens = COST_SPIKE_MAX_TOKENS if bug == "cost_spike" else NORMAL_MAX_TOKENS
    user_text = question + (COST_SPIKE_REQUEST if bug == "cost_spike" else "")
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

    status = "completed"
    answer = ""
    error: str | None = None
    step = 0
    while True:
        current = flags.route_flags(ROUTE)
        if current.disabled:
            status = "route disabled"
            break
        # A containment flag can lower the step cap, never raise it above the default.
        limit = DEFAULT_MAX_STEPS if current.max_steps is None else min(DEFAULT_MAX_STEPS, current.max_steps)
        if step >= limit:
            status = "step cap reached"
            break

        model_id = current.model or model_name
        try:
            response = model.create(
                model=model_id, system=system, messages=messages, tools=TOOL_SPECS, max_tokens=max_tokens,
            )
        except ModelCallError as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            recorder.generation(
                name="model_call", model=model_id, input=messages[-1]["content"],
                output={"error": error}, usage={}, level="ERROR",
            )
            break
        step += 1

        content = response.get("content", [])
        usage = response.get("usage", {})
        recorder.generation(
            name="model_call", model=model_id, input=messages[-1]["content"], output=content, usage=usage,
        )
        messages.append({"role": "assistant", "content": content})

        tool_uses = [block for block in content if block.get("type") == "tool_use"]
        if response.get("stop_reason") != "tool_use" or not tool_uses:
            answer = "".join(block.get("text", "") for block in content if block.get("type") == "text")
            break

        results: list[dict[str, Any]] = []
        for block in tool_uses:
            tool_input = block.get("input") or {}
            output, level = execute_tool(block["name"], tool_input, bug)
            recorder.tool(name=block["name"], input=tool_input, output=output, level=level)
            results.append({"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(output)})
        messages.append({"role": "user", "content": results})

    return RunResult(status=status, answer=answer, trace=recorder.finish(), error=error)
