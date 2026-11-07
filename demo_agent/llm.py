"""Together API client, plus the offline scripted stand-in.

The agent loop speaks one internal shape: content blocks (`text`, `tool_use`, `tool_result`), `stop_reason` and
`usage`. `TogetherModel` converts to and from Together's chat completions format, so the loop does not care which
client it has.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import together

REQUEST_TIMEOUT_SECONDS = 60.0

# USD per million tokens. These are the OFFLINE scripted prices only, not any real model's price.
# The cost_spike script is sized to them (300k input + 20k output lands just over $1).
# Online runs do not use these; they must set DEMO_PRICE_INPUT_PER_MTOK / DEMO_PRICE_OUTPUT_PER_MTOK.
DEFAULT_PRICE_INPUT_PER_MTOK = 3.0
DEFAULT_PRICE_OUTPUT_PER_MTOK = 15.0


@dataclass(frozen=True)
class Prices:
    input_per_mtok: float = DEFAULT_PRICE_INPUT_PER_MTOK
    output_per_mtok: float = DEFAULT_PRICE_OUTPUT_PER_MTOK

    def cost(self, usage: Mapping[str, Any]) -> float:
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total = input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok
        return round(total / 1_000_000, 6)


def prices_from_env(env: Mapping[str, str]) -> Prices:
    """Read the prices. Raise ValueError with a readable message if a price is not a usable number."""
    return Prices(
        input_per_mtok=_price_from_env(env, "DEMO_PRICE_INPUT_PER_MTOK", DEFAULT_PRICE_INPUT_PER_MTOK),
        output_per_mtok=_price_from_env(env, "DEMO_PRICE_OUTPUT_PER_MTOK", DEFAULT_PRICE_OUTPUT_PER_MTOK),
    )


def _price_from_env(env: Mapping[str, str], name: str, default: float) -> float:
    if not env.get(name):
        return default
    try:
        value = float(env[name])
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {env[name]!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite number of 0 or more, got {env[name]!r}")
    return value


class ModelClient(Protocol):
    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]: ...


class ModelCallError(Exception):
    """A model call failed: the API refused it, it could not be reached, or its answer was malformed."""


class TogetherModel:
    """Calls Together chat completions. The API key stays in the client, never in a log or a trace."""

    def __init__(self, api_key: str, *, http: httpx.Client, base_url: str | None = None) -> None:
        self._client = together.Together(
            api_key=api_key, base_url=base_url, http_client=http, timeout=REQUEST_TIMEOUT_SECONDS,
        )

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        try:
            response = self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=_to_together_messages(system, messages),
                tools=[_to_together_tool(tool) for tool in tools],
            )
        except together.APIError as exc:
            raise ModelCallError(str(exc)) from exc
        return _from_together_response(response)


def _to_together_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


def _to_together_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            converted.append({"role": message["role"], "content": content})
        elif message["role"] == "assistant":
            converted.append(_to_together_assistant(content))
        else:
            converted.extend(
                {"role": "tool", "tool_call_id": block["tool_use_id"], "content": block["content"]}
                for block in content
            )
    return converted


def _to_together_assistant(content: list[dict[str, Any]]) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(block["text"] for block in content if block["type"] == "text"),
    }
    calls = [
        {
            "id": block["id"],
            "type": "function",
            "function": {"name": block["name"], "arguments": json.dumps(block["input"])},
        }
        for block in content
        if block["type"] == "tool_use"
    ]
    if calls:
        message["tool_calls"] = calls
    return message


def _from_together_response(response: Any) -> dict[str, Any]:
    if not response.choices or response.choices[0].message is None:
        raise ModelCallError("the response has no message")
    message = response.choices[0].message
    content: list[dict[str, Any]] = [_text(message.content)] if message.content else []
    for call in message.tool_calls or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ModelCallError(f"tool call {call.function.name} has invalid JSON arguments") from exc
        content.append({"type": "tool_use", "id": call.id, "name": call.function.name, "input": arguments})
    usage = response.usage
    return {
        "content": content,
        "stop_reason": "tool_use" if message.tool_calls else "end_turn",
        "usage": {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        },
    }


class ScriptedModel:
    """Offline stand-in. Its moves are fixed per bug, so tests and CI need no API key.

    Token counts are simulated. The cost_spike script reports a large usage so one run costs over $1.
    """

    def __init__(self, bug: str) -> None:
        self._bug = bug

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        turn = sum(1 for message in messages if message["role"] == "assistant")
        if self._bug == "loop":
            content = [_tool_use(turn, "get_order", {"order_id": "A-1001"})]
        elif self._bug == "silent_error":
            if turn == 0:
                content = [_tool_use(turn, "search_customer", {"name": "Ada Lovelace"})]
            elif turn == 1:
                content = [_tool_use(turn, "get_order", {"order_id": "A-1001"})]
            else:
                content = [_text("Your order A-1001 has shipped.")]
        elif self._bug == "cost_spike":
            content = [_text("Full order history report follows.")]
        elif turn == 0:
            content = [_tool_use(turn, "get_order", {"order_id": "A-1001"})]
        else:
            content = [_text("Your order A-1001 has shipped.")]

        if any(block["type"] == "tool_use" for block in content):
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"
        usage = (
            {"input_tokens": 300_000, "output_tokens": 20_000}
            if self._bug == "cost_spike"
            else {"input_tokens": 800, "output_tokens": 60}
        )
        return {"id": f"msg_scripted_{turn}", "type": "message", "role": "assistant", "model": model,
                "content": content, "stop_reason": stop_reason, "usage": usage}


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _tool_use(turn: int, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_scripted_{turn}", "name": name, "input": tool_input}
