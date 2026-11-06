---
description: Run the full prod-parity check, then suggest per-change git add + commit commands
argument-hint: (optional focus, e.g. "frontend only" — or "--skip-checks" to bypass prod-check)
---

Review my current uncommitted changes and propose how to commit them. $ARGUMENTS

Context to gather first (captured now, before any check runs, so build artifacts don't pollute it):
- Status: !`git status --short`
- Stat:   !`git diff --stat`
- Recent messages (match this style): !`git log --oneline -8`

## Step 1 — Gate on prod-check (do this BEFORE anything else)

Unless $ARGUMENTS contains `--skip-checks`, read `~/.claude/commands/prod-check.md` and
carry out that entire procedure against this repo now. Follow it fully — do not
substitute a quick `pytest` run for it, and do not skip the teardown step.

Then branch on its verdict:

- **PASS** — continue to Step 2.
- **FAIL** — STOP. Do not print any commit commands. Report the prod-check summary
  exactly as that command specifies, name each failing command and its exact error,
  and end with: "Not committing — fix the above first, or re-run `/commits --skip-checks`
  if you're committing work-in-progress on purpose."

If $ARGUMENTS contains `--skip-checks`, skip straight to Step 2 and open your response
with a one-line warning that the prod-parity check was bypassed.

## Step 2 — Propose the commits

1. Group the changed files into small logical commits — one concern per commit.
   Do not lump unrelated changes together. If a file has mixed concerns, say so.
   Ignore any build artifacts, coverage files, or containers left behind by Step 1;
   group only the changes present in the status captured at the top of this command.
2. For each group write ONE short, plain commit message: single line, present tense,
   no jargon, no body. Match the simple style of the recent messages above.
3. Print each commit as a copy-paste block:
   ```
   git add <files>
   git commit -m "<message>"
   ```

Rules:
- Do NOT run git add / commit / push yourself — only print the commands for me to run.
- Do NOT add a Co-Authored-By line or mention any tool or model in the message.
- Keep every message short and simple enough for me to explain at a glance.
