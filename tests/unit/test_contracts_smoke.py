from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.fakes.clock import DEFAULT_START, FakeClock
from tests.fakes.containment import FakeContainment
from tests.fakes.langfuse import FakeLangfuse
from tests.fakes.switch import FakeSwitch
from tests.fakes.traces import make_trace
from tripwire.contracts import models
from tripwire.contracts.config import ConfigError, load_config_dict, resolve_secret
from tripwire.contracts.models import Incident, incident_from_dict, incident_to_dict
from tripwire.contracts.ports import (
    Clock,
    ContainmentClient,
    ContainmentRefused,
    LangfuseReader,
    Rule,
    SwitchPoster,
)


# ---- config ----------------------------------------------------------------


def test_config_defaults_match_section_3(cfg):
    assert cfg.poll_seconds == 15
    assert cfg.rules.loop.max_repeats == 5 and cfg.rules.loop.max_observations == 25
    assert cfg.rules.silent_error.count == 3 and cfg.rules.silent_error.window_minutes == 5
    assert cfg.rules.silent_error.patterns == ["error", "not found"]
    assert cfg.rules.cost_spike.median_multiplier == 5 and cfg.rules.cost_spike.per_trace_usd == 1.0
    assert cfg.allow_list_tools == ["list_orders_page"]
    assert cfg.routes["order-lookup"].loss_budget_usd == 50
    assert cfg.routes["order-lookup"].hourly_ceiling_usd == 50
    assert cfg.auto_pause.minutes == 10 and cfg.auto_pause.budget_fraction == 0.5
    assert cfg.verify_minutes == 5
    assert cfg.tripwire_guard.max_tool_calls == 20 and cfg.tripwire_guard.max_minutes == 3
    assert cfg.owners == ["jason", "winjasdan2"]
    assert cfg.window_minutes == 60
    assert cfg.containment_url == "http://127.0.0.1:8700"


def test_config_error_is_readable():
    with pytest.raises(ConfigError) as info:
        load_config_dict({"rules": {"loop": {"max_repeats": 0}}, "bogus": 1}, source="x.yaml")
    message = str(info.value)
    assert message.startswith("invalid config x.yaml:")
    assert "rules.loop.max_repeats" in message
    assert "bogus" in message


def test_resolve_secret_reads_env_var_by_name(cfg):
    assert resolve_secret(cfg, "github_token", {"GITHUB_TOKEN": "abc"}) == "abc"
    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        resolve_secret(cfg, "github_token", {})


# ---- models ------------------------------------------------------------------


def test_contract_modules_import():
    assert models.TRANSITIONS["verifying"] == frozenset({"resolved"})
    assert {Clock, ContainmentClient, LangfuseReader, Rule, SwitchPoster}


def test_incident_round_trips_through_dict():
    inc = Incident(id="INC-7", rule="loop", route="order-lookup", opened_at=DEFAULT_START, trace_ids=["t1"])
    inc.contained_at = DEFAULT_START + timedelta(minutes=2)
    back = incident_from_dict(incident_to_dict(inc))
    assert back == inc


# ---- fakes -------------------------------------------------------------------


def test_fake_clock_advances(clock: FakeClock):
    start = clock.now()
    clock.advance(minutes=2, seconds=30)
    assert clock.now() - start == timedelta(minutes=2, seconds=30)


def test_make_trace_builds_observations():
    t = make_trace(calls=[("tool", {"q": 1}, "ok", "DEFAULT", 0.25), ("tool", {}, "err", "ERROR", 0.5, "lookup")])
    assert t.route == "order-lookup"
    assert t.end_time is None
    assert [o.name for o in t.observations] == ["tool", "lookup"]
    assert t.total_cost_usd == 0.75
    done = make_trace(running=False, calls=[("tool", {}, None, "DEFAULT", 0)])
    assert done.end_time is not None


def test_fake_langfuse_returns_latest_version(langfuse: FakeLangfuse):
    t = make_trace(trace_id="tr-1", running=True)
    langfuse.put(t)
    langfuse.put(make_trace(trace_id="tr-1", running=False, calls=[("tool", {}, "x", "DEFAULT", 1.0)]))
    assert langfuse.get_trace("tr-1").end_time is not None
    assert [x.id for x in langfuse.recent_traces(DEFAULT_START)] == ["tr-1"]
    assert langfuse.recent_traces(DEFAULT_START + timedelta(days=1)) == []


