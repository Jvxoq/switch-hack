"""Detector: verify, resolve, reopen.

Moves incidents after an action through `verifying` -> `resolved`, reopens them when the rule fires again,
keeps a disabled route's status up to date, and records every handed-off incident.

Incident state is read and changed only through the ContainmentClient. Records are rendered, appended and
posted through `write_record`, which the caller injects (it wraps `tripwire.records`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from tripwire.contracts.config import TripwireConfig
from tripwire.contracts.models import NON_DISABLING_ACTIONS, Incident, RuleHit
from tripwire.contracts.ports import Clock, ContainmentClient, ContainmentRefused, SwitchPoster

# Renders the record for an incident, appends it to the record log, and returns the text to post.
WriteRecord = Callable[[Incident], str]

log = logging.getLogger(__name__)


class Verifier:
    def __init__(
        self,
        *,
        containment: ContainmentClient,
        switch: SwitchPoster,
        clock: Clock,
        cfg: TripwireConfig,
        write_record: WriteRecord,
    ) -> None:
        self._containment = containment
        self._switch = switch
        self._clock = clock
        self._verify = timedelta(minutes=cfg.verify_minutes)
        self._write_record = write_record
        # Notification de-duplication only (not incident state): status texts already posted, and
        # incidents whose record was already written in this process.
        self._status_posted: set[tuple[str, str]] = set()
        self._recorded: set[str] = set()
        self._unthreaded_status_logged: set[str] = set()

    def tick(self, incidents: Iterable[Incident]) -> list[str]:
        """Advance each incident one step. Returns one line per change, for logs and tests."""
        events: list[str] = []
        for inc in incidents:
            try:
                event = self._advance(inc)
            except ContainmentRefused as err:
                event = f"{inc.id}: refused: {err.reason}"
            except Exception:
                # One incident's failure (for example Switch down for its thread) must not stop the others.
                log.exception("verify step failed for %s", inc.id)
                event = f"{inc.id}: verify failed"
            if event:
                events.append(event)
        return events

    def observe_hits(self, inc: Incident, hits: list[RuleHit]) -> str | None:
        """New hits for an incident's rule and route. Reopens it if the action does not stop the hits."""
        if not hits:
            return None
        reopens = inc.state == "verifying" or (inc.state == "contained" and inc.action != "disable_route")
        if not reopens:
            return None
        reopened = self._containment.reopen(inc.id)
        self._reply(inc, "still firing, re-asking @tripwire")
        return f"{inc.id}: reopened, ask round {reopened.ask_round}"

    def on_handed_off(self, inc: Incident) -> str | None:
        """Render, append and post the record of a handed-off incident. Once per incident per process."""
        if inc.id in self._recorded:
            return None
        self._post_record(inc)
        self._recorded.add(inc.id)
        return f"{inc.id}: recorded (handed_off)"

    def _advance(self, inc: Incident) -> str | None:
        now = self._clock.now()
        if inc.state == "handed_off":
            return self.on_handed_off(inc)
        if inc.state == "contained" and inc.action in NON_DISABLING_ACTIONS:
            self._containment.update(inc.id, state="verifying", quiet_since=now)
            return f"{inc.id}: verifying"
        if inc.state == "verifying":
            return self._check_quiet(inc, now)
        # Not verifying: the quiet clock restarts when verification does, so drop any stale start.
        if inc.quiet_since is not None:
            self._containment.update(inc.id, quiet_since=None)
        if inc.state in ("contained", "auto_paused") and inc.action == "disable_route":
            return self._post_disabled_status(inc)
        return None

    def _check_quiet(self, inc: Incident, now: datetime) -> str | None:
        if inc.quiet_since is None:
            # Verification started without a stamp (e.g. after a revert): start the quiet clock now.
            self._containment.update(inc.id, quiet_since=now)
            return f"{inc.id}: verifying, quiet clock started"
        if now - inc.quiet_since < self._verify:
            return None
        resolved = self._containment.update(inc.id, state="resolved", resolved_at=now)
        self._post_record(resolved)
        return f"{inc.id}: resolved"

    def _post_disabled_status(self, inc: Incident) -> str | None:
        # A disabled route is always quiet, so quiet proves nothing: wait for the owner's revert.
        text = f"route disabled — owner runs revert {inc.id} once the fix is live"
        if inc.thread_ref is None:
            if inc.id not in self._unthreaded_status_logged:
                self._unthreaded_status_logged.add(inc.id)
                log.warning("no Switch thread for %s: disabled-route status not posted", inc.id)
            return None
        if (inc.id, text) in self._status_posted:
            return None
        self._switch.set_status(inc.thread_ref, text)
        self._status_posted.add((inc.id, text))
        return f"{inc.id}: status posted (route disabled)"

    def _post_record(self, inc: Incident) -> None:
        text = self._write_record(inc)
        self._reply(inc, text)

    def _reply(self, inc: Incident, text: str) -> None:
        if inc.thread_ref is None:
            log.warning("no Switch thread for %s: dropped reply %r", inc.id, text)
            return
        self._switch.reply(inc.thread_ref, text)
