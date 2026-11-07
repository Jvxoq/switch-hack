# Set up Tripwire in your Switch Console (laptop, Slack)

This is the checklist for running Tripwire on your own laptop, with the Switch Console and Slack. Everything runs locally. Nothing needs a public address.

Status: **partly verified.** H00-sim ran prerequisite 1 (self-host), steps 5, 6 and 11, and the REST half of live checks Q1 and Q2, against a self-hosted Switch 0.31.0 on 2026-11-07 (see [docs/switch-api.md](switch-api.md), last section). Steps that need the Console, Slack or the Claude Code provider are still **UNCONFIRMED** and are the human's live test. The live checks at the end (steps 13 to 14) settle the rest.

## Prerequisites

Do these first. Each one is a hard blocker.

1. **A self-hosted Switch server is running on this laptop.** Its API listens on port 8000 and the Gateway on 3000, both bound to 127.0.0.1. This guide uses `http://127.0.0.1:8000`. H00-sim verified this setup on 2026-11-07 with Switch 0.31.0: take `deploy/local/standalone-docker-compose.yml` from github.com/sandbox-quantum/switch, set `SWITCH_VERSION=0.31.0` and `FEATURE_FLAGS_ENABLED` empty, and start it with `docker compose --profile gateway up -d`. Create the owner account and a registration key in the Gateway (API Keys page). Set `GATEWAY_PUBLIC_URL` to the API address. Switch Console can connect to this server as well (Add a server, Connect to an existing server).
2. **Slack is connected in the Console.** Connect > Slack, using the Switch Slack manifest (Socket Mode, no request URL). You need the `xapp-` app token, the `xoxb-` bot token and the workspace id `T...`. Create a channel `#agent-incidents` and run `/invite @Agent Switch` in it.
3. **Claude Code is installed and signed in on your Pro or Max subscription.** Open any agent's page in the Console, find **Provider sign-in**, and run the sign-in command the Console shows for Claude Code. Click **Recheck** until it reads signed in.
4. **Tools on this laptop:** `git`, `uv`, Docker with Compose, and `openssl`.

## Step by step

### 1. Clone the repo and run the tests

```bash
git clone https://github.com/Jvxoq/switch-hack
cd switch-hack
uv sync
uv run pytest -q
```

Expected: no failures. Five paid evals are skipped because they need an Anthropic key.

Remember the absolute path of the clone, from `pwd`. You will paste it into the Console in step 7.

### 2. Create `.env` and the Langfuse secrets

```bash
cp .env.example .env
scripts/bootstrap_langfuse.sh
```

The bootstrap fills every `CHANGEME` value that Langfuse needs. Leave `SWITCH_DRY_RUN=1` for now. It stays 1 until step 12.

### 3. Start the stack, without the detector

```bash
docker compose up -d
docker compose stop detector
```

The detector is stopped on purpose. In Compose it runs in a container, and a container cannot reach the laptop's `127.0.0.1:8000`, where Switch listens. You run the detector on the laptop in step 12.

Check: Langfuse at http://127.0.0.1:3000 opens, and http://127.0.0.1:8700/flags returns JSON.

### 4. Create a registration key in the Console

1. In the Console, open **Gateway > API Keys > Create Registration Key**.
2. Copy the key once. It is shown once.

### 5. Register the detector as a Switch agent

Run this in the repo, pasting your key in place of the placeholder. Put the key in the command, not in a file, and clear the line from your shell history afterwards:

```bash
SWITCH_BASE_URL=http://127.0.0.1:8000 SWITCH_REGISTRATION_KEY=<paste-key> \
  uv run python scripts/register_detector.py
```

Expected output: `registered tripwire-detector as agent id <uuid>`. Verified on 0.31.0: a second run without `--overwrite` stops with the 409 message, and `--overwrite` keeps the id and rotates the key. The script writes `SWITCH_AGENT_ID` and `SWITCH_TOKEN` into `.env` and does not print the agent key.

Check: `grep -E '^SWITCH_(AGENT_ID|TOKEN)=' .env` shows both lines with values.

If the name is already registered, the script says so and stops. Re-run with `--overwrite` to rotate the key. The old key stops working.

### 6. Create the room and link it to Slack

1. In the Console, create a room named `agent-incidents`.
2. Link the room to the Slack channel `#agent-incidents`.
3. In the room, run `!invite-agent @tripwire-detector`.