def test_fake_switch_records_calls(switch: FakeSwitch, containment: FakeContainment):
    inc = containment.open_incident("loop", "order-lookup", DEFAULT_START)
    ref = switch.post_alert(inc, "loop on order-lookup")
    switch.set_status(ref, "investigating")
    switch.reply(ref, "details")
    assert switch.alerts[0]["incident_id"] == inc.id
    assert switch.status_updates == [{"thread_ref": ref, "text": "investigating"}]
    assert switch.replies == [{"thread_ref": ref, "text": "details"}]


def test_fake_containment_opens_and_refuses_duplicate(containment: FakeContainment):
    first = containment.open_incident("loop", "order-lookup", DEFAULT_START)
    assert first.id == "INC-1" and first.state == "detected"
    with pytest.raises(ContainmentRefused):
        containment.open_incident("loop", "order-lookup", DEFAULT_START)
    assert [i.id for i in containment.list()] == ["INC-1"]


def test_fake_containment_patch_rejects_bad_field_and_transition(containment: FakeContainment):
    inc = containment.open_incident("loop", "order-lookup", DEFAULT_START)
    with pytest.raises(ContainmentRefused):
        containment.update(inc.id, approver="someone")
    with pytest.raises(ContainmentRefused):
        containment.update(inc.id, state="resolved")
    with pytest.raises(ContainmentRefused):
        containment.update(inc.id, state="contained")
    assert containment.update(inc.id, state="investigating").state == "investigating"


def test_fake_containment_owner_action_and_one_per_round(containment: FakeContainment, clock: FakeClock):
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    containment.update(inc.id, state="investigating")
    containment.update(inc.id, state="awaiting_approval")
    flags = containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0)
    assert flags["routes"]["order-lookup"]["max_steps"] == 20
    got = containment.get(inc.id)
    assert got.state == "contained" and got.approver == "jason"
    with pytest.raises(ContainmentRefused):
        containment.apply(inc.id, "disable_route", "owner", "jason", 0)  # same ask round
    with pytest.raises(ContainmentRefused):
        containment.apply(inc.id, "disable_route", "owner", "mallory", 0)  # not an owner


def test_fake_containment_auto_pause_then_owner_replaces(containment: FakeContainment, clock: FakeClock):
    inc = containment.open_incident("cost_spike", "order-lookup", clock.now())
    with pytest.raises(ContainmentRefused):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 1.0)  # below threshold, 0 minutes
    flags = containment.apply(inc.id, "disable_route", "auto_pause", None, 30.0)  # 0.5 * $50 reached
    assert flags["routes"]["order-lookup"]["disabled"] is True
    assert containment.get(inc.id).state == "auto_paused"
    with pytest.raises(ContainmentRefused):
        containment.apply(inc.id, "disable_route", "auto_pause", None, 99.0)  # only once per incident
    containment.reopen(inc.id)  # ask round 2, does not use the owner round
    flags = containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0)
    assert flags["routes"]["order-lookup"] == {"disabled": False, "max_steps": 20, "model": None}
    assert containment.get(inc.id).ask_round == 2


def test_fake_containment_revert_restores_flags(containment: FakeContainment, clock: FakeClock):
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    containment.update(inc.id, state="investigating")
    containment.update(inc.id, state="awaiting_approval")
    containment.apply(inc.id, "fallback_model", "owner", "switch-approval", 0)
    assert containment.flags()["routes"]["order-lookup"]["model"] == "zai-org/GLM-5.3"
    flags = containment.revert(inc.id, "jason")
    assert flags["routes"]["order-lookup"]["model"] is None
    got = containment.get(inc.id)
    assert got.action is None and got.state == "verifying"
    assert containment.update(inc.id, state="resolved").state == "resolved"
    assert containment.log[-1]["event"] == "revert"


def test_fake_containment_replace_restores_previous_action(containment: FakeContainment, clock: FakeClock):
    inc = containment.open_incident("loop", "order-lookup", clock.now())
    containment.update(inc.id, state="investigating")
    containment.update(inc.id, state="awaiting_approval")
    containment.apply(inc.id, "disable_route", "owner", "jason", 0)
    containment.reopen(inc.id)
    flags = containment.apply(inc.id, "cap_max_steps", "owner", "jason", 0)
    assert flags["routes"]["order-lookup"] == {"disabled": False, "max_steps": 20, "model": None}
    assert len(containment.log) == 2
