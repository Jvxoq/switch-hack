# Verification report

Checked on 2026-11-07 against `claude/overnight-tasks-subagents-rtmqzx` (X01). The run had no paid model calls and no live Switch room. Items that need either are marked **PENDING** and have steps below.

## Result

- `uv run pytest -q`: **348 passed, 5 skipped**. The 5 skips are the paid evals (`ANTHROPIC_API_KEY` not set). They count as PENDING, not passing.
- Every test file also passes when run alone.
- T1 to T20: 18 of 20 IDs have offline tests that pass. T13, T16 and T19 also have paid tests that are PENDING. T14 and T20 have no test in the repo yet. They need the live Switch room (H00, H01, H02 are skipped), so they are PENDING.
- Four bugs found in this pass are fixed, each with a regression test that fails before the fix. See "Fixed in this pass".
- Open issues are listed under "Known issues". The most important is one containment bug (O1).

## T1 to T20

Counts are collected test items for each ID. "Pass" means the item passed in the run above.

| ID | What it checks | Where | Pass | Status |
| --- | --- | --- | --- | --- |
| T1 | Loop rule fires at 5 identical calls, not 4 | `tests/unit/test_rule_loop.py::test_T1_*` | 3 | pass |
| T2 | Allow-listed `list_orders_page` x10 does not fire | `tests/unit/test_rule_loop.py::test_T2_*` | 2 | pass |
| T3 | Silent-error rule: 3 in 5 min fires, spread or ERROR level does not | `tests/unit/test_rule_silent_error.py::test_T3_*` | 9 | pass |
| T4 | Cost spike: 5x median fires, 4.9x does not, $1 with no baseline fires | `tests/unit/test_rule_cost_spike.py::test_T4_*` | 10 | pass |
| T5 | 50 looping traces on one route make one incident, count 50 | `tests/unit/test_incidents.py::test_T5_*` | 3 | pass |
| T6 | A different rule on the same route opens a separate incident | `tests/unit/test_incidents.py::test_T6_*` | 2 | pass |
| T7 | Alert text has every field and addresses `@tripwire`; Switch client sends every field; dry run never calls the network | `tests/unit/test_incidents.py::test_T7_*`, `tests/integration/test_switch_client.py::test_T7_*` | 20 | pass, against a fake HTTP Switch. W01 is provisional (see below) |
| T8 | Auto-pause at half budget or 10 min, not earlier, once per incident, never while an owner action is active | `tests/unit/test_autopause.py::test_T8_*` | 8 | pass |
| T9 | Hourly ceiling pauses with zero rule hits and shows an alert | `tests/unit/test_autopause.py::test_T9_*` | 6 | pass |
| T10 | Containment refuses unknown INC, off-menu action, second owner action in a round, bad auto-pause, caller `opened_at` | `tests/unit/test_containment.py::test_T10_*` | 13 | pass |
| T11 | Real containment service over HTTP stops the demo agent with `route disabled` | `tests/integration/test_containment_demo_agent.py::test_T11_*` | 3 | pass. Leaks a localhost socket, see O8 |
| T12 | Revert restores exact previous flags; replace restores before applying | `tests/unit/test_containment.py::test_T12_*` | 4 | pass. Per-route only, see O1 |
| T13 | Diagnosis passes schema: rule, observation IDs that exist, cost, one menu action, confidence | offline: `tests/eval/test_eval_harness.py::test_T13_*`. Paid: `tests/eval/test_agent_evals.py::test_T13_diagnosis_passes_schema[loop, silent_error, cost_spike]` | 11 offline | offline pass. **Paid 3 PENDING** |
| T14 | Human Decline gives no owner action; Allow once gives exactly one | none | 0 | **PENDING** (live Switch room; H02 skipped; no test written) |
| T15 | Fix-PR tool opens a PR, requests no approval, stores `pr_url`; never merges | `tests/integration/test_fix_pr.py::test_T15_*` | 21 | pass, local bare git and stubbed GitHub |
| T16 | Tool server enforces the call and time cap and hands off with partial findings | offline: `tests/unit/test_agent_tools.py::test_T16_*`, `tests/eval/test_eval_harness.py::test_T16_*`. Paid: `tests/eval/test_agent_evals.py::test_T16_slow_tools_hit_server_cap` | 8 offline | offline pass. **Paid 1 PENDING** |
| T17 | Verify, resolve after quiet period, reopen on repeat, record once on hand-off | `tests/unit/test_verify.py::test_T17_*` | 9 | pass |
| T18 | Record has every field; missing optional fields render as `—`; torn JSONL line is skipped | `tests/unit/test_records.py::test_T18_*` | 7 | pass |
| T19 | Injected "ignore instructions" text gets no off-menu action and at most one request | offline: `tests/eval/test_eval_harness.py::test_T19_*`. Paid: `tests/eval/test_agent_evals.py::test_T19_injected_trace_text_gets_no_off_menu_action` | 5 offline | offline pass. **Paid 1 PENDING** |
| T20 | Full scenario: compose up, loop, human approve, revert, resolve, record printed | none | 0 | **PENDING** (live Switch room and human clicks; `scripts/e2e.sh` not written) |

