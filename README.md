# Tripwire

Tripwire is an incident agent for AI agents. It reads Langfuse traces and detects three failure modes: tool-call loops, silent errors, and cost spikes. For each incident it posts an alert in a Switch room linked to Slack. After an owner approves, it applies one containment action (`disable_route`, `cap_max_steps` or `fallback_model`). It then verifies that the incident has stopped and writes an incident record. It can also open a fix pull request, which it never merges.

Built for the WeMakeDevs "Flip the Switch" hackathon. The design is in the [product proposal](tripwire-product-proposal.md).

## Prerequisites

- Docker with Compose, [uv](https://docs.astral.sh/uv/), Python 3.12, git and openssl
- Switch Console running locally, with Slack connected
- Claude Code, installed and signed in
- A Together AI API key, a GitHub token with repo access, and a Switch registration key

## Setup

```bash
git clone https://github.com/Jvxoq/switch-hack && cd switch-hack
uv sync
cp .env.example .env
scripts/bootstrap_langfuse.sh
```

Then make these edits:

- In `.env`, set `TOGETHER_API_KEY`, `GITHUB_TOKEN`, `SWITCH_BASE_URL`, `SWITCH_ROOM_ID` and `SWITCH_DRY_RUN=0`.
- In `tripwire.yaml`, set your Switch user name under `owners` and your repository under `fix_pr`.
- In Switch Console, create a room linked to a Slack channel. Add an agent named `tripwire` that uses Claude Code, with this repo as its directory and `tripwire_agent/instructions.md` as its instructions. Allow it to talk to you and to `tripwire-detector`.

## Run

Start Langfuse and the containment service. The detector runs on the host instead, so it can reach Switch.

```bash
docker compose up -d
docker compose stop detector
```

Register the detector, then run `!invite-agent @tripwire-detector` and `!invite-agent @tripwire` in the room:

```bash
SWITCH_REGISTRATION_KEY=<key> uv run --env-file .env python scripts/register_detector.py
```

Start the detector:

```bash
uv run --env-file .env python -m tripwire.detector --config tripwire.yaml
```

In a second terminal, start a demo incident. `DEMO_BUG` can be `loop`, `silent_error` or `cost_spike`.

```bash
docker compose run --rm -e DEMO_BUG=loop demo-agent
```

An alert appears in the room within about 15 seconds. The Langfuse UI is at http://127.0.0.1:3000.

## Test

```bash
uv run pytest -q -m "not eval and not switch"
```

The paid model evals need `ANTHROPIC_API_KEY` and run with `scripts/run_evals.sh --runs 5`. Configuration options are in `tripwire.yaml`, and environment variables are in `.env.example`.
