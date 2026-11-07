"""The demo agent reads its route flags from a real containment service over HTTP.

Runs uvicorn in a thread on loopback with a temp state dir, so the flags file and the HTTP path are real.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from demo_agent.agent import QUESTIONS, ContainmentFlags, run_order_lookup
from demo_agent.cli import main
from demo_agent.llm import ScriptedModel, prices_from_env
from demo_agent.recording import TraceRecorder
from tests.fakes.clock import FakeClock
from tripwire.containment.app import create_app
from tripwire.containment.client import ContainmentHTTPClient
from tripwire.contracts.config import TripwireConfig

ROUTE = "order-lookup"
SERVER_START_SECONDS = 5.0


@dataclass
class RunningService:
    url: str
    state_dir: Path
    client: ContainmentHTTPClient
    clock: FakeClock
    _server: uvicorn.Server = field(repr=False)
    _thread: threading.Thread = field(repr=False)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=SERVER_START_SECONDS)


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def service(tmp_path: Path, cfg: TripwireConfig, clock: FakeClock) -> Iterator[RunningService]:
    app = create_app(cfg, clock, tmp_path)
    port = _free_loopback_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + SERVER_START_SECONDS
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("containment service did not start")
        time.sleep(0.01)

    url = f"http://127.0.0.1:{port}"
    running = RunningService(
        url=url,
        state_dir=tmp_path,
        client=ContainmentHTTPClient(url),
        clock=clock,
        _server=server,
        _thread=thread,
    )
    try:
        yield running
    finally:
        running.client.close()
        running.stop()


def _open_and_ask_owner(service: RunningService) -> str:
    """Open a loop incident and move it to awaiting_approval, the only state an owner action accepts."""
    incident = service.client.open_incident("loop", ROUTE, service.clock.now())
    service.client.update(incident.id, state="investigating")
    service.client.update(incident.id, state="awaiting_approval")
    return incident.id


class ApplyOnSecondModelCall:
    """Wraps the scripted loop model. The owner's disable_route lands while the run is in progress."""

    def __init__(self, service: RunningService, incident_id: str) -> None:
        self._service = service
        self._incident_id = incident_id
        self._inner = ScriptedModel("loop")
        self.calls = 0

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 2:
            self._service.client.apply(self._incident_id, "disable_route", "owner", "jason", 0.0)
        return self._inner.create(**kwargs)


def test_T11_disable_route_stops_loop_on_next_step(service: RunningService) -> None:
    """Disabling the route mid-run stops the agent before its third model call."""
    incident_id = _open_and_ask_owner(service)
    model = ApplyOnSecondModelCall(service, incident_id)
    flags = ContainmentFlags(service.url, http=httpx.Client())

    result = run_order_lookup(
        QUESTIONS[0],
        bug="loop",
        model=model,
        model_name="scripted",
        flags=flags,
        recorder=TraceRecorder(prices=prices_from_env({})),
    )

    assert (result.status, model.calls) == ("route disabled", 2)


def test_T11_cli_reads_flags_from_service_url(service: RunningService, capsys: pytest.CaptureFixture[str]) -> None:
    """The offline CLI honours TRIPWIRE_CONTAINMENT_URL, so a route disabled before start is never run."""
    incident_id = _open_and_ask_owner(service)
    service.client.apply(incident_id, "disable_route", "owner", "jason", 0.0)

    code = main(["run", "--bug", "loop", "--offline"], env={"TRIPWIRE_CONTAINMENT_URL": service.url})

    assert (code, "status=route disabled" in capsys.readouterr().out) == (0, True)


def test_T11_disable_is_written_to_flags_file(service: RunningService) -> None:
    """The disable is persisted to the flags file the service owns, not only held in memory."""
    incident_id = _open_and_ask_owner(service)
    service.client.apply(incident_id, "disable_route", "owner", "jason", 0.0)

    stored = json.loads((service.state_dir / "flags.json").read_text(encoding="utf-8"))

    assert stored["routes"][ROUTE]["disabled"] is True
