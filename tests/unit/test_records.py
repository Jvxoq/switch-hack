"""T18: incident record writer renders every field and appends JSONL."""

import json
from datetime import datetime, timezone

from tripwire.contracts.models import Incident
from tripwire import records

T0 = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)


def _full() -> Incident:
    return Incident(
        id="INC-7",
        rule="loop",
        route="order-lookup",
        opened_at=T0,
        cost_usd=12.5,
        action="disable_route",
        action_source="owner",
        approver="jason",
        approved_at=T0,
        contained_at=T0,
        resolved_at=T0,
        pr_url="https://github.com/x/y/pull/1",
        root_cause="retry loop on empty page token",
        rejections=2,
    )


def _empty() -> Incident:
    return Incident(id="INC-8", rule="cost_spike", route="order-lookup", opened_at=T0)


def test_T18_render_contains_every_field_when_full():
    text = records.render(_full())
    for needle in [
        "INC-7",
        "loop",
        "order-lookup",
        "retry loop on empty page token",
        "disable_route",
        "owner",
        "jason",
        "2026-11-06T10:00:00+00:00",
        "$12.50",
        "https://github.com/x/y/pull/1",
        "Rejections: 2",
    ]:
        assert needle in text, needle
    assert "Approved:" in text and "Contained:" in text and "Resolved:" in text


def test_T18_render_uses_dash_for_missing_optionals():
    text = records.render(_empty())
    assert "Root cause: —" in text
    assert "Action: —" in text
    assert "Action source: —" in text
    assert "Approver: —" in text
    assert "Approved: —" in text
    assert "Contained: —" in text
    assert "Resolved: —" in text
    assert "PR: —" in text
    assert "Rejections: 0" in text
    assert "$0.00" in text


def test_T18_append_writes_jsonl_with_every_field(tmp_path):
    path = tmp_path / "incidents.log"
    records.append(_full(), path)
    records.append(_empty(), path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    expected = set(records._record(_full()).keys())
    assert set(first) == expected
    assert set(second) == expected
    assert first["approver"] == "jason"
    assert second["root_cause"] is None
