#!/usr/bin/env bash
# Run the Tripwire agent evals N times per case and write docs/eval-results.md.
# Usage: scripts/run_evals.sh --runs 5 [--cases loop silent_error] [--model claude-opus-5-5]
# Spends real money. Needs ANTHROPIC_API_KEY and the claude CLI; exits 2 without them.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m tests.eval.run "$@"
