"""T17: verify, resolve, reopen. Uses the fakes for containment, Switch and the clock."""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.switch import FakeSwitch
from tripwire.contracts.config import TripwireConfig
from tripwire.contracts.models import RuleHit
from tripwire.detector.verify import Verifier


def _written(inc):
    return f"RECORD {inc.id} state={inc.state}"


@pytest.fixture
def records_log() -> list[str]:
    return []


@pytest.fixture
def verifier(containment: FakeContainment, switch: FakeSwitch, clock: FakeClock, cfg: TripwireConfig, records_log):
    def write_record(inc):
        records_log.append(inc.id)
        return _written(inc)

    return Verifier(containment=containment, switch=switch, clock=clock, cfg=cfg, write_record=write_record)


def _open_and_contain(containment: FakeContainment, clock: FakeClock, action: str):
    """Open an incident, ask the owner, and apply `action` (owner or auto-pause as the action requires)."""
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    containment.update(inc.id, state="investigating")
    containment.update(inc.id, state="awaiting_approval")
    containment.apply(inc.id, action, "owner", "jason", spend_usd=1.0)
    return containment.get(inc.id)


def _set_thread(containment: FakeContainment, switch: FakeSwitch, inc_id: str) -> None:
    containment.update(inc_id, thread_ref=switch.post_alert(containment.get(inc_id), "alert"))


def _hit(inc) -> RuleHit:
    return RuleHit(
        rule="loop",
        route=inc.route,
        trace_id="trace-x",
        observation_ids=["o1"],
        cost_usd=0.1,
        at=FakeClock().now(),
        detail="repeat",
    )


def test_T17_cap_max_steps_moves_to_verifying_then_resolves_after_5_quiet_minutes(
    verifier, containment, clock, switch, records_log
):
    inc = _open_and_contain(containment, clock, "cap_max_steps")
    _set_thread(containment, switch, inc.id)

    events = verifier.tick(containment.list())
    assert containment.get(inc.id).state == "verifying"
    assert events == [f"{inc.id}: verifying"]

    clock.advance(minutes=4)
    verifier.tick(containment.list())
    assert containment.get(inc.id).state == "verifying"

    clock.advance(minutes=1)
    verifier.tick(containment.list())
    resolved = containment.get(inc.id)
    assert resolved.state == "resolved"
    assert resolved.resolved_at == clock.now()
    assert records_log == [inc.id]
    assert switch.replies[-1]["text"] == _written(resolved)


def test_T17_disable_route_never_resolves_before_revert(verifier, containment, clock, switch, records_log):
    inc = _open_and_contain(containment, clock, "disable_route")
    _set_thread(containment, switch, inc.id)

    verifier.tick(containment.list())
    assert containment.get(inc.id).state == "contained"
    assert switch.status_updates == [
        {
            "thread_ref": containment.get(inc.id).thread_ref,
            "text": f"route disabled — owner runs revert {inc.id} once the fix is live",
        }
    ]

    clock.advance(minutes=30)
    verifier.tick(containment.list())
    assert containment.get(inc.id).state == "contained"
    assert len(switch.status_updates) == 1
    assert records_log == []


def test_T17_revert_then_5_quiet_minutes_resolves(verifier, containment, clock, switch, records_log):
    inc = _open_and_contain(containment, clock, "disable_route")
    _set_thread(containment, switch, inc.id)
    verifier.tick(containment.list())

    containment.revert(inc.id, by="jason")
    assert containment.get(inc.id).state == "verifying"

    verifier.tick(containment.list())
    assert containment.get(inc.id).quiet_since == clock.now()

    clock.advance(minutes=5)
    verifier.tick(containment.list())
    assert containment.get(inc.id).state == "resolved"
    assert records_log == [inc.id]


def test_T17_quiet_clock_starts_at_revert_not_at_contain_time(verifier, containment, clock, switch):
    inc = _open_and_contain(containment, clock, "disable_route")
    _set_thread(containment, switch, inc.id)
    verifier.tick(containment.list())

    clock.advance(minutes=20)
    containment.revert(inc.id, by="jason")
    verifier.tick(containment.list())
    clock.advance(minutes=4)
    verifier.tick(containment.list())
    assert containment.get(inc.id).state == "verifying"


def test_T17_still_firing_reopens_with_ask_round_2(verifier, containment, clock, switch):
    inc = _open_and_contain(containment, clock, "cap_max_steps")
    _set_thread(containment, switch, inc.id)
    verifier.tick(containment.list())
    clock.advance(minutes=2)

    current = containment.get(inc.id)
    event = verifier.observe_hits(current, [_hit(current)])

    reopened = containment.get(inc.id)
    assert event == f"{inc.id}: reopened, ask round 2"
    assert reopened.state == "awaiting_approval"
    assert reopened.ask_round == 2
    assert switch.replies[-1]["text"] == "still firing, re-asking @tripwire"

    verifier.tick(containment.list())
    assert containment.get(inc.id).quiet_since is None


def test_T17_hits_while_contained_with_disable_route_do_not_reopen(verifier, containment, clock, switch):
    inc = _open_and_contain(containment, clock, "disable_route")
    _set_thread(containment, switch, inc.id)
    assert verifier.observe_hits(containment.get(inc.id), [_hit(inc)]) is None
    assert containment.get(inc.id).ask_round == 1


def test_T17_handed_off_appends_record_once(verifier, containment, clock, switch, records_log):
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    _set_thread(containment, switch, inc.id)
    containment.update(inc.id, state="investigating")
    containment.update(inc.id, state="handed_off")
    handed = containment.get(inc.id)

    assert verifier.on_handed_off(handed) == f"{inc.id}: recorded (handed_off)"
    assert verifier.on_handed_off(handed) is None
    assert records_log == [inc.id]
    assert switch.replies[-1]["text"] == _written(handed)


def test_T17_tick_leaves_open_incidents_without_action_alone(verifier, containment, clock, switch):
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    _set_thread(containment, switch, inc.id)
    clock.advance(minutes=10)
    assert verifier.tick(containment.list()) == []
    assert containment.get(inc.id).state == "detected"
    assert switch.status_updates == [] and switch.replies == []


def test_T17_refusal_is_reported_and_does_not_stop_other_incidents(verifier, containment, clock, switch):
    real = _open_and_contain(containment, clock, "cap_max_steps")
    _set_thread(containment, switch, real.id)
    ghost = dataclasses.replace(real, id="INC-999")  # unknown to the service: every call is refused

    events = verifier.tick([ghost, containment.get(real.id)])

    assert events == ["INC-999: refused: unknown incident INC-999", f"{real.id}: verifying"]
    assert containment.get(real.id).state == "verifying"
