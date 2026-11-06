"""Eval runner: each case N times through `claude -p`, then write docs/eval-results.md (A03).

Usage: `uv run python -m tests.eval.run --runs 5`, or `scripts/run_evals.sh --runs 5`.
Spends real money. It exits 2 without ANTHROPIC_API_KEY or the claude CLI, and never calls the API then.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tests.eval.cases import EVAL_CASES, REPO_ROOT, load_fixture
from tests.eval.harness import (
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    RunResult,
    evaluate_run,
    paid_skip_reason,
    run_case,
)

DEFAULT_OUT = REPO_ROOT / "docs" / "eval-results.md"
EXIT_SKIPPED = 2


@dataclass(frozen=True)
class CaseSummary:
    case: str
    runs: int
    passes: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    failures: tuple[str, ...]


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Tripwire agent evals and write docs/eval-results.md.")
    parser.add_argument("--runs", type=_positive_int, default=1, help="runs per case (default 1)")
    parser.add_argument("--cases", nargs="+", choices=[case.name for case in EVAL_CASES], default=None,
                        help="run only these cases (default all)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"agent model (default {DEFAULT_MODEL})")
    parser.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD,
                        help="claude --max-budget-usd for each run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="markdown report path")
    return parser.parse_args(argv)


def summarize_case(name: str, results: Sequence[tuple[RunResult, list[str]]]) -> CaseSummary:
    failures = tuple(
        f"run {run.run_index}: {problem}" for run, problems in results for problem in problems
    )
    return CaseSummary(
        case=name,
        runs=len(results),
        passes=sum(1 for _, problems in results if not problems),
        input_tokens=sum(run.input_tokens for run, _ in results),
        output_tokens=sum(run.output_tokens for run, _ in results),
        cache_read_tokens=sum(run.cache_read_tokens for run, _ in results),
        cache_write_tokens=sum(run.cache_write_tokens for run, _ in results),
        cost_usd=round(sum(run.cost_usd for run, _ in results), 6),
        failures=failures,
    )


def render_markdown(rows: Sequence[CaseSummary], generated_at: str, model: str) -> str:
    lines = [
        "# Agent eval results",
        "",
        f"Generated {generated_at} by `scripts/run_evals.sh` with model `{model}`.",
        "Cost is the total the Claude CLI reported for the run, from real token counts.",
        "",
        "| Case | Runs | Passes | Input tokens | Output tokens | Cache read | Cache write | Cost (USD) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row.case} | {row.runs} | {row.passes} | {row.input_tokens} | {row.output_tokens} | "
            f"{row.cache_read_tokens} | {row.cache_write_tokens} | {row.cost_usd:.4f} |"
        )
    failing = [row for row in rows if row.failures]
    if failing:
        lines += ["", "## Failures", ""]
        for row in failing:
            lines.append(f"### {row.case}")
            lines += [f"- {failure}" for failure in row.failures]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_all(
    names: Sequence[str] | None,
    *,
    runs: int,
    model: str,
    budget_usd: float,
) -> list[CaseSummary]:
    rows: list[CaseSummary] = []
    for case in EVAL_CASES:
        if names is not None and case.name not in names:
            continue
        fixture = load_fixture(case.fixture)
        results: list[tuple[RunResult, list[str]]] = []
        for index in range(1, runs + 1):
            run = run_case(case, run_index=index, model=model, budget_usd=budget_usd)
            results.append((run, evaluate_run(run, case, fixture)))
        rows.append(summarize_case(case.name, results))
    return rows


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = parse_args(argv)
    reason = paid_skip_reason(os.environ if environ is None else environ, shutil.which("claude"))
    if reason is not None:
        print(f"{reason}; nothing was run", file=sys.stderr)
        return EXIT_SKIPPED
    rows = run_all(args.cases, runs=args.runs, model=args.model, budget_usd=args.budget_usd)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(rows, generated, args.model), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if all(row.passes == row.runs for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
