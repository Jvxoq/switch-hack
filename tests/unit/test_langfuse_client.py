from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from tripwire.contracts.ports import LangfuseReader
from tripwire.langfuse_client import DEFAULT_MAX_PAGES, LangfuseClient, LangfuseError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASE = "https://langfuse.test"
PUBLIC = "pk-lf-test"
SECRET = "sk-lf-test"
SINCE = datetime(2026, 11, 6, 9, 55, tzinfo=UTC)


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _client(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> LangfuseClient:
    options: dict[str, Any] = {"sleep": lambda _seconds: None, "rand": lambda: 0.0} | kwargs
    return LangfuseClient(BASE, PUBLIC, SECRET, transport=httpx.MockTransport(handler), **options)


def _window_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/public/traces":
            page = request.url.params["page"]
            name = "langfuse_traces_page1.json" if page == "1" else "langfuse_traces_page2.json"
            return httpx.Response(200, json=_load(name))
        if request.url.path == "/api/public/observations":
            return httpx.Response(200, json=_load("langfuse_observations_page1.json"))
        raise AssertionError(f"unexpected request {request.url}")

    return handler


def _window(requests: list[httpx.Request] | None = None) -> list[Any]:
    seen = requests if requests is not None else []
    return _client(_window_handler(seen)).recent_traces(SINCE)


def test_client_satisfies_reader_port() -> None:
    assert isinstance(_client(lambda r: httpx.Response(500)), LangfuseReader)


def test_recent_traces_pages_through_all_results() -> None:
    requested_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/public/traces":
            requested_pages.append(request.url.params["page"])
            name = "langfuse_traces_page1.json" if requested_pages[-1] == "1" else "langfuse_traces_page2.json"
            return httpx.Response(200, json=_load(name))
        return httpx.Response(200, json=_load("langfuse_observations_page1.json"))

    traces = _client(handler).recent_traces(SINCE)

    assert requested_pages == ["1", "2"]
    assert [t.id for t in traces] == ["tr-1", "tr-2", "tr-3"]


def test_recent_traces_filters_by_from_timestamp_and_sends_basic_auth() -> None:
    requests: list[httpx.Request] = []

    _window(requests)

    trace_request = next(r for r in requests if r.url.path == "/api/public/traces")
    obs_request = next(r for r in requests if r.url.path == "/api/public/observations")
    expected_auth = "Basic " + base64.b64encode(f"{PUBLIC}:{SECRET}".encode()).decode()
    assert trace_request.url.params["fromTimestamp"] == "2026-11-06T09:55:00+00:00"
    assert obs_request.url.params["fromStartTime"] == "2026-11-06T09:55:00+00:00"
    assert trace_request.headers["authorization"] == expected_auth


def test_route_comes_from_route_tag() -> None:
    traces = _window()

    assert [t.route for t in traces] == ["order-lookup", "unknown", "order-lookup"]


def test_session_id_becomes_thread_id() -> None:
    traces = _window()

    assert [t.thread_id for t in traces] == ["thread-a", None, "thread-c"]


def test_open_observation_makes_trace_running() -> None:
    traces = _window()

    assert traces[1].end_time is None


def test_closed_trace_ends_at_latest_observation_end() -> None:
    traces = _window()

    assert traces[0].end_time == datetime(2026, 11, 6, 10, 0, 30, tzinfo=UTC)


def test_trace_without_observations_is_running() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/public/traces":
            return httpx.Response(200, json=_load("langfuse_traces_page1.json") | {"meta": {"totalPages": 1}})
        return httpx.Response(200, json={"data": [], "meta": {"totalPages": 1}})

    traces = _client(handler).recent_traces(SINCE)

    assert [t.end_time for t in traces] == [None, None]


def test_trace_cost_prefers_trace_total() -> None:
    traces = _window()

    assert traces[0].total_cost_usd == 0.12


def test_missing_trace_cost_sums_observations() -> None:
    traces = _window()

    assert traces[2].total_cost_usd == pytest.approx(0.4)


def test_missing_cost_everywhere_reads_as_zero() -> None:
    traces = _window()

    assert traces[1].total_cost_usd == 0.0


def test_observations_group_under_their_trace() -> None:
    traces = _window()

    assert [[o.id for o in t.observations] for t in traces] == [
        ["ob-1a", "ob-1b"],
        ["ob-2a"],
        ["ob-3a", "ob-3b"],
    ]


def test_observation_of_unlisted_trace_is_dropped() -> None:
    traces = _window()

    assert "ob-old" not in [o.id for t in traces for o in t.observations]


def test_get_trace_maps_full_observations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/public/traces/tr-1"
        return httpx.Response(200, json=_load("langfuse_trace_detail.json"))

    trace = _client(handler).get_trace("tr-1")

    assert (trace.route, trace.end_time, [o.id for o in trace.observations]) == (
        "order-lookup",
        datetime(2026, 11, 6, 10, 0, 30, tzinfo=UTC),
        ["ob-1a", "ob-1b"],
    )


def test_naive_timestamp_is_read_as_utc() -> None:
    body = _load("langfuse_trace_detail.json") | {"timestamp": "2026-11-06T10:00:00"}

    trace = _client(lambda r: httpx.Response(200, json=body)).get_trace("tr-1")

    assert trace.start_time == datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def test_retries_server_errors_then_succeeds() -> None:
    seen: list[httpx.Request] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) <= 2:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=_load("langfuse_trace_detail.json"))

    client = _client(handler, sleep=waits.append)
    trace = client.get_trace("tr-1")

    assert len(seen) == 3
    assert waits == [0.5, 1.0]
    assert trace.id == "tr-1"


