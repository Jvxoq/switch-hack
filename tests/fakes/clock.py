"""Settable, advanceable clock for tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEFAULT_START = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: datetime = DEFAULT_START) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def set(self, when: datetime) -> None:
        self._now = when

    def advance(self, *, seconds: float = 0, minutes: float = 0) -> datetime:
        self._now = self._now + timedelta(seconds=seconds, minutes=minutes)
        return self._now
