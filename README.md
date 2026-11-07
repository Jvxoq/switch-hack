# switch-hack

Tripwire: a Switch room agent that watches Langfuse traces for runaway AI-agent behavior and contains it after an owner approves in Slack. Built for the WeMakeDevs "Flip the Switch" hackathon.

Read the [product proposal](tripwire-product-proposal.md) for the design and a flow chart per feature.

## What Tripwire does

A demo order-lookup agent sends its traces to a self-hosted Langfuse. Tripwire reads those traces and looks for three failure shapes:

- **loop**: the same tool call repeats in one trace;
- **silent_error**: a route keeps returning errors or "not found" without raising;
- **cost_spike**: one trace or route spends far above its normal median.

When a rule fires, Tripwire opens an incident and posts an alert in the Switch room. An owner approves one containment action in the room: `disable_route`, `cap_max_steps` or `fallback_model`. A budget-limited auto-pause can disable a route without an owner. Tripwire then verifies that the loop has stopped, resolves the incident, and writes an incident record. A fix PR can be opened for the proposed patch. The agent never merges it.

## Architecture

| Part | Path | Role |
| --- | --- | --- |
| Containment service | `tripwire/containment/` | FastAPI on `:8700`. The only writer of incident state (`incidents.json`) and flags (`flags.json`). Enforces the action menu, the one-action-per-ask-round rule and the state transitions. |
| Detector | `tripwire/detector/`, `tripwire/rules/` | Polls Langfuse every `poll_seconds`, keeps a 60-minute trace window, runs the three rules, opens incidents, auto-pauses, verifies and records. |
| Langfuse reader | `tripwire/langfuse_client.py` | Synchronous HTTP client with timeouts and bounded 5xx retries. |
| Switch client | `tripwire/switch_client.py` | Posts alerts and replies to the Switch room (agent path), or to Slack (fallback path). Compose and `.env.example` set dry run (`SWITCH_DRY_RUN=1`), which logs instead of posting. |
| Incident records | `tripwire/records.py` | Renders each incident record and appends it to a JSONL log. |
| Tripwire agent | `tripwire_agent/` | Room template, instructions, and an MCP tool server. The server runs the budget guard (20 calls, 3 minutes per ask round) and the fix-PR tool. |
| Demo agent | `demo_agent/` | The order-lookup victim agent, with switchable `loop`, `silent_error` and `cost_spike` bugs. Runs offline or online. |
| Paid evals | `tests/eval/`, `scripts/run_evals.sh` | Real-model evals of the Tripwire agent. Skipped without `ANTHROPIC_API_KEY`. |

Incident state lives only in the containment service. The detector and the tool server read and change it through HTTP.

## Prerequisites

