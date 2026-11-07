from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.switch import FakeSwitch
from tripwire.contracts.config import TripwireConfig, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class NetworkBlocked(RuntimeError):
    """Raised when a unit test tries to reach a non-local host."""


def _host_of(address: Any) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


@pytest.fixture(autouse=True)
def no_real_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Refuse non-local connections unless the test is marked `live`."""
    if request.node.get_closest_marker("live") is not None:
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if _host_of(address) not in _LOCAL_HOSTS:
            raise NetworkBlocked(f"real network blocked in unit test: {address!r}")
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if _host_of(address) not in _LOCAL_HOSTS:
            raise NetworkBlocked(f"real network blocked in unit test: {address!r}")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield


@pytest.fixture
def cfg() -> TripwireConfig:
    return load_config(REPO_ROOT / "tripwire.yaml")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def langfuse() -> FakeLangfuse:
    return FakeLangfuse()


@pytest.fixture
def switch() -> FakeSwitch:
    return FakeSwitch()


@pytest.fixture
def containment(clock: FakeClock, cfg: TripwireConfig) -> FakeContainment:
    return FakeContainment(clock, cfg)
