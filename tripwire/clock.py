from datetime import UTC, datetime


class SystemClock:
    """Wall clock in UTC: `now()` returns `datetime.now(UTC)`."""

    def now(self) -> datetime:
        return datetime.now(UTC)
