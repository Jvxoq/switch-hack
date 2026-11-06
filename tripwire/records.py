"""Incident record writer: the final thread message and the `incidents.log` JSONL line (task P01)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tripwire.contracts.models import Incident

MISSING = "—"


def _ts(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _or_missing(value: Any) -> Any:
    return MISSING if value is None or value == "" else value


def _record(incident: Incident) -> dict[str, Any]:
    """The fields shared by the rendered message and the JSONL line. Missing optionals are None."""
    return {
        "id": incident.id,
        "rule": incident.rule,
        "route": incident.route,
        "root_cause": incident.root_cause,
        "action": incident.action,
        "action_source": incident.action_source,
        "approver": incident.approver,
        "opened_at": _ts(incident.opened_at),
        "approved_at": _ts(incident.approved_at),
        "contained_at": _ts(incident.contained_at),
        "resolved_at": _ts(incident.resolved_at),
        "cost_usd": incident.cost_usd,
        "pr_url": incident.pr_url,
        "rejections": incident.rejections,
    }


def render(incident: Incident) -> str:
    """Final thread message for an incident. Every field appears; missing optional fields show `—`."""
    rec = _record(incident)
    cost = f"${rec['cost_usd']:.2f}"
    lines = [
        f"Incident {rec['id']} — {rec['rule']} on route {rec['route']}",
        f"Root cause: {_or_missing(rec['root_cause'])}",
        f"Action: {_or_missing(rec['action'])}",
        f"Action source: {_or_missing(rec['action_source'])}",
        f"Approver: {_or_missing(rec['approver'])}",
        f"Opened: {_or_missing(rec['opened_at'])}",
        f"Approved: {_or_missing(rec['approved_at'])}",
        f"Contained: {_or_missing(rec['contained_at'])}",
        f"Resolved: {_or_missing(rec['resolved_at'])}",
        f"Cost burned: {cost}",
        f"PR: {_or_missing(rec['pr_url'])}",
        f"Rejections: {rec['rejections']}",
    ]
    return "\n".join(lines)


def append(incident: Incident, path: str | Path) -> None:
    """Append one JSON line for the incident to `incidents.log` (JSONL)."""
    line = json.dumps(_record(incident), sort_keys=True)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A crash mid-write can leave a last line with no newline. Start a new line so this record is not glued onto it.
    prefix = "\n" if target.is_file() and _ends_without_newline(target) else ""
    with target.open("a", encoding="utf-8") as fh:
        fh.write(prefix + line + "\n")


def _ends_without_newline(target: Path) -> bool:
    with target.open("rb") as fh:
        fh.seek(0, 2)
        if fh.tell() == 0:
            return False
        fh.seek(-1, 2)
        return fh.read(1) != b"\n"


def recorded_ids(path: str | Path) -> set[str]:
    """Incident ids that already have a line in the record log. A missing file has none.

    A torn line (a crash mid-write) is skipped, so that incident counts as not recorded and is written again.
    """
    target = Path(path)
    if not target.is_file():
        return set()
    ids: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            ids.add(data["id"])
    return ids