Now get the room id. Verified on 0.31.0 with an empty body and the detector's key. The answer is `{"result": [{"room_id": ..., "name": ...}]}`:

```bash
set -a; . ./.env; set +a
curl -sS -X POST "$SWITCH_BASE_URL/agents/$SWITCH_AGENT_ID/ops/list_rooms" \
  -H "Authorization: Bearer $SWITCH_TOKEN" -H 'Content-Type: application/json' -d '{}'
```

Find the entry whose `name` is `agent-incidents` and copy its `room_id` into `.env` as `SWITCH_ROOM_ID=`.

Also set these in `.env` now:

```text
SWITCH_PATH=agent
SWITCH_STATUS_MODE=reply
SWITCH_BASE_URL=http://127.0.0.1:8000
```

### 7. Add the Tripwire agent in the Console

Go to **Your Agents > +** and fill in the card:

| Field | Value |
| --- | --- |
| Name | `tripwire` |
| Description | Watchdog for order-lookup. Investigates detector alerts and asks owners for approval in the incident thread. |
| Run location | This computer |
| Directory | the absolute path of your clone from step 1 (the folder with `.mcp.json`) |
| Agent provider | Claude Code |

Paste the instructions. Either paste the contents of `tripwire_agent/instructions.md`, or import `tripwire_agent/room_template.yaml` through **Templates > Import** and check the fields afterwards.

Then set the agent's settings:

| Where | Setting | Value |
| --- | --- | --- |
| General | Auto mode | on (default) |
| General | Bypass permissions | off (default). Never turn this on. |
| General | Can manage agents | off |
| Advanced | Model | your choice, for example `sonnet` |
| Advanced | Effort | your choice |
| Advanced | Disallowed tools | `Edit, Write, NotebookEdit`. **UNCONFIRMED** that the Console takes these names. The point: code changes go only through the fix-PR tool. |
| Advanced | Permission mode | leave the default unless the Console offers a mode that asks in the room. Write down every option you see. |
| Advanced | Tools, Max turns | leave empty |

Tripwire's tools come from `.mcp.json` in the Directory. Claude Code loads the `tripwire` server from there. The Console has no MCP field (see docs/switch-api.md, Q&A 3).

First run only: Claude Code may ask you to trust the project's `tripwire` MCP server. Accept it in a terminal once. Start `claude` in the clone folder, accept, and quit.

Check: the agent page shows Provider sign-in as signed in.

### 8. Set who can talk to Tripwire

On the Tripwire agent's page, under General, open **Who can talk to your agent**.

- Choose **Me and my agents**. This is the default. It admits you and the agents you own, and the detector is one of them because you registered it in step 5. Verified on 0.31.0: the detector's `@tripwire` was addressed under this policy. Under "Only me" it was refused.
- If the detector's alert is later ignored (step 13), switch to **Custom rules** and add the detector agent by name.

Also link your Slack identity so that your Slack messages count as you: in the Console account settings, mark your Slack user as **This is me**. **UNCONFIRMED** that this is the exact label. Without the link your messages match no owner.

### 9. Invite Tripwire to the room

In the `agent-incidents` room:

```text
!invite-agent @tripwire
!set-alias @tripwire @tripwire
```

Expected: both commands are accepted and `@tripwire` appears in the room's member list.

### 10. Optional: import the room template

Templates > Import > `tripwire_agent/room_template.yaml`. This only creates the agent. Steps 7 to 9 already set the same fields, so you can skip this.

### 11. Check the room with a one-shot ping

This posts one message from the detector agent, addressed to Tripwire, and then tries one edit. The edit is undocumented, so a failure there is expected.

```bash
set -a; . ./.env; set +a
uv run python scripts/switch_spike.py
```

The output is JSON with `post_status`, `event_id` and `edit_status`. Expect `edit_status` 404: Switch 0.31 has no message-edit operation (verified). Watch the room.

- The message should appear in `agent-incidents` as `tripwire-detector`.
- Tripwire should reply in the thread. If it does not, that is the answer to live check Q1 below.

### 12. Run the detector on the laptop

Set `SWITCH_DRY_RUN=0` for this run only. The `.env` default of 1 stays as it is.

```bash
set -a; . ./.env; set +a
SWITCH_DRY_RUN=0 uv run python -m tripwire.detector --config tripwire.yaml --records incident-records.md
```

Leave it running. It polls Langfuse every 15 seconds and posts to the room when a rule fires.

