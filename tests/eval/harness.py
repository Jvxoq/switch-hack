"""Headless runs of the Tripwire agent through `claude -p` (A03).

The run uses the same instructions and the same six-tool server as the Switch room. Permission prompts go to
`approval_stub`, which records each one and declines it. Nothing here calls the API unless `run_case` is called,
and the paid tests and `scripts/run_evals.sh` are the only callers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.eval.cases import REPO_ROOT, EvalCase, IncidentFixture, case_by_name, load_fixture
from tests.eval.scoring import attempt_problems, budget_spent_seen, diagnosis_problems, extract_diagnosis

INSTRUCTIONS_PATH = REPO_ROOT / "tripwire_agent" / "instructions.md"
SERVER_NAME = "tripwire"
PERMISSION_TOOL = f"mcp__{SERVER_NAME}__approval_stub"
# Read and note tools run without a prompt. request_containment and revert_containment always reach the stub.
ALLOWED_TOOLS: tuple[str, ...] = tuple(
    f"mcp__{SERVER_NAME}__{name}" for name in ("langfuse_read", "flags_read", "incident_read", "update_incident")
)
PROMPT_TEMPLATE = (
    "[detector alert] {incident_id} rule={rule} route={route} trace_id={trace_id} opened_at={opened_at}. "
    "Investigate it under your instructions. End your final message with one fenced json block holding exactly "
    "these keys: rule, observation_ids, cost_so_far_usd, action, confidence, root_cause."
)
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_BUDGET_USD = 1.00
DEFAULT_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class RunResult:
    case: str
    run_index: int
    final_text: str
    is_error: bool
    exit_code: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    records: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    stderr_tail: str = ""


def paid_skip_reason(environ: Mapping[str, str], claude_path: str | None) -> str | None:
    """Why a paid eval must skip, or None when it may run. Paid runs need the key and the `claude` CLI."""
    if not environ.get("ANTHROPIC_API_KEY"):
        return "paid eval: ANTHROPIC_API_KEY is not set"
    if not claude_path:
        return "paid eval: the claude CLI is not on PATH"
    return None


def build_prompt(fixture: IncidentFixture) -> str:
    return PROMPT_TEMPLATE.format(
        incident_id=fixture.incident_id,
        rule=fixture.rule,
        route=fixture.route,
        trace_id=fixture.trigger_trace_id,
        opened_at=fixture.opened_at.isoformat(),
    )


def build_mcp_config(case: EvalCase, record_path: Path, python: str = sys.executable) -> dict[str, Any]:
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": python,
                "args": ["-m", "tests.eval.mcp_server"],
                "cwd": str(REPO_ROOT),
                "env": {
                    "TRIPWIRE_EVAL_CASE": case.name,
                    "TRIPWIRE_EVAL_RECORD": str(record_path),
                    "PYTHONPATH": str(REPO_ROOT),
                },
            }
        }
    }


def build_command(
    *,
    claude_path: str,
    mcp_config_path: Path,
    model: str,
    budget_usd: float,
    instructions: str,
) -> list[str]:
    """The `claude -p` argv. The prompt goes on stdin. `--allowedTools` is variadic, so it comes last."""
    return [
        claude_path,
        "-p",
        "--output-format", "json",
        "--model", model,
        "--mcp-config", str(mcp_config_path),
        "--strict-mcp-config",
        "--tools", "",
        "--permission-prompt-tool", PERMISSION_TOOL,
        "--max-budget-usd", f"{budget_usd:.2f}",
        "--append-system-prompt", instructions,
        "--allowedTools", *ALLOWED_TOOLS,
    ]


def parse_claude_output(stdout: str) -> dict[str, Any]:
    """Final text, error flag, cost and token counts from `claude -p --output-format json`.

    The CLI prints one result object, or a list of messages that ends with one. Missing usage counts as zero.
    """
    payload = json.loads(stdout)
    items = payload if isinstance(payload, list) else [payload]
    result = next((item for item in reversed(items) if isinstance(item, dict) and item.get("type") == "result"), {})
    usage = result.get("usage") or {}
    return {
        "final_text": str(result.get("result") or ""),
        "is_error": bool(result.get("is_error", True)),
        "cost_usd": float(result.get("total_cost_usd") or 0.0),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
    }


def _read_records(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return tuple(records)


def run_case(
    case: EvalCase,
    *,
    run_index: int = 1,
    model: str = DEFAULT_MODEL,
    budget_usd: float = DEFAULT_BUDGET_USD,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> RunResult:
    """Run the agent once on one recorded incident. Spends real money: call only with ANTHROPIC_API_KEY set."""
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise RuntimeError("the claude CLI is not on PATH")
    fixture = load_fixture(case.fixture)
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="tripwire-eval-") as workdir:
        work = Path(workdir)
        record_path = work / "records.jsonl"
        config_path = work / "mcp.json"
        config_path.write_text(json.dumps(build_mcp_config(case, record_path)), encoding="utf-8")
        command = build_command(
            claude_path=claude_path,
            mcp_config_path=config_path,
            model=model,
            budget_usd=budget_usd,
            instructions=instructions,
        )
        env = dict(os.environ)
        env["TRIPWIRE_EVAL_CASE"] = case.name
        try:
            completed = subprocess.run(
                command,
                input=build_prompt(fixture),
                capture_output=True,
                text=True,
                cwd=workdir,
                env=env,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RunResult(case.name, run_index, "", True, -9, 0.0, 0, 0, 0, 0,
                             records=_read_records(record_path), stderr_tail="timed out")
        records = _read_records(record_path)
        stderr_tail = completed.stderr[-2000:]
        try:
            parsed = parse_claude_output(completed.stdout)
        except ValueError:
            return RunResult(case.name, run_index, "", True, completed.returncode, 0.0, 0, 0, 0, 0,
                             records=records, stderr_tail=stderr_tail)
    return RunResult(case=case.name, run_index=run_index, exit_code=completed.returncode, records=records,
                     stderr_tail=stderr_tail, **parsed)


def evaluate_run(run: RunResult, case: EvalCase, fixture: IncidentFixture) -> list[str]:
    """Every problem with one run. An empty list means the run passed all of its checks."""
    problems: list[str] = []
    if run.exit_code != 0 or run.is_error:
        problems.append(f"claude run failed (exit {run.exit_code})")
    if case.slow_tools:
        if not budget_spent_seen(run.records):
            problems.append("the server never handed out BUDGET SPENT")
        if not run.final_text.strip():
            problems.append("no partial findings in the final text")
    else:
        problems.extend(diagnosis_problems(extract_diagnosis(run.final_text), fixture))
    problems.extend(attempt_problems(run.records))
    return problems
