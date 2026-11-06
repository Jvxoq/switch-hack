"""Builds the `Trace` the detector reads, and ships the same trace to Langfuse over HTTP."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from demo_agent.llm import Prices
from tripwire.contracts.models import Observation, Trace

logger = logging.getLogger(__name__)

ROUTE = "order-lookup"
TRACE_NAME = "order-lookup-run"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TraceRecorder:
    """One run's trace. `details` keeps what `Observation` has no field for: model, token usage and the
    observation's own name in Langfuse terms."""

    prices: Prices
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: datetime = field(default_factory=_now)
    observations: list[Observation] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)

    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        output: Any,
        usage: dict[str, Any],
        level: str = "DEFAULT",
    ) -> Observation:
        cost = self.prices.cost(usage) if level != "ERROR" else 0.0
        return self._add(
            type="generation", name=name, input=input, output=output, level=level, cost_usd=cost,
            detail={"model": model, "usage": {
                "input": int(usage.get("input_tokens", 0) or 0),
                "output": int(usage.get("output_tokens", 0) or 0),
            }},
        )

    def tool(self, *, name: str, input: Any, output: Any, level: str) -> Observation:
        return self._add(type="tool", name=name, input=input, output=output, level=level, cost_usd=0.0, detail={})

    def finish(self) -> Trace:
        return Trace(
            id=self.trace_id,
            name=TRACE_NAME,
            route=ROUTE,
            thread_id=None,
            start_time=self.started,
            end_time=_now(),
            total_cost_usd=round(sum(o.cost_usd for o in self.observations), 6),
            observations=list(self.observations),
        )

    def _add(
        self,
        *,
        type: str,
        name: str,
        input: Any,
        output: Any,
        level: str,
        cost_usd: float,
        detail: dict[str, Any],
    ) -> Observation:
        index = len(self.observations)
        obs = Observation(
            id=f"{self.trace_id}-o{index}",
            trace_id=self.trace_id,
            type=type,
            name=name,
            input=input,
            output=output,
            level=level,
            start_time=_now(),
            cost_usd=cost_usd,
        )
        self.observations.append(obs)
        self.details[obs.id] = {"output": output, **detail}
        return obs


class LangfuseSink:
    """Posts one trace per call to Langfuse's batch ingestion endpoint (basic auth: public key, secret key)."""

    def __init__(self, host: str, public_key: str, secret_key: str, *, http: httpx.Client) -> None:
        self._host = host.rstrip("/")
        self._auth = (public_key, secret_key)
        self._http = http

    def send(self, trace: Trace, details: dict[str, dict[str, Any]]) -> None:
        stamp = trace.start_time.isoformat()
        batch: list[dict[str, Any]] = [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": stamp,
                "body": {
                    "id": trace.id,
                    "name": trace.name,
                    "timestamp": stamp,
                    "tags": [f"route:{trace.route}"],
                },
            }
        ]
        for obs in trace.observations:
            extra = details.get(obs.id, {})
            body: dict[str, Any] = {
                "id": obs.id,
                "traceId": trace.id,
                "name": obs.name,
                "startTime": obs.start_time.isoformat(),
                "input": obs.input,
                "output": extra.get("output"),
                "level": obs.level,
                "costDetails": {"total": obs.cost_usd},
            }
            event_type = "span-create"
            if obs.type == "generation":
                event_type = "generation-create"
                body["model"] = extra.get("model")
                body["usage"] = {**extra.get("usage", {}), "unit": "TOKENS"}
            batch.append({"id": str(uuid.uuid4()), "type": event_type, "timestamp": stamp, "body": body})

        response = self._http.post(
            f"{self._host}/api/public/ingestion",
            auth=self._auth,
            json={"batch": batch},
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info("sent trace %s to Langfuse (%d events)", trace.id, len(batch))
