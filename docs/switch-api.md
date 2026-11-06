# Switch API facts (C02)

Sources (fetched 2026-11-06): docs.switchagents.ai home, `/llms.txt`, `/switch-rooms/internals/agent-protocol.md`,
`/switch-rooms/internals/agent-connection.md`, `/switch-rooms/internals/agent-events.md`,
`/switch-rooms/internals/life-of-a-message.md`, `/switch-rooms/internals/identity-and-access.md`,
`/switch-rooms/resources/room-commands.md`, `/switch-rooms/resources/working-safely-with-agents.md`,
`/switch-rooms/getting-started/agent-settings.md`, `/switch-rooms/deploy/messaging-apps/slack.md`,
`/switch-rooms/deploy/messaging-apps/mattermost.md`, `/switch-rooms/use-cases/incident-response.md`,
github.com/sandbox-quantum/switch (README, `examples/agent-templates/triage-pair.template.yaml`, `docs/TEMPLATES.md`),
docs.slack.dev `chat.postMessage`.

## Q&A

**1. How does an external process register as an agent and post in a room thread?**
- Register once: `POST /agents` with a registration key as bearer token (created on the Gateway's API Keys page). Body needs
  `name`, `description`, `connector_type`, `integration_profile` (with `connection_model`: `always_on`, `session_addressable`,
  `auto_session`, or `session_passive`). Response `{id, api_key}`; the API key is shown once. Re-registering a name gives 409;
  `overwrite: true` rotates the key. (agent-protocol.md)
- Auth afterwards: `Authorization: Bearer <agent API key>` on every call and on the WebSocket. Registration key cannot open a
  connection; agent key cannot register. (agent-protocol.md)
- Post a message: `POST /agents/{agent_id}/message` with `{room_id, content}` (no connection needed), or the `post_message` op via
  `POST /agents/{agent_id}/ops/post_message`. Room-scoped ops need header `X-Switch-Connection-Id`. (agent-protocol.md)
- Receive events: WebSocket `GET /agents/{agent_id}/connection/ws` with `connection_id` (UUID you reuse on reconnect). First frame
  `connection_state`; answer `ping` with a `pong` that includes your cursor (server pings every 2 s, evicts after 6 s).
  (agent-connection.md)
- Thread placement: `thread_id` is on `message` and `command` events; replies go to the same room and thread through the
  bridge's correlation table. (life-of-a-message.md, agent-events.md)
- **Thread-to-session mapping: UNCONFIRMED.** The docs do not say how threads map to agent sessions.

**2. Can it edit a message (set_status)?**
- **No documented edit or status operation.** agent-protocol.md says the operation catalog covers room documents
  (`update_room_document`), not messages. Rooms are described as append-only logs. Do not depend on editing.
- Workaround for progress: post a new message, or write a room document via `update_room_document` (UNCONFIRMED whether that
  suits status). Edit is tried once in the spike script (`ops/update_message`, UNCONFIRMED endpoint).

**3. How does a template declare instructions, MCP tools, allowed senders, custom rules?** (TEMPLATES.md, triage-pair template)
- Agent block keys: `instructions` (required), `provider` (`claude`, `codex`, ...), `directory` (workdir), `machine`, `location`,
  `model`, `advanced_config` (e.g. `effort`), `connections` (deployer connections such as GitHub), `repo`, `sources`,
  `addressing` (`owner`, `owner-agents`, `anyone`; v2 also `{anyone_in: [room keys]}`), `join`, `auto_mode`, `auto_approve`,
  `can_manage_agents`, `isolation` (`shared` | `isolated`).
- **MCP tools: no template key.** Tool limits live in the UI under Advanced configuration: `Tools` (allow-list),
  `Disallowed tools`, `Permission mode` (options not documented). Switch's own tools are kept either way.
- **Allowed senders:** `addressing` is the closest analogue. The access model is an addressing policy with rules over
  `rooms`, `room_groups`, `users`, `agents`, plus symbolic `owner` and `owner_agents`. Rules widen access; no rules means open.
  New agents admit only owner and owner agents. Platform accounts must be claimed to a Switch user before they match (identity-and-access.md).
- **Custom rules:** no dedicated key. Rules go inside `instructions` (triage-pair template does this).
- Template format versions 1 and 2 are read by Switch 0.31 (room-templates.md).

**4. How is a tool marked "always ask", and what do Allow once / Allow for this session / Decline look like?**
- **No per-tool "always ask" marker is documented.** Approval is controlled per agent under General: `Auto mode` (provider
  decides; the agent posts a request in the room for the rest) and `Bypass permissions` (runs everything; overrides Auto mode).
  Template equivalents: `auto_mode`, `auto_approve`. (agent-settings.md, TEMPLATES.md)
- Provider behaviour under Auto mode: Claude Code and Codex use their own automatic review; Cursor asks before every action;
  OpenCode approves everything without review (agent-settings.md).
- **"Allow once / Allow for this session / Decline" labels: UNKNOWN.** Not in any fetched page, and a web search found none for
  Switch. Ask in hackathon Discord.
- The incident-response use case relies on instructions for human sign-off: the agent pages the engineer and waits; Switch
  does not enforce the gate (incident-response.md).

**5. Does the agent see who approved?**
- **UNKNOWN.** No page says so. The closest fields are `user_id` / `user_name` on `command` events, but the docs do not say
  they identify an approver. Treat approval as a conversational reply the agent reads (the incident-response example).

**6. Can one agent work several threads at once?**
- Limits documented: up to 32 connections per agent (33rd refused with 409); at most one connection per agent may act in a
  given room (agent-connection.md). Reopening a live `connection_id` is a takeover (`taken_over` is final).
- **Parallel work across threads within one process: UNCONFIRMED.** The docs do not say whether one process may handle several
  threads concurrently. Plan on one connection per room and serialise work per thread.

**7. How is Claude Code configured (Auto mode on, Bypass off)?**
- Agent page, General: Auto mode on (default), Bypass permissions off (default). Claude Code runs its own automatic review under
  Auto mode. Model and Effort are set in the agent settings; Console saves them in `.switch/config/<name>.json` in the workdir.
  Claude Code sessions need the CLI installed and signed in on the machine (agent-settings.md). Matches the task's
  "Auto mode on, Bypass off".

**8. Slack vs bundled Mattermost setup.**
- **Mattermost (bundled):** Switch Console starts and connects the server. Open the server's Home page, select Sign-in
  details… under Messaging apps, and log in. Nothing to configure by hand (mattermost.md).
- **Mattermost (own server):** enable Bot Account Creation in System Console; set Teammate Name Display to first and last name;
  Connect → Mattermost, with fields Name, Url, Admin User, Admin Password, Team Name (slug), optional Public Url, Default Member,
  Callback Base Url (enables answer buttons).
- **Slack:** create the app from the Switch manifest (Socket Mode, no request URL, no public address needed). Generate an
  app-level token `xapp-` with `connections:write`, install the app and copy the bot token `xoxb-`, get the workspace id `T…`,
  then Connect → Slack in Console. Run `/invite @Agent Switch` in the channel to make it a room (slack.md).
  Bot scopes include `chat:write`, `channels:history`, `groups:history`, `im:history`, `mpim:history`, `users:read`.
  Events: `message.channels`, `message.groups`, `message.im`, `message.mpim`. Do not declare `agent_view` if the workspace has guests.
- Room commands: `!invite-agent @agent`, `!set-alias @agent @alias`, `!reset @agent`, `!compact @agent`, `!interrupt @agent`,
  `!assign-agent @agent`, `!unassign-agent` (room-commands.md).

## Alert path

**(a) PREFERRED: detector posts as its own Switch agent.**
1. Operator registers the detector once: `POST /agents` (registration key), store the returned `api_key`.
2. Set addressing so the detector and humans can reach Tripwire: `POST /agents/{tripwire_id}/ops/update_agent_detail` with
   `"addressing": "anyone"` or a rule that admits the detector agent (`agents` dimension) and the room.
3. Add the detector to the room (`!invite-agent @detector`) and give Tripwire an alias (`!set-alias @tripwire @tripwire`).
4. Post: `POST /agents/{detector_id}/message` with `{room_id, content}` and `Authorization: Bearer <detector api_key>`.
   The alert text addresses `@tripwire`. The scripted check is `scripts/switch_spike.py` (no flag).
5. Caveat: the docs do not say how the `addressed` flag is set on a message, so whether `@tripwire` in content triggers Tripwire
   is **UNCONFIRMED**. H00 must confirm it live.

**(b) FALLBACK: Slack bot user.**
1. Create the Slack app (above) and invite it to the incident channel.
2. Add the bot's Slack identity to Tripwire's addressing policy `users` dimension. Its platform account must be claimed to a
   Switch user first, or it matches nothing (identity-and-access.md).
3. Post with `chat.postMessage` (`POST https://slack.com/api/chat.postMessage`, `Authorization: Bearer xoxb-…`, `channel`,
   `text`; success is `ok: true` with `ts`). Run: `python scripts/switch_spike.py --fallback` (env `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`).
4. Whether Switch treats a bot post as a human sender for addressing: **UNCONFIRMED**. The incident-response page says a post
   from a Slack app counts the same as a typed one, which supports it.
5. Edit: `chat.update` was not confirmed from docs; the spike tries it once.

## Spike script

`scripts/switch_spike.py`. Env vars only: `SWITCH_BASE_URL`, `SWITCH_AGENT_ID`, `SWITCH_AGENT_KEY`, `SWITCH_ROOM_ID`
(path a); `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` (`--fallback`). `--dry-run` prints the request without sending. H00 runs it live.
