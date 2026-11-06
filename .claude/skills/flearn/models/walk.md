# Answer model: walk the request

The answer model behind this mode is the user's own note:
`/Users/jvxoq/Documents/random/research_notes/YC AI startup interview questions/progress/answer-model.md`.
If that file exists, read it first. When it disagrees with this file, it wins,
and this file should be updated to match.

## The model in one line

A request is a **package** that travels through **stops**. At each stop say three
things: **who** holds it, **what they do**, **what they hand to the next stop**.
If every stop says what it hands over, the flow connects by itself.

## Which stops

**An AI request (calls a model): six stops.**

| # | Stop | Question to answer |
|---|---|---|
| 1 | Screen | What did the user do, and what request left the client? |
| 2 | Door | Which route caught it? What did it check before spending money: auth, input shape, rate limit, input guard? |
| 3 | Context | What goes into the prompt, in what order? System prompt, history, retrieved data, the user message. What keeps it under the token budget? |
| 4 | Loop | Which model runs? Which tools can it call? What stops the loop: final answer, max steps, deadline? |
| 5 | Pipe | How do events become bytes on the wire: SSE, WebSocket, plain JSON? |
| 6 | Screen again | How does the client turn bytes back into something on screen? |

Stops 3 and 4 are deep: three or four sentences each. Stops 1, 2, 5 and 6 get
one or two. If Stop 4 says only "it calls the LLM", it is too thin.

**A plain request (no model): five stops.** Context and Loop merge into one
stop, **3 Brain**: the use case that does the work and what it hands back. Then
4 Pipe and 5 Screen again. Brain is the deep stop.

**No client at all** (a cron job, a CLI, a webhook): Stop 1 is whatever starts
it, and the last stop is where the result lands (a row, a file, a log line).
Say so in the overview.

## What to say at Context

- **System prompt:** sent once per thread or every turn, and why.
- **History:** how much is kept, and what happens when it gets too long.
- **Retrieved data:** where from, how many chunks, filtered by what (owner, thread).
- **Untrusted text:** anything from a file, a page or a tool is fenced, so the
  model treats it as data, not orders.
- **Budget:** what caps the size, so one request can't blow up the cost.

Name only the ones this code actually does. A missing one is worth one line.

## What to say at Loop

- **The loop:** the model answers or asks for a tool. The tool runs. The result
  goes back. Repeat.
- **Tools:** name them. Say who decides: the model alone, or code rules that can refuse.
- **Stop rule:** final answer, max step count, or deadline. Never "until the model is done".
- **Hands over:** a stream of events. The loop knows nothing about the wire format.

## The three closing blocks

- **Failure:** one, and an AI failure when the request is an AI request. Pick
  from: prompt injection, model timeout or outage, runaway loop, context
  overflow, wrong tool, data leak across users. Say which line of code defends
  against it. "User closes the tab" is only a backup.
- **Choice and why:** one. For example streaming vs one full answer, SSE vs
  WebSocket, agent loop vs fixed pipeline, rate limit before the stream starts,
  code rules vs trusting the prompt, which model. Say why this code made it.
- **Number:** one. Time to first token, cost per turn, tokens per request, a
  timeout, a cap. Prefer a number from the code or config (a setting's default)
  and say where it comes from. Never invent one.

## Interview cadence (print it once, at the bottom of the page)

1. One-line overview. 2. Draw the boxes. 3. Walk the stops, short at the edges,
deep in the middle. 4. One failure. 5. One choice and why. 6. One number. Then stop
and let them ask.

## Session source

Use this when the target is what a coding agent built: `/flearn session` or
`/flearn diff`.

1. Find the changes: `git status`, `git diff --stat`, and `git diff` against the
   base branch (or the last commit if the work is committed). Skip lock files and
   generated files.
2. Find the request the change sits on. Ask: "which user action makes this new
   code run?" That request is the walk. If the changes touch two unrelated
   requests, ask the user which one first.
3. Walk the whole request as usual, not only the changed lines. The user needs
   to see where the new code sits between the parts they already know.
4. Mark each stop the session changed with `"changed": true` in the spec. Point
   its code rows at the changed lines in the working tree.
5. The overview says what the change does and why the agent wrote it, in two
   or three sentences.
6. Add one line to the failure block: what broke, or could break, before this change.

## Check before rendering

- Every stop says what it **hands over**.
- Each job sits at the **right stop**. Common mistake: saying the route builds
  events. The loop or use case builds them. The pipe only packs them.
- Most of the words go to the deep stops.
- Every code row is an absolute path with lines read in this run.
- Every word is written by its group from the logs: owned words plain, shaky
  words said the right way, new words defined in place.