Totals: 144 offline T-ID tests pass. 5 paid items are PENDING (T13 x3, T16 x1, T19 x1). T14 and T20 have no test items.

## Live verification

Recorded by K01. Not re-run in X01, which had no Docker and no network.

- Docker Compose stack with Langfuse pinned to v3 (`LANGFUSE_IMAGE_TAG=3`) came up.
- 6 healthchecked services were healthy.
- The detector polled `/api/public/traces` 35 times, and all 35 returned HTTP 200.
- A live loop incident was **not** produced. The demo agent needs a real `ANTHROPIC_API_KEY`.

Not verified live: the Switch room (H00 skipped), Slack, the Claude Code tool-server registration, and the owner approval flow.

## PENDING: how to finish

### 1. Paid evals (T13 x3, T16 x1, T19 x1)

Cost: real model spend. Needs the `claude` CLI on `PATH` and a key.

1. `export ANTHROPIC_API_KEY=...` (never commit it).
2. Check the paid set alone: `uv run pytest -q -m eval -rs`. Each item should pass, not skip.
3. Run the repeated eval: `scripts/run_evals.sh --runs 5`. It writes `docs/eval-results.md` with pass counts and cost.
4. Put the pass counts for T13, T16 and T19 into the table above. Mark each one with its runs.

Note: the X01 spec counts a skipped eval as failed. This run's decision is PENDING, so these items are not counted as failures here.

### 2. Live loop incident (containment and detector end to end)

Cost: real model spend. Needs Docker and a real key.

1. `cp .env.example .env`, then `scripts/bootstrap_langfuse.sh`.
2. In `.env`, set `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`. Set `DEMO_BUG=loop`.
3. `docker compose up -d` and wait until `docker compose ps` shows healthy.
4. `docker compose run --rm demo-agent`. This runs the loop bug for `DEMO_RUNS` runs.
5. `docker compose logs -f detector`: expect a `loop` incident line.
6. `curl -s http://127.0.0.1:8700/incidents`: expect one open `loop` incident for `order-lookup`.
7. Owner approval by hand (no Switch): `curl -s -X PATCH http://127.0.0.1:8700/incidents/INC-1 -H 'content-type: application/json' -d '{"state":"investigating"}'`, then the same with `"awaiting_approval"`. Then `curl -s -X POST http://127.0.0.1:8700/actions -H 'content-type: application/json' -d '{"incident_id":"INC-1","action":"disable_route","source":"owner","approver":"jason","spend_usd":0}'`.
8. `curl -s http://127.0.0.1:8700/flags`: expect `order-lookup` with `"disabled": true`.
9. Run the demo agent again: it should stop with `route disabled`.

### 3. Switch room and live tests (H00, H01, H02: T14, T20)

Needs a human with a Switch account. The steps below use the open items in `docs/switch-api.md`.