def test_gives_up_after_max_server_error_retries() -> None:
    seen: list[httpx.Request] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500, text="boom")

    with pytest.raises(LangfuseError, match="HTTP 500") as excinfo:
        _client(handler, sleep=waits.append).get_trace("tr-1")

    assert excinfo.value.status_code == 500
    assert len(seen) == 4
    assert waits == [0.5, 1.0, 2.0]


def test_backoff_adds_jitter_to_each_wait() -> None:
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    client = LangfuseClient(
        BASE,
        PUBLIC,
        SECRET,
        transport=httpx.MockTransport(handler),
        sleep=waits.append,
        rand=lambda: 1.0,
        max_retries=2,
    )
    with pytest.raises(LangfuseError):
        client.get_trace("tr-1")

    assert waits == [1.0, 1.5]


def test_unauthorized_raises_without_retry() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, text="invalid keys")

    with pytest.raises(LangfuseError, match="refused the API keys"):
        _client(handler).get_trace("tr-1")

    assert len(seen) == 1


def test_not_found_trace_raises_without_retry() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404, text="not found")

    with pytest.raises(LangfuseError, match="HTTP 404") as excinfo:
        _client(handler).get_trace("tr-missing")

    assert excinfo.value.status_code == 404
    assert len(seen) == 1


def test_timeout_raises_langfuse_error_without_retry() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise httpx.ReadTimeout("no answer", request=request)

    with pytest.raises(LangfuseError, match="ReadTimeout"):
        _client(handler).get_trace("tr-1")

    assert len(seen) == 1


def test_connection_error_raises_langfuse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LangfuseError, match="ConnectError"):
        _client(handler).get_trace("tr-1")


def test_every_request_carries_ten_second_read_timeout() -> None:
    timeouts: list[float | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json=_load("langfuse_trace_detail.json"))

    _client(handler).get_trace("tr-1")

    assert timeouts == [10.0]


def test_malformed_json_raises() -> None:
    with pytest.raises(LangfuseError, match="malformed JSON"):
        _client(lambda r: httpx.Response(200, text="<html>not json")).get_trace("tr-1")


