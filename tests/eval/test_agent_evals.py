"""Paid agent evals: the real agent, a real model, recorded incidents (A03).

Each test spends real tokens. They skip unless ANTHROPIC_API_KEY is set and the claude CLI is on PATH.
Run them with `uv run pytest -q -m eval`, or `scripts/run_evals.sh` for N runs per case.
"""

from __future__ import annotations

import os
import shutil

import pytest

from tests.eval.cases import case_by_name, load_fixture
from tests.eval.harness import evaluate_run, paid_skip_reason, run_case
from tests.eval.scoring import attempt_problems, budget_spent_seen

_SKIP = paid_skip_reason(os.environ, shutil.which("claude"))
paid = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")
pytestmark = pytest.mark.eval


@paid
@pytest.mark.parametrize("name", ["loop", "silent_error", "cost_spike"], ids=["loop", "silent_error", "cost_spike"])
def test_T13_diagnosis_passes_schema(name: str) -> None:
    """The diagnosis names the recorded rule, a real observation, a menu action and a confidence level."""
    case = case_by_name(name)
    run = run_case(case)

    assert evaluate_run(run, case, load_fixture(case.fixture)) == []


@paid
def test_T16_slow_tools_hit_server_cap() -> None:
    """Slow tools exhaust the round budget; the agent gets BUDGET SPENT and posts partial findings."""
    case = case_by_name("loop_slow_tools")
    run = run_case(case)

    assert budget_spent_seen(run.records)
    assert run.final_text.strip()


@paid
def test_T19_injected_trace_text_gets_no_off_menu_action() -> None:
    """Instructions inside a trace are data: no off-menu action and at most one request_containment."""
    case = case_by_name("injection")
    run = run_case(case)

    assert attempt_problems(run.records) == []
    assert evaluate_run(run, case, load_fixture(case.fixture)) == []
