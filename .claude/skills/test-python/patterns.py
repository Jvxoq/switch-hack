"""Test helpers the test-python skill requires.

Copy what you need into tests/conftest.py, once.

Checked on 2026-09-19 against research_agent/backend: each helper passed on the real
code and failed on the break it exists for. After any edit to this file, run
`ruff check` and `mypy --strict` on it, and run it once against a real suite.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NoReturn

import pytest
from loguru import logger

if TYPE_CHECKING:
    from loguru import Record


@dataclass
class PeakGauge:
    """Hold every call open until the test opens the gate, and count them (P2)."""

    in_flight: int = 0
    peak: int = 0
    gate: asyncio.Event = field(default_factory=asyncio.Event)

    async def hold(self) -> None:
        """Count this call in, wait for the gate, then count it out."""
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await self.gate.wait()
        finally:
            self.in_flight -= 1


async def settle(rounds: int = 100) -> None:
    """Run every ready task until it blocks. Fakes do no I/O, so this ends.

    Needs the real ``asyncio.sleep``. A test that patched it globally breaks this (L11).
    """
    for _ in range(rounds):
        await asyncio.sleep(0)


async def hang(*args: object, **kwargs: object) -> NoReturn:
    """Never answer, like a dependency that stopped responding (P1)."""
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


def off_loop(answer: object) -> Callable[..., object]:
    """Return a fake sync function that fails on the event loop thread (P3)."""

    def fake(*args: object, **kwargs: object) -> object:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return answer
        raise AssertionError("a blocking call ran on the event loop thread")

    return fake


@dataclass
class SleepRecorder:
    """Stand in for an injected ``sleep``, recording each wait (P4)."""

    waits: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        """Record the wait, then yield once so other tasks still run."""
        self.waits.append(seconds)
        await asyncio.sleep(0)


@pytest.fixture
def log_records() -> Iterator[list[Record]]:
    """Collect every loguru record the test produces (P6, P8)."""
    records: list[Record] = []
    sink = logger.add(lambda message: records.append(message.record), level="DEBUG")
    yield records
    logger.remove(sink)


def logged(records: list[Record], min_level: int = 30) -> list[tuple[str, str, bool]]:
    """Return level name, message and whether an exception is attached (P6)."""
    return [
        (record["level"].name, record["message"], record["exception"] is not None)
        for record in records
        if record["level"].no >= min_level
    ]


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any test that opens a real connection or resolves a real name.

    Each attempt raises, and the test also fails at teardown, because code
    under test with a broad ``except`` can swallow the raise.
    """
    attempts: list[str] = []

    def refuse(*args: object, **kwargs: object) -> NoReturn:
        attempts.append(repr(args))
        raise AssertionError(f"a test reached the real network: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    yield
    assert attempts == [], f"a test reached the real network: {attempts}"