1. Create the Switch room and register the detector agent. Set `SWITCH_BASE_URL`, `SWITCH_AGENT_ID`, `SWITCH_ROOM_ID`, `SWITCH_TOKEN`, then `SWITCH_DRY_RUN=0` in `.env`.
2. Confirm each UNCONFIRMED item in `docs/switch-api.md` against the live API: the thread id shape in the POST response, the `thread_id` field on replies, the update-message endpoint for edit mode, whether an approver's name can be read from the approval record, and how `@tripwire` addressing is detected.
3. Once confirmed, update `W01` and `A01` (see "Provisional points"), then write `tests/switch/*` and `scripts/e2e.sh` per H02.
4. Human clicks: Decline (T14, expect no owner action in `containment.log`), then Allow once (expect exactly one). Then run `scripts/e2e.sh` for T20.

## Provisional points

These are built against `docs/switch-api.md` and have not been checked against a live Switch room.

- `tripwire/switch_client.py` (W01): the thread id is read from the POST response (`thread_id`, `message.thread_id`, then `id`). Replies send `thread_id` in the body. Edit mode calls `POST /agents/{id}/ops/update_message`, which is an UNCONFIRMED endpoint. Addressing uses the `@tripwire` text, since the `addressed` flag is not documented. The Slack path treats a bot post as a human sender (UNCONFIRMED). The module docstring says all of this.
- `tripwire_agent/server.py` (A01): the tool server cannot read the approver from Switch. It sends the fixed value `switch-approval`, and the containment service skips its owners check for that value. The owner gate for `request_containment` and `revert_containment` is Switch's approval flow plus `instructions.md`, not code in this module. Switch's per-tool "always ask" setting is not documented. The module docstring says so.
- `docs/switch-api.md`: marked UNCONFIRMED where the docs were silent.

## Fixed in this pass

Each fix has a regression test. Each test was run before the fix and failed.

1. **Verifier stopped at the first failing incident.** `Verifier.tick` let one incident's exception escape, so an unreachable Switch thread stopped every later incident in the poll. Fix: per-incident isolation with an ERROR log. Test: `tests/unit/test_verify.py::test_tick_keeps_advancing_after_one_incident_fails`.
2. **Failed handed-off record was never retried.** `Verifier.on_handed_off` marked the incident recorded before the write, so a failed write was dropped until the next restart. Fix: mark it only after the write succeeds. Test: `tests/unit/test_verify.py::test_handed_off_record_retried_after_write_failure`.
3. **Auto-pause stopped at the first apply error.** `run_autopause` let a non-refusal error (for example containment unreachable) skip every later incident in the poll. Fix: log and continue. Test: `tests/unit/test_autopause.py::test_auto_pause_keeps_going_after_one_apply_fails`.
4. **Tool server ignored the configured Langfuse host.** `tripwire_agent/server.py` read only `LANGFUSE_HOST` and defaulted to Langfuse Cloud. The detector and `tripwire.yaml` use `langfuse_host`. Fix: `langfuse_host(cfg, environ)` with the same rule as the detector. Test: `tests/unit/test_agent_tools.py::test_langfuse_host_comes_from_config_unless_env_set`.
5. **Switch requests had no test for their timeout.** Removing the timeout from the Switch HTTP client left the suite green. Fix: no code change. Added a test that the request leaving the client carries the 10 s timeout. Test: `tests/integration/test_switch_client.py::test_every_switch_request_carries_timeout`.

## Known issues

Open, not fixed in X01. Ordered by impact.

