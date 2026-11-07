"""Detector main loop and wiring (E04).

Every `poll_seconds`, one poll does, in order:
1. `TraceWindow.refresh()`. If Langfuse fails, the last good window is reused.
2. Every rule runs on the full window. A rule that raises is logged and the others still run.
3. Hits on open incidents that carry a trace the incident has not seen yet go to `Verifier.observe_hits`
   (a verifying or re-asked incident reopens when the rule fires again).
4. Every hit goes to `IncidentManager.ingest`.
5. `run_autopause`: auto-pause and the hourly ceiling. A containment refusal is logged inside it and skipped.
6. `Verifier.tick` over every incident that is not resolved: verify, resolve, and record handed-off incidents.
   A handed-off incident that already has a line in the record log is skipped. The record log is the only
   dedupe source across restarts, so a hand-off that happened while the detector was down is recorded on the
   next start, and a restart never writes a record twice.

Inside a step, each open incident (observe) is guarded too. The incident manager guards each (rule, route)
group (ingest). One bad incident or group is logged and the others still run. Each step is guarded, so one
failing step is logged and the loop keeps going. Incident state lives only in the containment service. The only things kept between polls are the last trace window and the de-duplication sets
that the verifier and the incident manager already hold.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
import httpx

from tripwire import records
from tripwire.clock import SystemClock
from tripwire.containment.client import ContainmentHTTPClient
from tripwire.contracts.config import (
    ConfigError,
    TripwireConfig,
    load_config,
    resolve_langfuse_host,
    resolve_secret,
)
from tripwire.contracts.models import Incident, RuleHit, Trace
from tripwire.contracts.ports import (
    Clock,
    ContainmentClient,
    LangfuseReader,
    Rule,
    SwitchPoster,
)
from tripwire.detector.autopause import run_autopause
from tripwire.detector.incidents import IncidentManager
from tripwire.detector.verify import Verifier
from tripwire.detector.window import TraceWindow
from tripwire.langfuse_client import LangfuseClient
from tripwire.rules.cost_spike import CostSpikeRule
from tripwire.rules.loop import LoopRule
from tripwire.rules.silent_error import SilentErrorRule
from tripwire.switch_client import SwitchError, build_poster

log = logging.getLogger(__name__)

def default_rules(cfg: TripwireConfig) -> list[Rule]:
    """The three rules. The loop rule gets its allow-list from config, since `RulesConfig` does not carry it."""
    return [LoopRule(cfg.allow_list_tools), SilentErrorRule(), CostSpikeRule()]


class Detector:
    def __init__(
        self,
        *,
        cfg: TripwireConfig,
        reader: LangfuseReader,
        containment: ContainmentClient,
        switch: SwitchPoster,
        clock: Clock,
        rules: Iterable[Rule],
        write_record: Callable[[Incident], str],
        recorded_ids: Callable[[], set[str]],
    ) -> None:
        self._cfg = cfg
        self._containment = containment
        self._switch = switch
        self._clock = clock
        self._rules = list(rules)
        self._window = TraceWindow(reader, clock, minutes=cfg.window_minutes)
        self._incidents = IncidentManager(containment, switch, clock)
        self._verifier = Verifier(
            containment=containment,
            switch=switch,
            clock=clock,
            cfg=cfg,
            write_record=write_record,
        )
        self._recorded_ids = recorded_ids
        self._last_traces: list[Trace] = []

    def poll(self) -> list[str]:
        """One poll. Returns one line per change, for logs and tests. Never raises for a step's failure."""
        events: list[str] = []
        try:
            self._last_traces = self._window.refresh()
        except Exception:
            log.exception("trace refresh failed; using the last window")
            events.append("trace refresh failed")
        traces = self._last_traces

        hits = self._evaluate(traces, events)
        self._guarded("observe", lambda: self._observe(hits), events)
        self._guarded("ingest", lambda: self._ingest(hits), events)
        self._guarded("auto-pause", lambda: self._autopause(traces), events)
        self._guarded("verify", self._verify, events)
        return events

    # ---- steps -----------------------------------------------------------

    def _evaluate(self, traces: list[Trace], events: list[str]) -> list[RuleHit]:
        now = self._clock.now()
        hits: list[RuleHit] = []
        for rule in self._rules:
            try:
                hits.extend(rule.evaluate(traces, self._cfg.rules, now))
            except Exception:
                log.exception("rule %s failed", getattr(rule, "name", rule))
                events.append(f"rule {getattr(rule, 'name', rule)} failed")
        return hits

    def _observe(self, hits: list[RuleHit]) -> list[str]:
        events: list[str] = []
        for inc in self._containment.list(open_only=True):
            new = [
                hit
                for hit in hits
                if (hit.rule, hit.route) == (inc.rule, inc.route)
                and hit.trace_id not in inc.trace_ids
            ]
            if not new:
                continue
            try:
                line = self._verifier.observe_hits(inc, new)
            except Exception:
                log.exception("observe failed for %s", inc.id)
                events.append(f"observe failed for {inc.id}")
                continue
            if line:
                events.append(line)
        return events

    def _ingest(self, hits: list[RuleHit]) -> list[str]:
        return self._incidents.ingest(hits)

    def _autopause(self, traces: list[Trace]) -> list[str]:
        pauses = run_autopause(
            containment=self._containment,
            switch=self._switch,
            clock=self._clock,
            cfg=self._cfg,
            traces=traces,
            ingest=self._ingest_one,
        )
        return [
            f"{p.incident_id}: auto-paused {p.route} at ${p.spend_usd:.2f}"
            for p in pauses
        ]

    def _ingest_one(self, hit: RuleHit) -> None:
        # The hourly ceiling incident must exist before auto-pause lists the open incidents, so ingest now.
        # The manager logs a failure and returns it as an event. Raise it so auto-pause still sees the failure.
        events = self._incidents.ingest([hit])
        if events:
            raise RuntimeError(events[0])

    def _verify(self) -> list[str]:
        incidents = self._containment.list(open_only=False)
        recorded = self._recorded_ids()
        # A handed-off incident already in the record log was recorded by an earlier run (or this one).
        tracked = [
            inc
            for inc in incidents
            if inc.state != "resolved"
            and not (inc.state == "handed_off" and inc.id in recorded)
        ]
        return self._verifier.tick(tracked)

    def _guarded(
        self, label: str, step: Callable[[], list[str] | None], events: list[str]
    ) -> None:
        try:
            result = step()
        except Exception:
            log.exception("detector step %s failed", label)
            events.append(f"{label} failed")
            return
        if result:
            events.extend(result)