def test_missing_data_list_raises() -> None:
    with pytest.raises(LangfuseError, match="no list 'data'"):
        _client(lambda r: httpx.Response(200, json={"meta": {"totalPages": 1}})).recent_traces(SINCE)


def test_bad_timestamp_raises() -> None:
    body = _load("langfuse_trace_detail.json") | {"timestamp": "yesterday"}

    with pytest.raises(LangfuseError, match="bad 'timestamp' time"):
        _client(lambda r: httpx.Response(200, json=body)).get_trace("tr-1")


def test_non_numeric_cost_raises() -> None:
    body = _load("langfuse_trace_detail.json") | {"totalCost": "cheap"}

    with pytest.raises(LangfuseError, match="non-numeric 'totalCost'"):
        _client(lambda r: httpx.Response(200, json=body)).get_trace("tr-1")


def test_error_body_is_truncated() -> None:
    with pytest.raises(LangfuseError) as excinfo:
        _client(lambda r: httpx.Response(400, text="x" * 100_000)).get_trace("tr-1")

    assert str(excinfo.value) == "Langfuse returned HTTP 400: " + "x" * 200


def _endless_pages(requested: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.params["page"])
        return httpx.Response(200, json={"data": [], "meta": {"totalPages": 1000}})

    return handler


def test_default_page_cap_is_one_hundred() -> None:
    requested: list[str] = []

    with pytest.raises(LangfuseError, match=f"more than {DEFAULT_MAX_PAGES} pages"):
        _client(_endless_pages(requested)).recent_traces(SINCE)

    assert DEFAULT_MAX_PAGES == 100
    assert len(requested) == DEFAULT_MAX_PAGES


def test_page_cap_hit_fails_and_names_the_knob() -> None:
    requested: list[str] = []

    with pytest.raises(LangfuseError, match="more than 3 pages; raise langfuse_max_pages") as excinfo:
        _client(_endless_pages(requested), max_pages=3).recent_traces(SINCE)

    assert str(excinfo.value).startswith("/api/public/traces has more than 3 pages")
    assert requested == ["1", "2", "3"]


def test_exactly_at_page_cap_reads_every_page() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.params["page"])
        if request.url.path == "/api/public/traces":
            return httpx.Response(200, json={"data": [], "meta": {"totalPages": 3}})
        return httpx.Response(200, json={"data": [], "meta": {"totalPages": 1}})

    traces = _client(handler, max_pages=3).recent_traces(SINCE)

    assert traces == []
    assert requested == ["1", "2", "3", "1"]


def test_pages_under_cap_return_every_row() -> None:
    traces = _client(_window_handler([]), max_pages=2).recent_traces(SINCE)

    assert [t.id for t in traces] == ["tr-1", "tr-2", "tr-3"]


@pytest.mark.parametrize(
    ("tags", "expected_route"),
    [
        (["env:prod", "route:order-lookup"], "order-lookup"),
        (["env:prod"], "unknown"),
        (["route:"], "unknown"),
    ],
    ids=["route_after_other_tag", "no_route_tag", "empty_route_name"],
)
def test_only_route_prefixed_tags_name_the_route(tags: list[str], expected_route: str) -> None:
    body = _load("langfuse_trace_detail.json") | {"tags": tags}

    trace = _client(lambda r: httpx.Response(200, json=body)).get_trace("tr-1")

    assert trace.route == expected_route