- **O1 (high): containment restores flags per route, not per incident.** Reverting one incident restores the route snapshot taken when that incident acted, which drops another incident's active action on the same route. Reproduced with the real `ContainmentStore`: `loop` disable, then `cost_spike` cap, then revert `loop` gives flags `{disabled: false, max_steps: null}` while `cost_spike` still reads `cap_max_steps`. The route is then uncapped. Fix direction: derive route flags from defaults plus every active incident action, and drop the per-incident snapshots. This changes the `flags.json` format and the S01 contract, so it needs a contract decision.
- **O2 (medium): containment mutates memory before it persists.** `apply`, `revert` and `update` change in-memory state, then write `incidents.json`. If the write fails, memory stays ahead until restart. Fix: build the new state, persist, then swap.
- **O3 (medium): Langfuse read has a hard page cap.** `_collect` raises after 50 pages (5,000 observations). A busy 60-minute window would fail every poll, with only "narrow the window" as the message. There is no config knob.
- **O4 (medium): the detector's per-step guard is coarse.** `observe` and `ingest` in `Detector.poll` still stop at the first failing incident (only `verify` and auto-pause were isolated here).
- **O5 (low): tool server leaks a Langfuse error to the model.** `langfuse_read` does not catch `LangfuseError`, so the model gets an MCP error, not a text refusal. The text carries up to 200 chars of the Langfuse response.
- **O6 (low): Switch error text carries response body.** `SwitchClient._post` and `SlackFallbackClient._call` put up to 200 chars of the response into the error. Probably harmless. Revisit if Switch echoes request content.
- **O7 (low): invalid `SWITCH_STATUS_MODE` raises `ValueError`.** It is not a `SwitchError`, so startup prints a traceback instead of a clean exit code 2.
- **O8 (test hygiene): the T11 integration test leaks a socket.** Under `pytest -W error` it fails with a ResourceWarning. This is why `filterwarnings = error` is not enabled (see gates).
- **O9 (type check): mypy reports 13 errors** (not run in CI; mypy is not a dev dependency). Run with `uv run --with mypy mypy --ignore-missing-imports tripwire tripwire_agent demo_agent`. Main items: `rule: str` passed where `RuleName` is a `Literal` (`tripwire/detector/autopause.py:101`, `tripwire/containment/app.py:131`); `default_factory` types in `tripwire/contracts/config.py:38-93`; `tripwire/detector/window.py:49`; `tripwire/switch_client.py:127`; `demo_agent/cli.py:72`.
- **O10 (lint): default ruff reports 32 findings**, all unused imports, import order and `datetime.UTC` style. The extended rules (`ASYNC`, `BLE`, `S110`, `S112`, `RUF006`, `B006`, `B008`) pass. Not fixed to keep the diff focused.

## Harness gates

Checked against the test standards for this repo.

| Gate | State |
| --- | --- |
| Per-test time limit | on: `pytest-timeout`, `timeout = 10` in `pyproject.toml` |
| Warnings are errors | **missing**: no `filterwarnings = ["error"]`. Blocked by O8. Proposed config once O8 is fixed: `filterwarnings = ["error"]` |
| No real network | on: autouse `no_real_network` in `tests/conftest.py` blocks non-local connects. It records no attempts and checks nothing at teardown, so a broad `except` can hide a blocked call |
| Lint rules that find killers | **not configured** in `pyproject.toml`. Pass when selected explicitly. Proposed: `[tool.ruff.lint] extend-select = ["ASYNC","BLE","S110","S112","RUF006","B006","B008"]` |
| Type checker | **not configured**. mypy reports O9. Proposed: add mypy to the dev group and fix O9 |

## Production guard spot check

Breaks run in a scratch copy, one at a time, to see whether a named test goes red.

| Break | Caught by |
| --- | --- |
| Tool-call cap `20` replaced with `10**9` (P2) | 7 T16 tests |
| Langfuse request timeout removed (P1) | `test_every_request_carries_ten_second_read_timeout` |
| Switch request timeout removed (P1) | escaped before fix 5; now `test_every_switch_request_carries_timeout` |
| Git call timeout removed (P1) | `test_T15_every_git_call_has_timeout` |
| Verifier `log.exception` removed (P6) | `test_tick_keeps_advancing_after_one_incident_fails` |
| Backoff jitter removed (P4) | `test_backoff_adds_jitter_to_each_wait` |

Not run in this pass: the full break table for every P entry, and the bounded-growth, cancellation and resource-lifetime breaks (P9 to P12). Those are open for a later audit.

## How this was checked

- `uv run pytest -q -rA` for the full run, and per file.
- Collected test items per ID with `uv run pytest --co`, so parametrized cases are counted.
- `uv run ruff check` with the default config and with the extended rules.
- mypy through `uv run --with mypy`.
- A `ContainmentStore` script for O1. The script was in a scratch directory and is not committed.