def run(
    detector: Detector,
    *,
    poll_seconds: float,
    sleep: Callable[[float], object] = time.sleep,
    polls: int | None = None,
) -> None:
    """Poll forever, or `polls` times when given. An exception from a poll is logged and never ends the loop."""
    count = 0
    while polls is None or count < polls:
        try:
            for line in detector.poll():
                log.info("%s", line)
        except Exception:
            log.exception("detector poll failed")
        count += 1
        sleep(poll_seconds)


def make_write_record(records_path: str) -> Callable[[Incident], str]:
    """Append the incident's record to the record log and return the text to post in its thread."""

    def write_record(incident: Incident) -> str:
        records.append(incident, records_path)
        return records.render(incident)

    return write_record


def make_reader(
    cfg: TripwireConfig,
    host: str,
    public_key: str,
    secret_key: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> LangfuseClient:
    """The Langfuse client with the configured page cap. `transport` is for tests only."""
    return LangfuseClient(
        host,
        public_key,
        secret_key,
        max_pages=cfg.langfuse_max_pages,
        transport=transport,
    )


def resolve_records_path(flag: str | None, cfg: TripwireConfig) -> str:
    """The --records flag wins; otherwise the config's `records_path`."""
    return flag if flag is not None else cfg.records_path


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m tripwire.detector")
    parser.add_argument("--config", required=True, help="path to tripwire.yaml")
    parser.add_argument(
        "--records",
        default=None,
        help="where incident records are appended (default: records_path from the config)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    env = dict(os.environ if environ is None else environ)
    try:
        cfg = load_config(args.config)
        public_key = resolve_secret(cfg, "langfuse_public_key", env)
        secret_key = resolve_secret(cfg, "langfuse_secret_key", env)
        host = resolve_langfuse_host(cfg, env)
        records_path = resolve_records_path(args.records, cfg)
        switch = build_poster(env)
    except (ConfigError, SwitchError) as err:
        log.error("%s", err)
        return 2

    reader = make_reader(cfg, host, public_key, secret_key)
    containment = ContainmentHTTPClient(cfg.containment_url)
    detector = Detector(
        cfg=cfg,
        reader=reader,
        containment=containment,
        switch=switch,
        clock=SystemClock(),
        rules=default_rules(cfg),
        write_record=make_write_record(records_path),
        recorded_ids=lambda: records.recorded_ids(records_path),
    )
    try:
        run(detector, poll_seconds=cfg.poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()
        containment.close()
        switch.close()
    return 0
