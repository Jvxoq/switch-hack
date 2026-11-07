"""Langfuse public API client: the `LangfuseReader` port over HTTP.

Endpoints: GET /api/public/traces (paged, `fromTimestamp`), GET /api/public/observations (paged,
`fromStartTime`) and GET /api/public/traces/{id}. Auth is HTTP basic with the public and secret keys.

The trace list is filtered by start time only. This client has no "updated since" filter, so E00
refreshes running traces with `get_trace`.

Synchronous on purpose: the `LangfuseReader` port is a plain `def`. Every request has a timeout.
5xx responses are retried with exponential backoff and jitter. Every other failure raises
`LangfuseError`, so callers handle one exception type.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from tripwire.contracts.models import Observation, Trace

PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 100
MAX_ERROR_CHARS = 200
UNKNOWN_ROUTE = "unknown"
ROUTE_TAG_PREFIX = "route:"


class LangfuseError(Exception):
    """Langfuse could not be read: keys refused, not found, still failing after retries, or a malformed body."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LangfuseClient:
    """Implements `LangfuseReader` (`recent_traces`, `get_trace`) against the Langfuse public API."""

    def __init__(
        self,
        base_url: str,
        public_key: str,
        secret_key: str,
        *,
        timeout_seconds: float = 10.0,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=(public_key, secret_key),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )
        self._max_pages = max_pages
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds
        self._sleep = sleep
        self._rand = rand

    def close(self) -> None:
        self._http.close()

    def recent_traces(self, since: datetime) -> list[Trace]:
        """Traces that started at or after `since`, with their observations loaded."""
        trace_rows = self._collect("/api/public/traces", {"fromTimestamp": _iso(since)})
        observation_rows = self._collect("/api/public/observations", {"fromStartTime": _iso(since)})

        observations_by_trace: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in observation_rows:
            observations_by_trace[_str_field(row, "traceId")].append(row)

        rows_by_id = {_str_field(row, "id"): row for row in trace_rows}
        return [
            self._build_trace(row, observations_by_trace.get(trace_id, []))
            for trace_id, row in rows_by_id.items()
        ]

    def get_trace(self, trace_id: str) -> Trace:
        """Fresh copy of one trace with all its observations."""
        body = self._get_json(f"/api/public/traces/{quote(trace_id, safe='')}")
        return self._build_trace(_expect_dict(body), _dict_list(body, "observations"))

    # ----- HTTP -----

    def _collect(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self._get_json(path, {**params, "page": page, "limit": PAGE_SIZE})
            rows.extend(_dict_list(body, "data"))
            total_pages = _total_pages(body)
            if page >= total_pages:
                return rows
            if page >= self._max_pages:
                # Partial rows would break the window contract (full window, observations loaded), so fail loudly.
                raise LangfuseError(
                    f"{path} has more than {self._max_pages} pages; raise langfuse_max_pages or narrow the window"
                )
            page += 1

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        attempt = 0
        while True:
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as exc:
                raise LangfuseError(f"Langfuse request failed: {type(exc).__name__}") from exc
            if response.status_code < 500 or attempt >= self._max_retries:
                break
            self._sleep(self._backoff(attempt))
            attempt += 1

        if response.status_code == 401:
            raise LangfuseError("Langfuse refused the API keys (HTTP 401)", status_code=401)
        if response.status_code >= 400:
            snippet = response.text[:MAX_ERROR_CHARS]
            raise LangfuseError(
                f"Langfuse returned HTTP {response.status_code}: {snippet}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LangfuseError("Langfuse returned a malformed JSON body") from exc

    def _backoff(self, attempt: int) -> float:
        return self._base_backoff * float(2**attempt) + self._rand() * self._base_backoff

    # ----- mapping -----

    def _build_trace(self, row: dict[str, Any], observation_rows: list[dict[str, Any]]) -> Trace:
        observations = [_observation(obs) for obs in observation_rows]
        ends = [_optional_datetime(obs, "endTime") for obs in observation_rows]
        closed = [end for end in ends if end is not None]
        # A trace is running while any observation is still open, or while it has none yet.
        end_time = max(closed) if observation_rows and len(closed) == len(observation_rows) else None

        total_cost = _optional_number(row, "totalCost")
        if total_cost is None:
            total_cost = sum(obs.cost_usd for obs in observations)

        return Trace(
            id=_str_field(row, "id"),
            name=_optional_str(row, "name") or "",
            route=_route(row),
            thread_id=_optional_str(row, "sessionId"),
            start_time=_datetime_field(row, "timestamp"),
            end_time=end_time,
            total_cost_usd=total_cost,
            observations=observations,
        )


# ----- helpers: route, observation, validation -----


def _route(row: dict[str, Any]) -> str:
    tags = row.get("tags") or []
    if not isinstance(tags, list):
        raise LangfuseError("Langfuse body has non-list 'tags'")
    for tag in tags:
        if isinstance(tag, str) and tag.startswith(ROUTE_TAG_PREFIX) and len(tag) > len(ROUTE_TAG_PREFIX):
            return tag[len(ROUTE_TAG_PREFIX) :]
    return UNKNOWN_ROUTE


def _observation(row: dict[str, Any]) -> Observation:
    return Observation(
        id=_str_field(row, "id"),
        trace_id=_str_field(row, "traceId"),
        type=_str_field(row, "type"),
        name=_optional_str(row, "name") or "",
        input=row.get("input"),
        output=row.get("output"),
        level=_optional_str(row, "level") or "DEFAULT",
        start_time=_datetime_field(row, "startTime"),
        cost_usd=_optional_number(row, "calculatedTotalCost") or 0.0,
    )


def _total_pages(body: Any) -> int:
    meta = _expect_dict(body).get("meta")
    if not isinstance(meta, dict):
        raise LangfuseError("Langfuse body has no 'meta'")
    total = meta.get("totalPages")
    if isinstance(total, bool) or not isinstance(total, int):
        raise LangfuseError("Langfuse body has no integer 'totalPages'")
    return total


def _expect_dict(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise LangfuseError("Langfuse body is not a JSON object")
    return body


def _dict_list(body: Any, key: str) -> list[dict[str, Any]]:
    value = _expect_dict(body).get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LangfuseError(f"Langfuse body has no list '{key}'")
    return value


def _str_field(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise LangfuseError(f"Langfuse body has no string '{key}'")
    return value


def _optional_str(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LangfuseError(f"Langfuse body has non-string '{key}'")
    return value


def _optional_number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LangfuseError(f"Langfuse body has non-numeric '{key}'")
    return float(value)


def _datetime_field(row: dict[str, Any], key: str) -> datetime:
    value = _optional_datetime(row, key)
    if value is None:
        raise LangfuseError(f"Langfuse body has no '{key}' time")
    return value


def _optional_datetime(row: dict[str, Any], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LangfuseError(f"Langfuse body has non-string '{key}' time")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LangfuseError(f"Langfuse body has bad '{key}' time") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _iso(moment: datetime) -> str:
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat()