- **Switch Console** desktop app running on this machine (its local server), with **Slack** connected.
- **Claude Code** installed and signed in (Pro or Max). Tripwire runs on it inside Switch.
- **Docker** with Compose, **uv**, Python 3.12, git and openssl.
- **Keys:** a Together AI key (the demo agent's model), a GitHub token with repo access (fix PRs), and a Switch agent registration key.
- **In the Console, once:**
  1. Create a room and link it to a Slack channel.
  2. Add an agent named `tripwire`. Provider: Claude Code. Directory: this repo. Instructions: paste `tripwire_agent/instructions.md`.
  3. Under "Who can talk to your agent", pick Custom rules: you, plus the agent `tripwire-detector`.
- **In `tripwire.yaml`:** put your Switch user name in `owners`, and your repo in `fix_pr`.

## Quickstart

```bash
git clone https://github.com/Jvxoq/switch-hack && cd switch-hack && uv sync
cp .env.example .env && scripts/bootstrap_langfuse.sh   # then set TOGETHER_API_KEY, GITHUB_TOKEN, SWITCH_BASE_URL, SWITCH_ROOM_ID, SWITCH_DRY_RUN=0
docker compose up -d && docker compose stop detector    # Langfuse + containment; the detector runs on the host to reach Switch
SWITCH_REGISTRATION_KEY=<key> uv run --env-file .env python scripts/register_detector.py   # then in the room: !invite-agent @tripwire-detector and !invite-agent @tripwire
uv run --env-file .env python -m tripwire.detector --config tripwire.yaml
```

Then start an incident from a second terminal:

```bash
docker compose run --rm -e DEMO_BUG=loop demo-agent
```

An alert lands in the room within about 15 seconds, and Tripwire takes it from there. Langfuse is at http://127.0.0.1:3000.

## Tests

```bash
uv run pytest -q                 # offline suite; the paid evals skip without a key
uv run pytest -q -m 'not eval'   # same, explicitly without the paid set
uv run pytest -q -m eval -rs     # paid evals only (needs ANTHROPIC_API_KEY and the claude CLI)
```

The offline suite makes no network calls. Unit tests use the fakes in `tests/fakes/`, and HTTP is mocked with `httpx.MockTransport`.

### Paid evals

These run real model calls and cost money. They are not run in CI.

```bash
export ANTHROPIC_API_KEY=...
scripts/run_evals.sh --runs 5    # prints case, runs, passes and cost
```

Pass counts are pending.

## Configuration

`tripwire.yaml` holds the rules, routes, auto-pause and owners. Secrets are env-var names only. Values come from the environment.

| Setting | Default | Meaning |
| --- | --- | --- |
| `poll_seconds` | 15 | Detector poll interval |
| `window_minutes` | 60 | Rolling trace window every rule judges |
| `containment_url` | `http://127.0.0.1:8700` | Containment service |
| `langfuse_host` | `http://localhost:3000` | Langfuse; `LANGFUSE_HOST` overrides it |
| `records_path` | `incident-records.jsonl` | Incident record log; `--records` overrides it |
| `rules.loop` | `max_repeats 5`, `max_observations 25` | Repeat rule; `max_observations` is the only catch for reworded loops |
| `rules.silent_error` | `count 3`, `window_minutes 5`, `patterns ["error","not found"]` | Silent-error rule |
| `rules.cost_spike` | `median_multiplier 5`, `per_trace_usd 1.0` | Cost-spike rule |
| `allow_list_tools` | `[list_orders_page]` | Tools the loop rule ignores |
| `routes.<name>` | `loss_budget_usd`, `hourly_ceiling_usd` | Per-route budgets (`order-lookup`: $50 and $50) |
| `auto_pause` | `minutes 10`, `budget_fraction 0.5` | When the detector may pause a route alone |
| `verify_minutes` | 5 | Quiet time before an incident resolves |
| `tripwire_guard` | `max_tool_calls 20`, `max_minutes 3` | Tool-server budget per ask round |
| `fix_pr` | empty | Local clone, GitHub owner and repo for fix PRs; empty turns the tool off |
| `owners` | `[jason]` | Who may approve or revert |

Environment variables:

| Variable | Used by | Notes |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | detector, tool server, demo agent | Project keys. `bootstrap_langfuse.sh` writes them. |
| `LANGFUSE_HOST` | detector, tool server, demo agent | Overrides `langfuse_host`. Compose sets `http://langfuse-web:3000`. |
| `TRIPWIRE_CONFIG` | containment, tool server | Path to `tripwire.yaml` (default `tripwire.yaml`) |
| `TRIPWIRE_STATE_DIR` | containment | State directory (default `containment-state`; Compose uses `/state`) |
| `TRIPWIRE_CONTAINMENT_URL` | demo agent | Containment URL for the demo agent (Compose sets it) |
| `SWITCH_DRY_RUN` | detector | `1` logs instead of posting. Keep `1` until Switch is set up. |
| `SWITCH_PATH` | detector | `agent` (default) or `slack` |
| `SWITCH_BASE_URL`, `SWITCH_AGENT_ID`, `SWITCH_ROOM_ID`, `SWITCH_TOKEN` | detector, agent path | `SWITCH_TOKEN` is the agent key (`SWITCH_AGENT_KEY` is also read) |
| `SWITCH_STATUS_MODE` | detector | `reply` (default) or `edit` |
| `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` | detector, slack path | Slack fallback |
| `GITHUB_TOKEN` | tool server (fix PR) | Pull requests and contents write on the repo in `fix_pr` |
| `TOGETHER_API_KEY`, `TOGETHER_MODEL` | demo agent (online) | Real model calls through the Together client |
| `DEMO_PRICE_INPUT_PER_MTOK`, `DEMO_PRICE_OUTPUT_PER_MTOK` | demo agent | Prices of `TOGETHER_MODEL`, used for trace costs |
| `ANTHROPIC_API_KEY` | evals, exported in the shell | The evals run the Tripwire agent through the `claude` CLI |
| `DEMO_BUG`, `DEMO_RUNS` | Compose demo agent | Bug to switch on (`none`, `loop`, `silent_error`, `cost_spike`) and run count |

Keep secrets in `.env` (git-ignored) or the environment. Never commit them.

## Status

- Offline suite: 433 passing, 5 paid evals skipped (no key).
- Live, in a Switch room linked to Slack: detect, investigate, approve, contain and fix PR all ran end to end on a real loop incident.
- Paid evals (T13, T16, T19) are not run yet.

## Future work

From the proposal's scope table:

- ML-based anomaly detection
- Per-team rooms and PagerDuty escalation
- Auto-generated regression tests
- Real flag services (LaunchDarkly, Unleash)
- Auto-merge of low-risk fixes
- Weekly incident digest

The hackathon build's loop rule catches only repeats of the same call. Reworded loops are caught only by the `max_observations` cap.