def _page_handler(
    traces: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        rows = traces if request.url.path == "/api/public/traces" else observations
        return httpx.Response(200, json={"data": rows, "meta": {"totalPages": 1}})

    return handler


def _trace_row(trace_id: str) -> dict[str, Any]:
    return {"id": trace_id, "name": "n", "timestamp": "2026-11-06T10:00:00Z", "tags": []}


def _observation_row(observation_id: str, trace_id: str) -> dict[str, Any]:
    return {
        "id": observation_id,
        "traceId": trace_id,
        "type": "SPAN",
        "startTime": "2026-11-06T10:00:00Z",
        "endTime": "2026-11-06T10:00:05Z",
    }


@pytest.mark.parametrize(
    "bad_row",
    [
        _trace_row("tr-bad") | {"timestamp": "yesterday"},
        _trace_row("tr-bad") | {"timestamp": None},
        _trace_row("tr-bad") | {"tags": "route:x"},
        _trace_row("tr-bad") | {"totalCost": "cheap"},
    ],
    ids=["bad_timestamp", "missing_timestamp", "non_list_tags", "non_numeric_cost"],
)
def test_bad_trace_row_is_skipped_and_logged(bad_row: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
    rows = [_trace_row("tr-a"), bad_row, _trace_row("tr-c")]

    with caplog.at_level(logging.WARNING, logger="tripwire.langfuse_client"):
        traces = _client(_page_handler(rows, [])).recent_traces(SINCE)

    assert [t.id for t in traces] == ["tr-a", "tr-c"]
    assert [(r.levelno, "tr-bad" in r.getMessage()) for r in caplog.records] == [(logging.WARNING, True)]


@pytest.mark.parametrize("bad_id", [None, 7], ids=["missing_id", "non_string_id"])
def test_trace_row_without_id_is_skipped(bad_id: Any, caplog: pytest.LogCaptureFixture) -> None:
    rows = [_trace_row("tr-a"), _trace_row("x") | {"id": bad_id}, _trace_row("tr-c")]

    with caplog.at_level(logging.WARNING, logger="tripwire.langfuse_client"):
        traces = _client(_page_handler(rows, [])).recent_traces(SINCE)

    assert [t.id for t in traces] == ["tr-a", "tr-c"]
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_trace_with_bad_observation_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    rows = [_trace_row("tr-a"), _trace_row("tr-b"), _trace_row("tr-c")]
    observations = [
        _observation_row("ob-a", "tr-a"),
        _observation_row("ob-b", "tr-b") | {"calculatedTotalCost": "cheap"},
        _observation_row("ob-c", "tr-c"),
    ]

    with caplog.at_level(logging.WARNING, logger="tripwire.langfuse_client"):
        traces = _client(_page_handler(rows, observations)).recent_traces(SINCE)

    assert [[o.id for o in t.observations] for t in traces] == [["ob-a"], ["ob-c"]]
    assert [(r.levelno, "tr-b" in r.getMessage()) for r in caplog.records] == [(logging.WARNING, True)]


def test_observation_without_trace_id_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    observations = [_observation_row("ob-a", "tr-a"), _observation_row("ob-x", "tr-a") | {"traceId": None}]

    with caplog.at_level(logging.WARNING, logger="tripwire.langfuse_client"):
        traces = _client(_page_handler([_trace_row("tr-a")], observations)).recent_traces(SINCE)

    assert [[o.id for o in t.observations] for t in traces] == [["ob-a"]]
    assert [(r.levelno, "ob-x" in r.getMessage()) for r in caplog.records] == [(logging.WARNING, True)]


def test_clean_window_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="tripwire.langfuse_client"):
        _window()

    assert caplog.records == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (["not", "an", "object"], "not a JSON object"),
        ({"data": []}, "no 'meta'"),
        ({"meta": {"totalPages": 1}}, "no list 'data'"),
        ({"data": [1], "meta": {"totalPages": 1}}, "no list 'data'"),
        ({"data": [], "meta": {"totalPages": "1"}}, "no integer 'totalPages'"),
    ],
    ids=["body_not_dict", "no_meta", "no_data", "non_dict_rows", "bad_total_pages"],
)
def test_bad_envelope_still_raises(body: Any, message: str) -> None:
    with pytest.raises(LangfuseError, match=message):
        _client(lambda r: httpx.Response(200, json=body)).recent_traces(SINCE)


def test_unauthorized_window_still_raises() -> None:
    with pytest.raises(LangfuseError, match="refused the API keys"):
        _client(lambda r: httpx.Response(401, text="no")).recent_traces(SINCE)
