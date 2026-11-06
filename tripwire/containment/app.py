"""Containment service (`:8700`): the incident store and the only writer of `flags.json`.

Section 3 of tasks.md is the contract. Every read-modify-write of `incidents.json` and `flags.json` runs under
one process-wide lock, so the service must run with a single worker. Handlers are plain `def` routes: they run
in FastAPI's thread pool, and the lock is a `threading.Lock`.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, get_args
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict

from tripwire.contracts.config import TripwireConfig, load_config
from tripwire.contracts.models import (
    ACTIONS,
    TRANSITIONS,
    Action,
    ActionSource,
    Incident,
    IncidentState,
    incident_from_dict,
    incident_to_dict,
)
from tripwire.contracts.ports import Clock, ContainmentRefused

RULES: tuple[str, ...] = ("loop", "silent_error", "cost_spike", "hourly_ceiling")
STATES: frozenset[str] = frozenset(get_args(IncidentState))
CLOSED_STATES: frozenset[str] = frozenset({"resolved", "handed_off"})
REOPENABLE: frozenset[str] = frozenset({"contained", "verifying", "auto_paused"})
PATCHABLE: frozenset[str] = frozenset(
    {
        "state",
        "hit_count",
        "trace_ids",
        "cost_usd",
        "thread_ref",
        "root_cause",
        "pr_url",
        "rejections",
        "quiet_since",
        "resolved_at",
    }
)
PATCH_DATETIME_FIELDS: frozenset[str] = frozenset({"quiet_since", "resolved_at"})
SWITCH_APPROVAL = "switch-approval"
# Values the menu actions set. The config has no field for them, so they are fixed here.
MAX_STEPS_CAP = 20
FALLBACK_MODEL = "fallback-model"

INCIDENTS_FILE = "incidents.json"
FLAGS_FILE = "flags.json"
LOG_FILE = "containment.log"


class Refused(ContainmentRefused):
    """A refusal with the HTTP status the service answers with."""

    def __init__(self, reason: str, status: int = 409) -> None:
        super().__init__(reason)
        self.status = status


def _default_flags() -> dict[str, Any]:
    return {"disabled": False, "max_steps": None, "model": None}


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write to a temp file in the same directory, fsync it, then rename over the target."""
    tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class ContainmentStore:
    """Incident store and flags. Every public method takes the one lock; nothing else touches the files."""

    def __init__(self, cfg: TripwireConfig, clock: Clock, state_dir: Path) -> None:
        self._cfg = cfg
        self._clock = clock
        self._dir = state_dir
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)

        raw_incidents = _read_json(self._dir / INCIDENTS_FILE, {})
        self._next_number: int = raw_incidents.get("next_number", 1)
        self._owner_rounds: dict[str, int] = dict(raw_incidents.get("owner_rounds", {}))
        self._incidents: dict[str, Incident] = {
            key: incident_from_dict(value) for key, value in raw_incidents.get("incidents", {}).items()
        }

        raw_flags = _read_json(self._dir / FLAGS_FILE, {})
        self._flags: dict[str, dict[str, Any]] = dict(raw_flags.get("routes", {}))
        # incident id -> flags of its route before its active action (restored on replace or revert)
        self._snapshots: dict[str, dict[str, Any]] = dict(raw_flags.get("snapshots", {}))

    # ---- incidents -------------------------------------------------------

    def open_incident(self, rule: str, route: str, opened_at: datetime) -> Incident:
        with self._lock:
            if rule not in RULES:
                raise Refused(f"unknown rule {rule!r}", 422)
            for inc in self._incidents.values():
                if inc.rule == rule and inc.route == route and inc.state not in CLOSED_STATES:
                    raise Refused(f"an open incident already exists for rule {rule} on route {route}")
            inc = Incident(id=f"INC-{self._next_number}", rule=rule, route=route, opened_at=opened_at)
            self._next_number += 1
            self._incidents[inc.id] = inc
            self._persist_incidents()
            return deepcopy(inc)

    def get(self, incident_id: str) -> Incident:
        with self._lock:
            return deepcopy(self._require(incident_id))

    def list(self, open_only: bool = True) -> list[Incident]:
        with self._lock:
            return [
                deepcopy(inc)
                for inc in self._incidents.values()
                if not open_only or inc.state not in CLOSED_STATES
            ]

    def update(self, incident_id: str, fields: dict[str, Any]) -> Incident:
        with self._lock:
            inc = self._require(incident_id)
            for name in fields:
                if name not in PATCHABLE:
                    raise Refused(f"field {name!r} cannot be changed with PATCH", 422)
            new_state = fields.get("state")
            if new_state is not None and new_state != inc.state:
                self._check_transition(inc, new_state)
            for name, value in fields.items():
                if name in PATCH_DATETIME_FIELDS and isinstance(value, str):
                    value = _parse_datetime(name, value)
                setattr(inc, name, deepcopy(value))
            self._persist_incidents()
            return deepcopy(inc)

    def reopen(self, incident_id: str) -> Incident:
        with self._lock:
            inc = self._require(incident_id)
            if inc.state not in REOPENABLE:
                raise Refused(f"cannot reopen {incident_id} from state {inc.state}")
            inc.ask_round += 1
            inc.state = "awaiting_approval"
            self._persist_incidents()
            return deepcopy(inc)

    # ---- actions ---------------------------------------------------------

    def apply(
        self,
        incident_id: str,
        action: str,
        source: str,
        approver: str | None,
        spend_usd: float,
    ) -> dict[str, Any]:
        with self._lock:
            inc = self._require(incident_id)
            if action not in ACTIONS:
                raise Refused(f"action {action!r} is not on the menu", 422)
            if source == "owner":
                self._check_owner_action(inc, approver)
            elif source == "auto_pause":
                self._check_auto_pause(inc, action, spend_usd)
            else:
                raise Refused(f"unknown action source {source!r}", 422)

            # Replace, don't stack: restore what the active action changed, then apply the new one.
            if inc.action is not None:
                self._restore(inc)
            self._snapshots[inc.id] = deepcopy(self._route_flags(inc.route))
            self._apply_effect(inc.route, action)
            inc.action = action  # type: ignore[assignment]
            inc.action_source = source  # type: ignore[assignment]
            if source == "owner":
                now = self._clock.now()
                inc.state = "contained"
                inc.approver = approver
                inc.approved_at = now
                inc.contained_at = now
                self._owner_rounds[inc.id] = inc.ask_round
            else:
                inc.state = "auto_paused"
                inc.auto_paused = True
            self._persist(incidents=True, flags=True)
            self._log(
                "apply",
                inc.id,
                action=action,
                source=source,
                approver=approver,
                spend_usd=spend_usd,
            )
            return self._flags_view()

    def revert(self, incident_id: str, by: str | None) -> dict[str, Any]:
        with self._lock:
            inc = self._require(incident_id)
            if inc.action is None:
                raise Refused(f"{incident_id} has no active action to revert")
            self._check_approver(by, "revert")
            self._restore(inc)
            inc.action = None
            inc.action_source = None
            inc.state = "verifying"
            self._persist(incidents=True, flags=True)
            self._log("revert", inc.id, by=by)
            return self._flags_view()

    def flags(self) -> dict[str, Any]:
        with self._lock:
            return self._flags_view()

    # ---- helpers (call only with the lock held) --------------------------

    def _require(self, incident_id: str) -> Incident:
        inc = self._incidents.get(incident_id)
        if inc is None:
            raise Refused(f"unknown incident {incident_id}", 404)
        return inc

    def _check_transition(self, inc: Incident, new_state: str) -> None:
        if new_state not in STATES:
            raise Refused(f"unknown state {new_state!r}", 422)
        if new_state in ("contained", "auto_paused"):
            raise Refused(f"{new_state} is set only by /actions")
        if inc.state == "contained" and new_state == "verifying":
            if inc.action not in ("cap_max_steps", "fallback_model"):
                raise Refused("contained -> verifying needs an active cap_max_steps or fallback_model")
            return
        if new_state not in TRANSITIONS.get(inc.state, frozenset()):
            raise Refused(f"transition {inc.state} -> {new_state} is not allowed")

    def _check_owner_action(self, inc: Incident, approver: str | None) -> None:
        self._check_approver(approver, "approve")
        if inc.state != "awaiting_approval":
            raise Refused(f"owner actions need state awaiting_approval, not {inc.state}")
        if self._owner_rounds.get(inc.id) == inc.ask_round:
            raise Refused(f"an owner action was already accepted in ask round {inc.ask_round}")

    def _check_approver(self, who: str | None, verb: str) -> None:
        if who == SWITCH_APPROVAL:
            return
        if who is None or who not in self._cfg.owners:
            raise Refused(f"only owners can {verb}; {who!r} is not in owners")

    def _check_auto_pause(self, inc: Incident, action: str, spend_usd: float) -> None:
        if action != "disable_route":
            raise Refused("auto-pause only applies disable_route")
        if inc.auto_paused:
            raise Refused(f"{inc.id} was already auto-paused once")
        if inc.action is not None:
            raise Refused(f"{inc.id} already has an active action")
        route_cfg = self._cfg.routes.get(inc.route)
        if route_cfg is None:
            raise Refused(f"unknown route {inc.route!r}")
        auto = self._cfg.auto_pause
        # opened_at comes from the service's own record; the caller cannot supply it.
        elapsed_min = (self._clock.now() - inc.opened_at).total_seconds() / 60
        budget_hit = spend_usd >= auto.budget_fraction * route_cfg.loss_budget_usd
        if not (budget_hit or elapsed_min >= auto.minutes):
            raise Refused("auto-pause thresholds not reached")

    def _route_flags(self, route: str) -> dict[str, Any]:
        return self._flags.setdefault(route, _default_flags())

    def _restore(self, inc: Incident) -> None:
        self._flags[inc.route] = self._snapshots.pop(inc.id)

    def _apply_effect(self, route: str, action: str) -> None:
        flags = self._route_flags(route)
        if action == "disable_route":
            flags["disabled"] = True
        elif action == "cap_max_steps":
            flags["max_steps"] = MAX_STEPS_CAP
        elif action == "fallback_model":
            flags["model"] = FALLBACK_MODEL

    def _flags_view(self) -> dict[str, Any]:
        routes = {name: _default_flags() for name in self._cfg.routes}
        routes.update(deepcopy(self._flags))
        return {"routes": routes}

    def _persist_incidents(self) -> None:
        _write_json_atomic(
            self._dir / INCIDENTS_FILE,
            {
                "next_number": self._next_number,
                "owner_rounds": self._owner_rounds,
                "incidents": {key: incident_to_dict(value) for key, value in self._incidents.items()},
            },
        )

    def _persist_flags(self) -> None:
        _write_json_atomic(self._dir / FLAGS_FILE, {"routes": self._flags, "snapshots": self._snapshots})

    def _persist(self, *, incidents: bool, flags: bool) -> None:
        if flags:
            self._persist_flags()
        if incidents:
            self._persist_incidents()

    def _log(self, event: str, incident_id: str, **details: Any) -> None:
        entry = {"ts": self._clock.now().isoformat(), "event": event, "incident": incident_id, **details}
        with (self._dir / LOG_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _parse_datetime(name: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise Refused(f"{name} is not an ISO 8601 datetime", 422) from None
    if parsed.tzinfo is None:
        raise Refused(f"{name} must include a timezone", 422)
    return parsed


# ---- HTTP surface ---------------------------------------------------------


class OpenIncidentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: str
    route: str
    opened_at: AwareDatetime


class ApplyBody(BaseModel):
    # Extra keys (for example a caller-supplied opened_at) are ignored on purpose; see section 3.
    incident_id: str
    action: str
    source: str
    approver: str | None = None
    spend_usd: float = 0.0


class RevertBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    incident_id: str
    by: str | None = None


def get_store(request: Request) -> ContainmentStore:
    """Resolves the store built in lifespan. No logic: the store owns every rule."""
    store: ContainmentStore = request.app.state.store
    return store


# Module level on purpose: FastAPI resolves string annotations from module globals.
StoreDep = Annotated[ContainmentStore, Depends(get_store)]


class _Clock:
    """Real clock for the default app."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def create_app(config: TripwireConfig, clock: Clock, state_dir: Path) -> FastAPI:
    """Build the service. Nothing is opened here; the store is built in `lifespan`."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = ContainmentStore(config, clock, state_dir)
        yield

    app = FastAPI(title="Tripwire containment", lifespan=lifespan)

    @app.exception_handler(Refused)
    async def _refused(request: Request, exc: Refused) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"reason": exc.reason})

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        reason = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return JSONResponse(status_code=422, content={"reason": reason})

    @app.post("/incidents", status_code=201)
    def open_incident(body: OpenIncidentBody, store: StoreDep) -> dict[str, Any]:
        return incident_to_dict(store.open_incident(body.rule, body.route, body.opened_at))

    @app.get("/incidents")
    def list_incidents(store: StoreDep, open_only: bool = True) -> list[dict[str, Any]]:
        return [incident_to_dict(inc) for inc in store.list(open_only=open_only)]

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str, store: StoreDep) -> dict[str, Any]:
        return incident_to_dict(store.get(incident_id))

    @app.patch("/incidents/{incident_id}")
    def patch_incident(incident_id: str, body: dict[str, Any], store: StoreDep) -> dict[str, Any]:
        return incident_to_dict(store.update(incident_id, body))

    @app.post("/incidents/{incident_id}/reopen")
    def reopen_incident(incident_id: str, store: StoreDep) -> dict[str, Any]:
        return incident_to_dict(store.reopen(incident_id))

    @app.post("/actions")
    def apply_action(body: ApplyBody, store: StoreDep) -> dict[str, Any]:
        return store.apply(body.incident_id, body.action, body.source, body.approver, body.spend_usd)

    @app.post("/revert")
    def revert_action(body: RevertBody, store: StoreDep) -> dict[str, Any]:
        return store.revert(body.incident_id, body.by)

    @app.get("/flags")
    def get_flags(store: StoreDep) -> dict[str, Any]:
        return store.flags()

    return app


def create_default_app() -> FastAPI:
    """Entry point for `uvicorn --factory`. Reads the config file at boot, never at import time.

    `TRIPWIRE_CONFIG` (default `tripwire.yaml`) and `TRIPWIRE_STATE_DIR` (default `containment-state`).
    """
    config = load_config(os.environ.get("TRIPWIRE_CONFIG", "tripwire.yaml"))
    state_dir = Path(os.environ.get("TRIPWIRE_STATE_DIR", "containment-state"))
    return create_app(config, _Clock(), state_dir)
