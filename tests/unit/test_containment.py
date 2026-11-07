"""Containment service and HTTP client (S01). Section 3 of tasks.md is the contract.

Action-rule cases run twice through the `containment` fixture: once against `FakeContainment` and once against
the real service over HTTP (FastAPI TestClient, no socket). A case that passes on one and fails on the other
means the fake has drifted.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tripwire.containment import app as app_module
from tripwire.containment.app import create_app
from tripwire.containment.client import ContainmentHTTPClient
from tripwire.contracts.config import TripwireConfig, load_config_dict
from tripwire.contracts.models import Incident
from tripwire.contracts.ports import ContainmentClient, ContainmentRefused

# The TestClient warns that httpx is deprecated in favour of httpx2. The service is tested over httpx here.
pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`")

ROUTE = "order-lookup"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cfg() -> TripwireConfig:
    return load_config_dict({})  # defaults: owners [jason], loss budget $50, auto-pause 10 min or 50%


@pytest.fixture
def http_app(clock: FakeClock, cfg: TripwireConfig, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(cfg, clock, tmp_path)
    with TestClient(app) as http:  # `with` runs lifespan, which builds the store
        yield http


@pytest.fixture
def http_client(http_app: TestClient) -> ContainmentHTTPClient:
    return ContainmentHTTPClient(http=http_app)


@pytest.fixture
def fake(clock: FakeClock, cfg: TripwireConfig) -> FakeContainment:
    return FakeContainment(clock, cfg)


@pytest.fixture(params=["fake", "http"])
def containment(request: pytest.FixtureRequest, fake: FakeContainment, http_client: ContainmentHTTPClient) -> ContainmentClient:
    return fake if request.param == "fake" else http_client


def _open(c: ContainmentClient, clock: FakeClock, rule: str = "loop", route: str = ROUTE) -> Incident:
    return c.open_incident(rule, route, clock.now())


def _awaiting_approval(c: ContainmentClient, clock: FakeClock, rule: str = "loop", route: str = ROUTE) -> Incident:
    inc = _open(c, clock, rule, route)
    c.update(inc.id, state="investigating")
    c.update(inc.id, state="awaiting_approval")
    return inc


# ---- T10: refusals ---------------------------------------------------------


def test_T10_unknown_incident_refused(containment: ContainmentClient) -> None:
    with pytest.raises(ContainmentRefused, match="unknown incident"):
        containment.apply("INC-999", "disable_route", "owner", "jason", 0.0)


def test_T10_off_menu_action_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    with pytest.raises(ContainmentRefused, match="is not on the menu"):
        containment.apply(inc.id, "delete_everything", "owner", "jason", 0.0)


def test_T10_second_owner_action_same_round_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    # After an owner action the state is `contained`, so the state check refuses before the round check does.
    # Only /reopen starts a new round; test_reopen_allows_exactly_one_more_owner_action covers that path.
    with pytest.raises(ContainmentRefused, match="owner actions need state awaiting_approval"):
        containment.apply(inc.id, "fallback_model", "owner", "jason", 0.0)


def test_T10_auto_pause_with_active_action_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    with pytest.raises(ContainmentRefused, match="already has an active action"):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 100.0)


def test_T10_auto_pause_not_disable_route_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    with pytest.raises(ContainmentRefused, match="auto-pause only applies disable_route"):
        containment.apply(inc.id, "cap_max_steps", "auto_pause", None, 100.0)


def test_T10_auto_pause_before_budget_or_time_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    # Budget is $50 and the threshold is 0.5 of it, so $10 is below it. Nine minutes is below the 10-minute window.
    with pytest.raises(ContainmentRefused, match="auto-pause thresholds not reached"):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 10.0)
    clock.advance(minutes=9)
    with pytest.raises(ContainmentRefused, match="auto-pause thresholds not reached"):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 10.0)


def test_T10_caller_opened_at_ignored(http_app: TestClient, clock: FakeClock) -> None:
    """The service takes opened_at from its own record. A caller-supplied opened_at far in the past is ignored."""
    client = ContainmentHTTPClient(http=http_app)
    inc = _open(client, clock)
    forged = (clock.now() - timedelta(days=1)).isoformat()
    response = http_app.post(
        "/actions",
        json={
            "incident_id": inc.id,
            "action": "disable_route",
            "source": "auto_pause",
            "approver": None,
            "spend_usd": 0.0,
            "opened_at": forged,
        },
    )
    assert response.status_code == 409
    assert response.json() == {"reason": "auto-pause thresholds not reached"}


def test_auto_pause_by_budget_pauses_route(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    flags = containment.apply(inc.id, "disable_route", "auto_pause", None, 25.0)
    assert flags["routes"][ROUTE]["disabled"] is True
    assert containment.get(inc.id).state == "auto_paused"


def test_auto_pause_by_elapsed_time_pauses_route(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    clock.advance(minutes=10)  # spend is $0, so only the 10-minute window can trigger it
    flags = containment.apply(inc.id, "disable_route", "auto_pause", None, 0.0)
    assert flags["routes"][ROUTE]["disabled"] is True


def test_auto_pause_at_most_once_per_incident(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    containment.apply(inc.id, "disable_route", "auto_pause", None, 25.0)
    containment.reopen(inc.id)  # a new ask round does not reset the auto-pause
    with pytest.raises(ContainmentRefused, match="already auto-paused once"):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 25.0)


# ---- T12: revert and replace-don't-stack -----------------------------------


def test_T12_revert_restores_previous_flags(containment: ContainmentClient, clock: FakeClock) -> None:
    before = containment.flags()
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    containment.reopen(inc.id)
    containment.apply(inc.id, "fallback_model", "owner", "jason", 0.0)
    # Replace, don't stack: the step cap is gone, only the model is set.
    assert containment.flags()["routes"][ROUTE] == {"disabled": False, "max_steps": None, "model": "zai-org/GLM-5.3"}
    flags = containment.revert(inc.id, "jason")
    assert flags == before
    assert containment.get(inc.id).action is None
    assert containment.get(inc.id).state == "verifying"


def test_T12_replace_restores_before_applying(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    containment.apply(inc.id, "disable_route", "auto_pause", None, 25.0)
    assert containment.flags()["routes"][ROUTE]["disabled"] is True
    containment.reopen(inc.id)
    flags = containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    # The owner action restores the route first (re-enabled), then applies its own cap.
    assert flags["routes"][ROUTE] == {"disabled": False, "max_steps": 20, "model": None}


# ---- action rules and transitions -----------------------------------------


def test_reopen_allows_exactly_one_more_owner_action(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    reopened = containment.reopen(inc.id)
    assert (reopened.ask_round, reopened.state) == (2, "awaiting_approval")
    containment.apply(inc.id, "fallback_model", "owner", "jason", 0.0)
    with pytest.raises(ContainmentRefused, match="owner actions need state awaiting_approval"):
        containment.apply(inc.id, "disable_route", "owner", "jason", 0.0)


def test_owner_action_after_auto_pause_reenables_route(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    containment.apply(inc.id, "disable_route", "auto_pause", None, 25.0)
    containment.reopen(inc.id)
    flags = containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    assert flags["routes"][ROUTE]["disabled"] is False
    assert containment.get(inc.id).state == "contained"


def test_owner_action_needs_owner_approver(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    with pytest.raises(ContainmentRefused, match="only owners can approve"):
        containment.apply(inc.id, "cap_max_steps", "owner", "mallory", 0.0)
    with pytest.raises(ContainmentRefused, match="only owners can approve"):
        containment.apply(inc.id, "cap_max_steps", "owner", None, 0.0)


def test_switch_approval_skips_owner_check(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "switch-approval", 0.0)
    assert containment.get(inc.id).state == "contained"


def test_revert_by_non_owner_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _awaiting_approval(containment, clock)
    containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
    with pytest.raises(ContainmentRefused, match="only owners can revert"):
        containment.revert(inc.id, "mallory")
    assert containment.flags()["routes"][ROUTE]["max_steps"] == 20


def test_revert_without_active_action_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    with pytest.raises(ContainmentRefused, match="no active action to revert"):
        containment.revert(inc.id, "jason")


def test_illegal_patch_transitions_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    with pytest.raises(ContainmentRefused, match="transition detected -> resolved is not allowed"):
        containment.update(inc.id, state="resolved")
    with pytest.raises(ContainmentRefused, match="contained is set only by /actions"):
        containment.update(inc.id, state="contained")
    with pytest.raises(ContainmentRefused, match="cannot be changed with PATCH"):
        containment.update(inc.id, approver="jason")


def test_contained_to_verifying_only_for_non_disabling_action(containment: ContainmentClient, clock: FakeClock) -> None:
    disabled = _awaiting_approval(containment, clock, rule="loop")
    containment.apply(disabled.id, "disable_route", "owner", "jason", 0.0)
    with pytest.raises(ContainmentRefused, match="needs an active cap_max_steps or fallback_model"):
        containment.update(disabled.id, state="verifying")

    capped = _awaiting_approval(containment, clock, rule="silent_error")
    containment.apply(capped.id, "cap_max_steps", "owner", "jason", 0.0)
    assert containment.update(capped.id, state="verifying").state == "verifying"


def test_duplicate_open_incident_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    _open(containment, clock)
    with pytest.raises(ContainmentRefused, match="an open incident already exists"):
        _open(containment, clock)


def test_reopen_from_detected_refused(containment: ContainmentClient, clock: FakeClock) -> None:
    inc = _open(containment, clock)
    with pytest.raises(ContainmentRefused, match="cannot reopen"):
        containment.reopen(inc.id)


def test_list_returns_open_incidents_only(containment: ContainmentClient, clock: FakeClock) -> None:
    closed = _open(containment, clock, rule="loop")
    containment.update(closed.id, state="investigating")
    containment.update(closed.id, state="handed_off")
    still_open = _open(containment, clock, rule="silent_error")
    assert [i.id for i in containment.list(open_only=True)] == [still_open.id]
    assert {i.id for i in containment.list(open_only=False)} == {closed.id, still_open.id}


def test_flags_lists_every_configured_route(containment: ContainmentClient) -> None:
    assert containment.flags() == {"routes": {ROUTE: {"disabled": False, "max_steps": None, "model": None}}}


# ---- HTTP-only: concurrency, persistence, audit log -----------------------


def test_concurrent_patches_lose_no_update(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Twenty concurrent PATCHes each rewrite incidents.json. Every write must survive, on disk and in memory.

    Without the lock, a slower writer can finish after a faster one and put its stale snapshot on disk. The
    frequent thread switches and the zero-length yield below make that interleaving likely. A yield, not a wait.
    """
    real_write = app_module._write_json_atomic

    def yielding_write(path: Path, data: Any) -> None:
        time.sleep(0)
        real_write(path, data)

    monkeypatch.setattr(app_module, "_write_json_atomic", yielding_write)
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with TestClient(create_app(cfg, clock, tmp_path)) as http:
            client = ContainmentHTTPClient(http=http)
            ids = [client.open_incident("loop", f"route-{i}", clock.now()).id for i in range(20)]

            def patch(index: int) -> None:
                client.update(ids[index], hit_count=index + 1)

            with ThreadPoolExecutor(max_workers=20) as pool:
                list(pool.map(patch, range(20)))
    finally:
        sys.setswitchinterval(previous_interval)

    expected = {inc_id: index + 1 for index, inc_id in enumerate(ids)}
    on_disk = json.loads((tmp_path / "incidents.json").read_text(encoding="utf-8"))["incidents"]
    assert {key: value["hit_count"] for key, value in on_disk.items()} == expected
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        restored = ContainmentHTTPClient(http=http).list(open_only=False)
    assert {inc.id: inc.hit_count for inc in restored} == expected