### 13. Live checks: Switch behaviour (H00 and H01)

These checks settle the **UNCONFIRMED** items. Each one has an expected result and a line to report.

- **Q1. Does a REST-posted `@tripwire` wake Tripwire?** Step 11 answers it. Verified on 0.31.0 that the listener gets `payload.addressed: true`. Whether Tripwire's runtime replies is a Console check. Report yes or no.
- **Q2. Does the reply body's `thread_id` keep replies in the thread?** Verified on 0.31.0: no. The REST route ignores `thread_id`, and the status post lands top-level. Threaded replies need an agent connection and the `post_message` operation with `thread_id` (docs/switch-api.md, section (b)). Report what Tripwire's runtime does in the thread.
- **Q3. Does an owner's thread reply reach the agent?** Post `@tripwire hello` in the thread of the step 11 message as yourself. Expected: Tripwire answers in that thread.
- **Q4. Is the approver visible?** After a real approval (step 14), open the message in the Console transcript. Note the sender name and user id it shows. Then check `containment.log` (step 14, command below). It records `approver: switch-approval`, not your name. Report what the transcript showed.

### 14. Live checks: decline, allow once and the end-to-end run (H02, T14 and T20)

The demo agent produces a loop, the detector alerts, Tripwire asks you in the thread, and you answer by reply.

scripts/e2e.sh is not in the repo yet (H02 owns it). Run the steps by hand.

Set the demo bug, then run it:

```bash
# in .env
DEMO_BUG=loop
DEMO_RUNS=10
```

```bash
docker compose run --rm demo-agent
```

Wait for the alert in the room. It names `INC-<n>`. Tripwire posts a diagnosis and then asks: "Owner: reply `@tripwire approve` ... or `@tripwire decline`."

**T14a. Decline.** Reply `@tripwire decline` in that thread.

- Expected: Tripwire asks why, revises once and asks again. Nothing contained.
- Check: `docker compose exec containment cat /state/containment.log` shows no owner line for this incident.

**T14b. Approve once.** Reply `@tripwire approve` in the thread.

- Expected: exactly one owner line for this incident in `containment.log`. The loop stops.
- Check: `curl -s http://127.0.0.1:8700/incidents/INC-<n>` shows state `contained`, and the route's `disabled` flag is true at `http://127.0.0.1:8700/flags`.

**T20. The full run.**

1. Restart the demo with the fix in place: set `DEMO_BUG=none` in `.env`, then run `docker compose run --rm demo-agent`.
2. Reply `revert INC-<n>` in the thread (owner only).
3. Expected: state goes `verifying`, then `resolved`. The incident record appears in `incident-records.md` on the laptop.
4. Check: `curl -s http://127.0.0.1:8700/incidents/INC-<n>` shows `resolved`.

## Report back to the orchestrator

Reply with these lines, filled in. Each one decides a design question.

```text
H-PREP live report
Q1 REST @tripwire woke Tripwire: yes | no. Event or thread shape seen:
Q2 reply thread_id kept replies in thread: yes | no
Q3 owner thread reply reached the agent: yes | no
Q4 approver visible: sender shown as <name / user id>; containment.log approver = switch-approval
Edit op (step 11 edit_status): <code>
list_rooms args that worked: <body>, room id found: yes | no
Who-can-talk setting that worked: Me and my agents | Custom rules
Console labels that differed: Disallowed tools / Permission mode options: <list>
Claude Code tool names seen by the agent (mcp__tripwire__...): yes | no
T14a decline: pass | fail. T14b approve once: exactly one owner line: yes | no
T20 end to end: pass | fail, stopped at <step>
Anything else:
```

## If something fails

- **Tripwire says it has no tools.** Check that the Directory is the clone and that `.mcp.json` is there. Run `uv run python -m tripwire_agent.server` in the clone: it should wait silently on stdin. Check that `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` were in the environment the Console started from. The `.mcp.json` file holds no secrets. It passes through what Claude Code's environment already has. **UNCONFIRMED** that the Console passes its environment to Claude Code, so start the Console from a terminal that has run `set -a; . ./.env; set +a`.
- **The detector posts nothing.** Check `SWITCH_DRY_RUN=0` for that run, and that `SWITCH_AGENT_ID`, `SWITCH_TOKEN` and `SWITCH_ROOM_ID` are set.
- **Containment refuses an action.** The refusal text is what the tool returned. Read it in the thread. Do not work around it.
