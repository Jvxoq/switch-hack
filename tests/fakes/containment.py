"""In-memory ContainmentClient with the same action rules and state transitions as section 3 of tasks.md.

Route flags are derived the same way the real service derives them (C-FIX6): defaults plus every ACTIVE incident
action on that route. Any disable disables the route; the strictest step cap wins. There are no per-route snapshots,
so reverting one incident never drops another incident's action. `tests/unit/test_containment_fake_parity.py` runs
the same operations against this fake and the real `ContainmentStore` and asserts identical results.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from tripwire.contracts.config import TripwireConfig
from tripwire.contracts.models import (
    ACTIONS,
    TRANSITIONS,
    Action,
    ActionSource,
    Incident,
)
from tripwire.contracts.ports import ContainmentRefused

RULES = ("loop", "silent_error", "cost_spike", "hourly_ceiling")
STATES = frozenset(TRANSITIONS) | {"resolved", "handed_off", "contained", "auto_paused"}
CLOSED_STATES = frozenset({"resolved", "handed_off"})
# Fields PATCH may change (state is checked against TRANSITIONS separately).
PATCHABLE = frozenset(
    {"state", "hit_count", "trace_ids", "cost_usd", "thread_ref", "root_cause", "pr_url", "rejections",
     "quiet_since", "resolved_at"}
)
SWITCH_APPROVAL = "switch-approval"
REOPENABLE = frozenset({"contained", "verifying", "auto_paused"})


def _default_flags() -> dict[str, Any]:
    return {"disabled": False, "max_steps": None, "model": None}


class FakeContainment:
    def __init__(
        self,
        clock: Any,
        cfg: TripwireConfig,
        *,
        max_steps_cap: int = 20,
        fallback_model: str = "fallback-model",
    ) -> None:
        self._clock = clock
        self._cfg = cfg
        self._max_steps_cap = max_steps_cap
        self._fallback_model = fallback_model
        self._incidents: dict[str, Incident] = {}
        self._counter = 0
        # incident id -> ask round in which an owner action was accepted
        self._owner_round: dict[str, int] = {}
        self.log: list[dict[str, Any]] = []

    # ---- incidents -------------------------------------------------------

    def open_incident(self, rule: str, route: str, opened_at: datetime) -> Incident:
        if rule not in RULES:
            raise ContainmentRefused(f"unknown rule {rule!r}")
        for inc in self._incidents.values():
            if inc.rule == rule and inc.route == route and inc.state not in CLOSED_STATES:
                raise ContainmentRefused(f"an open incident already exists for rule {rule} on route {route}")
        self._counter += 1
        inc = Incident(id=f"INC-{self._counter}", rule=rule, route=route, opened_at=opened_at)
        self._incidents[inc.id] = inc
        return deepcopy(inc)

    def get(self, incident_id: str) -> Incident:
        return deepcopy(self._require(incident_id))

    def list(self, open_only: bool = True) -> list[Incident]:
        return [
            deepcopy(inc)
            for inc in self._incidents.values()
            if not open_only or inc.state not in CLOSED_STATES
        ]

    def update(self, incident_id: str, **fields: Any) -> Incident:
        inc = self._require(incident_id)
        for name in fields:
            if name not in PATCHABLE:
                raise ContainmentRefused(f"field {name!r} cannot be changed with PATCH")
        new_state = fields.get("state")
        if new_state is not None and new_state != inc.state:
            self._check_transition(inc, new_state)
        for name, value in fields.items():
            setattr(inc, name, deepcopy(value))
        return deepcopy(inc)

    def reopen(self, incident_id: str) -> Incident:
        inc = self._require(incident_id)
        if inc.state not in REOPENABLE:
            raise ContainmentRefused(f"cannot reopen {incident_id} from state {inc.state}")
        inc.ask_round += 1
        inc.state = "awaiting_approval"
        return deepcopy(inc)

    # ---- actions ---------------------------------------------------------

    def apply(
        self,
        incident_id: str,
        action: Action,
        source: ActionSource,
        approver: str | None,
        spend_usd: float,
    ) -> dict[str, Any]:
        inc = self._require(incident_id)
        if action not in ACTIONS:
            raise ContainmentRefused(f"action {action!r} is not on the menu")
        if source == "owner":
            self._check_owner_action(inc, approver)
        elif source == "auto_pause":
            self._check_auto_pause(inc, action, spend_usd)
        else:
            raise ContainmentRefused(f"unknown action source {source!r}")

        # Replace, don't stack: the incident's one action slot takes the new action. Flags are derived from
        # every active action, so the old one stops counting and the other incidents' actions are untouched.
        inc.action = action
        inc.action_source = source
        if source == "owner":
            inc.state = "contained"
            inc.approver = approver
            inc.approved_at = self._clock.now()
            inc.contained_at = inc.approved_at
            self._owner_round[inc.id] = inc.ask_round
        else:
            inc.state = "auto_paused"
            inc.auto_paused = True
        self._log("apply", inc.id, action=action, source=source, approver=approver, spend_usd=spend_usd)
        return self.flags()

    def revert(self, incident_id: str, by: str) -> dict[str, Any]:
        inc = self._require(incident_id)
        if inc.action is None:
            raise ContainmentRefused(f"{incident_id} has no active action to revert")
        self._check_approver(by, "revert")
        inc.action = None
        inc.action_source = None
        inc.state = "verifying"
        self._log("revert", inc.id, by=by)
        return self.flags()

    def flags(self) -> dict[str, Any]:
        routes = {name: _default_flags() for name in self._cfg.routes}
        for inc in self._incidents.values():
            if inc.action is not None:
                self._apply_effect(routes.setdefault(inc.route, _default_flags()), inc.action)
        return {"routes": routes}

    # ---- helpers ---------------------------------------------------------

    def _require(self, incident_id: str) -> Incident:
        inc = self._incidents.get(incident_id)
        if inc is None:
            raise ContainmentRefused(f"unknown incident {incident_id}")
        return inc

    def _check_transition(self, inc: Incident, new_state: str) -> None:
        if new_state not in STATES:
            raise ContainmentRefused(f"unknown state {new_state!r}")
        if new_state == "contained" or new_state == "auto_paused":
            raise ContainmentRefused(f"{new_state} is set only by /actions")
        if inc.state == "contained" and new_state == "verifying":
            if inc.action not in ("cap_max_steps", "fallback_model"):
                raise ContainmentRefused("contained -> verifying needs an active cap_max_steps or fallback_model")
            return
        if new_state not in TRANSITIONS.get(inc.state, frozenset()):
            raise ContainmentRefused(f"transition {inc.state} -> {new_state} is not allowed")

    def _check_owner_action(self, inc: Incident, approver: str | None) -> None:
        self._check_approver(approver, "approve")
        if inc.state != "awaiting_approval":
            raise ContainmentRefused(f"owner actions need state awaiting_approval, not {inc.state}")
        if self._owner_round.get(inc.id) == inc.ask_round:
            raise ContainmentRefused(f"an owner action was already accepted in ask round {inc.ask_round}")

    def _check_approver(self, who: str | None, verb: str) -> None:
        if who == SWITCH_APPROVAL:
            return
        if who is None or who not in self._cfg.owners:
            raise ContainmentRefused(f"only owners can {verb}; {who!r} is not in owners")

    def _check_auto_pause(self, inc: Incident, action: str, spend_usd: float) -> None:
        if action != "disable_route":
            raise ContainmentRefused("auto-pause only applies disable_route")
        if inc.auto_paused:
            raise ContainmentRefused(f"{inc.id} was already auto-paused once")
        if inc.action is not None:
            raise ContainmentRefused(f"{inc.id} already has an active action")
        route_cfg = self._cfg.routes.get(inc.route)
        if route_cfg is None:
            raise ContainmentRefused(f"unknown route {inc.route!r}")
        budget = route_cfg.loss_budget_usd
        auto = self._cfg.auto_pause
        elapsed_min = (self._clock.now() - inc.opened_at).total_seconds() / 60
        if not (spend_usd >= auto.budget_fraction * budget or elapsed_min >= auto.minutes):
            raise ContainmentRefused("auto-pause thresholds not reached")

    def _apply_effect(self, flags: dict[str, Any], action: str) -> None:
        if action == "disable_route":
            flags["disabled"] = True
        elif action == "cap_max_steps":
            current = flags["max_steps"]
            flags["max_steps"] = self._max_steps_cap if current is None else min(current, self._max_steps_cap)
        elif action == "fallback_model":
            flags["model"] = self._fallback_model

    def _log(self, event: str, incident_id: str, **details: Any) -> None:
        entry = {"ts": self._clock.now().isoformat(), "event": event, "incident": incident_id, **details}
        self.log.append(entry)