def test_failed_write_keeps_previous_state(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the rename fails, the old file stays whole and the half-written temp file is removed."""
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        kept = _open(client, clock, rule="loop")

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(app_module.os, "replace", failing_replace)
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        with pytest.raises(OSError, match="disk full"):
            _open(client, clock, rule="silent_error")
    monkeypatch.undo()

    assert [p.name for p in tmp_path.glob("incidents.json*")] == ["incidents.json"]
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        assert [inc.id for inc in ContainmentHTTPClient(http=http).list(open_only=False)] == [kept.id]


def test_state_survives_restart_and_log_records_changes(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path
) -> None:
    app = create_app(cfg, clock, tmp_path)
    with TestClient(app) as http:
        client = ContainmentHTTPClient(http=http)
        inc = _awaiting_approval(client, clock)
        client.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
        flags_before = client.flags()

    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        restored = client.get(inc.id)
        assert (restored.state, restored.action, restored.approver) == ("contained", "cap_max_steps", "jason")
        assert client.flags() == flags_before
        # The snapshot survived the restart, so revert still restores the pre-action flags.
        client.revert(inc.id, "jason")
        assert client.flags()["routes"][ROUTE]["max_steps"] is None

    lines = (tmp_path / "containment.log").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert [(e["event"], e["incident"]) for e in events] == [("apply", inc.id), ("revert", inc.id)]
    assert {k: v for k, v in events[0].items() if k != "ts"} == {
        "event": "apply",
        "incident": inc.id,
        "action": "cap_max_steps",
        "source": "owner",
        "approver": "jason",
        "spend_usd": 0.0,
    }
    assert events[1]["by"] == "jason"


def test_refused_change_writes_no_log_line(http_app: TestClient, clock: FakeClock, tmp_path: Path) -> None:
    client = ContainmentHTTPClient(http=http_app)
    inc = _open(client, clock)
    with pytest.raises(ContainmentRefused):
        client.apply(inc.id, "disable_route", "auto_pause", None, 0.0)
    assert not (tmp_path / "containment.log").exists()


def test_http_client_maps_unknown_incident_to_refusal(http_client: ContainmentHTTPClient) -> None:
    with pytest.raises(ContainmentRefused) as refused:
        http_client.get("INC-404")
    assert refused.value.reason == "unknown incident INC-404"


# ---- O1: flags come from every active action on the route -----------------

# The fake in tests/fakes/containment.py still restores per-route snapshots, so this case runs on the HTTP service
# only. Fixing the fake is a separate change: it is outside the files this task may edit.


def test_T12_O1_revert_keeps_other_incident_action(http_client: ContainmentHTTPClient, clock: FakeClock) -> None:
    """Two incidents on one route: reverting one must not drop the other's active action.

    Repro from docs/verification.md O1: loop disable, cost_spike cap, revert loop. The route must stay capped.
    """
    loop = _awaiting_approval(http_client, clock, rule="loop")
    http_client.apply(loop.id, "disable_route", "owner", "jason", 0.0)
    spend = _awaiting_approval(http_client, clock, rule="cost_spike")
    http_client.apply(spend.id, "cap_max_steps", "owner", "jason", 0.0)
    assert http_client.flags()["routes"][ROUTE] == {"disabled": True, "max_steps": 20, "model": None}

    http_client.revert(loop.id, "jason")

    assert http_client.flags()["routes"][ROUTE] == {"disabled": False, "max_steps": 20, "model": None}
    assert http_client.get(spend.id).action == "cap_max_steps"
    http_client.revert(spend.id, "jason")
    assert http_client.flags()["routes"][ROUTE] == {"disabled": False, "max_steps": None, "model": None}


def test_O1_flags_file_matches_active_actions_after_restart(
    cfg: TripwireConfig, clock: FakeClock, tmp_path: Path
) -> None:
    """flags.json mirrors the flags derived from active actions, and a restart derives the same flags."""
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        loop = _awaiting_approval(client, clock, rule="loop")
        client.apply(loop.id, "disable_route", "owner", "jason", 0.0)
        spend = _awaiting_approval(client, clock, rule="cost_spike")
        client.apply(spend.id, "cap_max_steps", "owner", "jason", 0.0)
        client.revert(loop.id, "jason")
        flags = client.flags()

    stored = json.loads((tmp_path / "flags.json").read_text(encoding="utf-8"))
    assert stored == flags
    assert "snapshots" not in stored
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        assert ContainmentHTTPClient(http=http).flags() == flags


# ---- O2: persist before swapping memory -----------------------------------


@pytest.mark.parametrize("failing_file", ["incidents.json", "flags.json"])
def test_O2_failed_write_leaves_memory_and_files_unchanged(
    failing_file: str,
    cfg: TripwireConfig,
    clock: FakeClock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An owner action whose write fails changes neither memory nor disk, whichever file fails.

    When flags.json fails, incidents.json was already written and must be restored, so the files agree again.
    """
    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        # A first accepted action makes both files exist before the failing write.
        other = _awaiting_approval(client, clock, rule="silent_error")
        client.apply(other.id, "disable_route", "owner", "jason", 0.0)
        inc = _awaiting_approval(client, clock)
        flags_before = client.flags()
        incident_before = client.get(inc.id)
    incidents_bytes = (tmp_path / "incidents.json").read_bytes()
    flags_bytes = (tmp_path / "flags.json").read_bytes()
    log_bytes = (tmp_path / "containment.log").read_bytes()

    real_replace = os.replace

    def failing_replace(src: Any, dst: Any) -> None:
        if Path(dst).name == failing_file:
            raise OSError("disk full")
        real_replace(src, dst)

    with TestClient(create_app(cfg, clock, tmp_path)) as http:
        client = ContainmentHTTPClient(http=http)
        monkeypatch.setattr(app_module.os, "replace", failing_replace)
        with pytest.raises(OSError, match="disk full"):
            client.apply(inc.id, "cap_max_steps", "owner", "jason", 0.0)
        monkeypatch.undo()

        assert client.flags() == flags_before
        assert client.get(inc.id) == incident_before

    assert (tmp_path / "incidents.json").read_bytes() == incidents_bytes
    assert (tmp_path / "flags.json").read_bytes() == flags_bytes
    assert (tmp_path / "containment.log").read_bytes() == log_bytes
    assert [p.name for p in tmp_path.glob("*.tmp")] == []
