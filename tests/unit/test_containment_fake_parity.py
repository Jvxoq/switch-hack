"""The containment fake must match the real store, step for step (C-FIX8, drift O1).

Each scenario is a list of operations. The same list runs against `FakeContainment` and against the real
`ContainmentStore` in a tmp dir. After every step the test records the outcome (the result or the refusal reason)
and the route flags. At the end it records every incident and the audit log. Both runs must produce the same record.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tripwire.containment.app import ContainmentStore
from tripwire.contracts.config import TripwireConfig, load_config_dict
from tripwire.contracts.ports import SWITCH_APPROVAL, ContainmentRefused

ROUTE = "order-lookup"
OTHER_ROUTE = "checkout"  # not in the default config, so the flags must come from the incident
DEFAULT_FLAGS = {"disabled": False, "max_steps": None, "model": None}

Step = Callable[[Any, FakeClock], Any]


@pytest.fixture
def cfg() -> TripwireConfig:
    return load_config_dict({})  # the defaults: owner jason, $50 loss budget, auto-pause at 10 minutes or 50%


class _StoreClient:
    """Gives `ContainmentStore` the `ContainmentClient` call shape the fake uses (PATCH takes **fields)."""

    def __init__(self, store: ContainmentStore) -> None:
        self._store = store

    def open_incident(self, rule: str, route: str, opened_at: Any) -> Any:
        return self._store.open_incident(rule, route, opened_at)

    def get(self, incident_id: str) -> Any:
        return self._store.get(incident_id)

    def list(self, open_only: bool = True) -> Any:
        return self._store.list(open_only=open_only)

    def update(self, incident_id: str, **fields: Any) -> Any:
        return self._store.update(incident_id, fields)

    def reopen(self, incident_id: str) -> Any:
        return self._store.reopen(incident_id)

    def apply(self, incident_id: str, action: str, source: str, approver: str | None, spend_usd: float) -> Any:
        return self._store.apply(incident_id, action, source, approver, spend_usd)

    def revert(self, incident_id: str, by: str) -> Any:
        return self._store.revert(incident_id, by)

    def flags(self) -> Any:
        return self._store.flags()


# ---- operations ------------------------------------------------------------


def _open(rule: str, route: str = ROUTE) -> Step:
    return lambda c, k: c.open_incident(rule, route, k.now())


def _move(incident_id: str, state: str) -> Step:
    return lambda c, k: c.update(incident_id, state=state)


def _set(incident_id: str, **fields: Any) -> Step:
    return lambda c, k: c.update(incident_id, **fields)


def _apply(
    incident_id: str,
    action: str,
    source: str = "owner",
    approver: str | None = "jason",
    spend: float = 0.0,
) -> Step:
    return lambda c, k: c.apply(incident_id, action, source, approver, spend)


def _reopen(incident_id: str) -> Step:
    return lambda c, k: c.reopen(incident_id)


def _revert(incident_id: str, by: str = "jason") -> Step:
    return lambda c, k: c.revert(incident_id, by)


def _wait(minutes: int) -> Step:
    def advance(c: Any, k: FakeClock) -> None:
        k.advance(minutes=minutes)

    return advance


def _awaiting(incident_id: str, rule: str, route: str = ROUTE) -> list[Step]:
    """Open an incident and move it to awaiting_approval, the state an owner action needs."""
    return [_open(rule, route), _move(incident_id, "investigating"), _move(incident_id, "awaiting_approval")]


# ---- scenarios -------------------------------------------------------------

# Two incidents on one route: the loop disable, then the cost_spike cap, then revert the loop. The route must stay capped.
_REPRO_BEFORE_REVERT: list[Step] = [
    *_awaiting("INC-1", "loop"),
    _apply("INC-1", "disable_route"),
    *_awaiting("INC-2", "cost_spike"),
    _apply("INC-2", "cap_max_steps"),
]

SCENARIOS: dict[str, list[Step]] = {
    "two_incident_repro": [*_REPRO_BEFORE_REVERT, _revert("INC-1"), _revert("INC-2")],
    "replace_does_not_stack": [
        *_awaiting("INC-1", "loop"),
        _apply("INC-1", "cap_max_steps"),
        _reopen("INC-1"),
        _apply("INC-1", "fallback_model"),
        _revert("INC-1"),
    ],
    "auto_pause_then_owner_replaces": [
        _open("cost_spike"),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=25.0),
        _reopen("INC-1"),
        _apply("INC-1", "cap_max_steps"),
        _revert("INC-1"),
    ],
    "auto_pause_under_other_cap": [
        *_awaiting("INC-1", "silent_error"),
        _apply("INC-1", "cap_max_steps"),
        _open("loop"),
        _apply("INC-2", "disable_route", source="auto_pause", approver=None, spend=30.0),
        _revert("INC-1"),
        _revert("INC-2"),
    ],
    "stacked_caps_revert_one": [
        *_awaiting("INC-1", "loop"),
        _apply("INC-1", "cap_max_steps"),
        *_awaiting("INC-2", "cost_spike"),
        _apply("INC-2", "cap_max_steps"),
        _revert("INC-1"),
        _revert("INC-2"),
    ],
    "other_route_untouched": [
        *_awaiting("INC-1", "loop", ROUTE),
        _apply("INC-1", "disable_route"),
        *_awaiting("INC-2", "loop", OTHER_ROUTE),
        _apply("INC-2", "fallback_model"),
        _revert("INC-1"),
    ],
    "contained_to_verifying_rules": [
        *_awaiting("INC-1", "loop"),
        _apply("INC-1", "disable_route"),
        _move("INC-1", "verifying"),
        *_awaiting("INC-2", "silent_error"),
        _apply("INC-2", "cap_max_steps", approver=SWITCH_APPROVAL),
        _move("INC-2", "verifying"),
        _move("INC-2", "resolved"),
    ],
    "refusals_and_auto_pause_thresholds": [
        _apply("INC-9", "disable_route"),
        _open("loop"),
        _apply("INC-1", "delete_everything"),
        _apply("INC-1", "disable_route", source="mystery"),
        _apply("INC-1", "cap_max_steps", approver="mallory"),
        _apply("INC-1", "cap_max_steps"),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=24.99),
        _apply("INC-1", "cap_max_steps", source="auto_pause", approver=None, spend=100.0),
        _set("INC-1", state="resolved"),
        _set("INC-1", state="contained"),
        _set("INC-1", approver="jason"),
        _reopen("INC-1"),
        _revert("INC-1"),
        _open("loop"),
        _move("INC-1", "investigating"),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=0.0),
        _wait(9),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=0.0),
        _wait(1),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=0.0),
        _apply("INC-1", "disable_route", source="auto_pause", approver=None, spend=99.0),
        _apply("INC-1", "cap_max_steps"),
        _revert("INC-1", by="mallory"),
        _reopen("INC-1"),
        _apply("INC-1", "cap_max_steps"),
        _apply("INC-1", "fallback_model"),
        _apply("INC-1", "cap_max_steps", source="auto_pause", approver=None, spend=100.0),
        _revert("INC-1", by=SWITCH_APPROVAL),
        _revert("INC-1"),
    ],
}


# ---- running a scenario ----------------------------------------------------


def _norm(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    return value


def _play(client: Any, clock: FakeClock, steps: list[Step]) -> list[tuple[Any, Any]]:
    """Run every step. Record each outcome and the flags after it, then every incident."""
    record: list[tuple[Any, Any]] = []
    for step in steps:
        try:
            outcome: tuple[str, Any] = ("ok", _norm(step(client, clock)))
        except ContainmentRefused as exc:
            outcome = ("refused", exc.reason)
        record.append((outcome, client.flags()))
    incidents = [_norm(inc) for inc in client.list(open_only=False)]
    record.append((("incidents", incidents), None))
    return record


def _fake_log(fake: FakeContainment) -> list[dict[str, Any]]:
    return [{k: v for k, v in entry.items() if k != "ts"} for entry in fake.log]


def _store_log(state_dir: Path) -> list[dict[str, Any]]:
    path = state_dir / "containment.log"
    if not path.exists():
        return []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [{k: v for k, v in entry.items() if k != "ts"} for entry in lines]


# ---- tests -----------------------------------------------------------------


@pytest.mark.parametrize("scenario", list(SCENARIOS), ids=list(SCENARIOS))
def test_fake_matches_store_step_for_step(scenario: str, cfg: TripwireConfig, tmp_path: Path) -> None:
    """Outcomes, refusal reasons, flags after each step, final incidents and the audit log all match."""
    fake_clock, store_clock = FakeClock(), FakeClock()
    fake = FakeContainment(fake_clock, cfg)
    store = _StoreClient(ContainmentStore(cfg, store_clock, tmp_path))

    fake_record = _play(fake, fake_clock, SCENARIOS[scenario])
    store_record = _play(store, store_clock, SCENARIOS[scenario])

    assert fake_record == store_record
    assert _fake_log(fake) == _store_log(tmp_path)


@pytest.mark.parametrize("impl", ["fake", "store"])
def test_two_incident_repro_keeps_route_capped(impl: str, cfg: TripwireConfig, tmp_path: Path) -> None:
    """Revert the loop disable while the cost_spike cap is active: the route stays capped, not re-enabled."""
    clock = FakeClock()
    client: Any = FakeContainment(clock, cfg) if impl == "fake" else _StoreClient(ContainmentStore(cfg, clock, tmp_path))
    for step in _REPRO_BEFORE_REVERT:
        step(client, clock)
    assert client.flags()["routes"][ROUTE] == {"disabled": True, "max_steps": 20, "model": None}

    _revert("INC-1")(client, clock)

    assert client.flags()["routes"][ROUTE] == {"disabled": False, "max_steps": 20, "model": None}
    assert client.get("INC-2").action == "cap_max_steps"


def test_parity_check_catches_a_drifted_step_cap(cfg: TripwireConfig, tmp_path: Path) -> None:
    """A fake whose cap differs from the store's must fail the same comparison, or the comparison proves nothing."""
    steps = SCENARIOS["two_incident_repro"]
    drifted_clock, store_clock = FakeClock(), FakeClock()
    drifted = FakeContainment(drifted_clock, cfg, max_steps_cap=5)
    store = _StoreClient(ContainmentStore(cfg, store_clock, tmp_path))

    assert _play(drifted, drifted_clock, steps) != _play(store, store_clock, steps)
