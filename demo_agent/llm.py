"""Claude Messages API client over httpx, plus the offline scripted stand-in.

Both clients return the Messages API response shape, so the agent loop does not care which one it has.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

ANTHROPIC_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 60.0

# USD per million tokens. Override with DEMO_PRICE_INPUT_PER_MTOK / DEMO_PRICE_OUTPUT_PER_MTOK to match the model.
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
    return Prices(
        input_per_mtok=float(env.get("DEMO_PRICE_INPUT_PER_MTOK", DEFAULT_PRICE_INPUT_PER_MTOK)),
        output_per_mtok=float(env.get("DEMO_PRICE_OUTPUT_PER_MTOK", DEFAULT_PRICE_OUTPUT_PER_MTOK)),
    )


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


class AnthropicModel:
    """Calls POST /v1/messages. The API key goes only in the request header, never in a log or a trace."""

    def __init__(self, api_key: str, *, http: httpx.Client, base_url: str = ANTHROPIC_URL) -> None:
        self._api_key = api_key
        self._http = http
        self._base_url = base_url.rstrip("/")

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        response = self._http.post(
            f"{self._base_url}/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "tools": tools,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()


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
