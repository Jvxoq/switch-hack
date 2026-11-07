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

## Research update, 2026-11-07 (H-PREP)

Re-read against docs.switchagents.ai and the TEMPLATES.md on GitHub. Items marked **confirmed** were seen on a fetched page.
Items marked **research note** came from the task brief and were not re-read by H-PREP.

### Corrections to the sections above

- **Template version key (confirmed, TEMPLATES.md):** the key is `version`, an integer. `template_version` is not read.
  `tripwire_agent/room_template.yaml` now uses `version: 1`. Its earlier `template_version: 2` was a silent no-op.
- **Template addressing values (confirmed):** `owner`, `owner-agents`, `anyone`. The template keeps `owner-agents`.
- **Agent ops addressing values (confirmed, agent-protocol.md):** `update_agent_detail` takes `owner_only`,
  `owner_and_owner_agents` or `anyone`. The `owner-agents` spelling above is for the template, not the op.
  Call it as `POST /agents/{id}/ops/update_agent_detail` with the agent's own key.
- **Registration `connector_type` (confirmed):** free-form. Switch does not validate it. H-PREP sends `tripwire-detector-py`.
- **Connection model for the detector (research note, agent-protocol.md):** `session_passive` fits a process that only posts
  and never listens. The docs do not name an option for this case. `scripts/register_detector.py` uses `session_passive`.
- **No MCP key in templates or agent settings (confirmed):** agent-settings.md mentions MCP only in the docs-search header.
  Tripwire's tools come from `.mcp.json` in the agent's Directory, which Claude Code reads. This is standard Claude Code
  behaviour (research note), not a Switch feature.
- **Console advanced fields (confirmed, agent-settings.md):** Model (alias such as `sonnet`, or a full id), Effort, Tools,
  Disallowed tools, Permission mode (no option values listed), Max turns, Isolation, Persistent memory, Color, Always run in
  background. No option values are documented for Effort, Permission mode or Max turns.
- **Who can talk to your agent (confirmed, agent-settings.md):** the options are "Me and my agents" (default), "Only me",
  "Anyone", "Custom rules".
- **Directory (confirmed):** fixed at creation for agents the Console runs. Set it to the clone path when you create the agent.

### Research notes (not re-read by H-PREP)

- **Approvals are conversational.** No approve or deny buttons are documented anywhere. The incident-response page relies on
  instructions for human sign-off. H-PREP's approval rule is a thread reply: `@tripwire approve` or `@tripwire decline`.
  `instructions.md` and the room template carry it.
- **Approver identity is still unknown.** `user_id` and `user_name` appear on `command` events, but no page says they name an
  approver. The tool server sends the fixed value `switch-approval`, and the containment service skips its owners check for
  that value (see `tripwire_agent/server.py`). So nothing server-side checks who replied. The only gate is Switch's
  addressing policy plus the agent's instruction to act on owner replies only. **PROVISIONAL.**
- **Message edit is not documented.** H-PREP makes replies the default. `SWITCH_STATUS_MODE=edit` stays opt-in.
- **Room id lookup:** the `list_rooms` op exists (agent-protocol.md), but its arguments are not documented. The setup
  guide calls it with an empty body. **UNCONFIRMED.**

### Still unconfirmed

Each of these is a live check in [switch-setup.md](switch-setup.md), steps 11 and 13 to 14.

1. Whether a REST-posted `@tripwire` in content sets the `addressed` flag and wakes Tripwire (Q1).
2. Whether `thread_id` in the body of `POST /agents/{id}/message` keeps the reply in the thread, and the shape of the
   response that carries the thread id (Q2).
3. Whether an owner's thread reply reaches the agent's session, and how threads map to sessions (Q3).
4. Who the approver is in the transcript, and whether `user_id` or `user_name` can identify them (Q4).
5. The `list_rooms` arguments and the room id.
6. Whether `POST .../ops/update_message` exists (the spike's edit probe). Expected: a 404 or 405 when it does not.
7. Console labels for per-tool approval ("Disallowed tools" names and the Permission mode options).
8. Whether the Console passes its environment to Claude Code, so the tool server sees `LANGFUSE_*` keys.
9. Whether `Who can talk to your agent: Me and my agents` admits the detector agent registered by the same owner.
