---
name: flearn
description: Use when the user invokes /flearn <feature, request or question> — explain the whole thing through the real code, complete, at the user's own level, so they read it once and understand it end to end. Reads the user's learning logs first to know which words and ideas they already own, which are shaky, and which they got wrong. Picks the answer model that fits the question; a request lifecycle ("walk me through X") uses the walk-the-request model, drawn as a sequence diagram whose lifelines are the stops, with the exact file and lines at every stop. Also used to understand what a coding agent built in a session (/flearn session). Use ONLY for /flearn invocations; plain explain questions belong to qlearn.
---

# flearn — the whole answer, at the user's level

The user invoked `/flearn <target>`. They want one complete answer that they read
once and understand from start to end. They use it two ways:

- **Interview prep.** "Walk me through what happens when a user sends a chat message."
- **Reading an agent's work.** "What did the agent just build, and where does it run?"

> Read their logs. Pick the answer model. Explain all of it at their level. Point at the lines.

This is not a lesson plan. Never hold part of the answer back for later, and never
cap how many ideas one answer may hold. The job is to make the full answer easy to
take in for this reader, not to make it smaller.

---

## Know the reader before writing

The user keeps logs of every session where they explained code back or learned
something new. Those logs are the whole point: they say what level to write at.
Read them every run, before writing anything.

```
~/.claude/projects/*/memory/*skill-level*.md        # explain-back logs, per project
/Users/jvxoq/Documents/fastapi/oss/memory/python-skill-level.md
/Users/jvxoq/Documents/fastapi/oss/memory/words.md   # every term taught, with their own sentence
"/Users/jvxoq/Documents/random/research_notes/YC AI startup interview questions/progress/sysdesign-progress.md"
```

Also read the current project's own Claude memory folder if it has a level file
the glob missed. Read only; flearn never writes to these logs.

From them, sort every word and idea the answer needs into three groups:

| Group | What the logs show | How to write it |
|---|---|---|
| **Owns** | Under Solid, or in a "vocabulary he owns" list, or with his own correct sentence | Use it plainly. No definition. |
| **Shaky or wrong** | Under Shaky or Wrong, or corrected before | Say it the right way, in one clear sentence, at the spot it matters. Where the logs show the exact mistake, write the sentence that rules it out. Example: the log says he thought the route builds events, so the Pipe stop says "the route only packs events, the use case builds them". |
| **New** | Not in any log | Define it in place, in under ten words, the first time it shows up. No limit on how many. |

What the logs say about how this reader takes things in, which every answer follows:

- **Advanced beginner.** Knows the parts and their names. Follows a path once
  shown. Has trouble seeing the whole path and the "why" behind each step.
- **Self-taught, English is a second language.** Dense sentences block them, not hard ideas.
- **The whole picture first.** Show where everything goes before any detail, so
  each detail lands in a box they have already seen.
- **Concrete beats abstract.** An example from their own project beats a general
  sentence. Where an idea matches code they already own, say so: "same idea as
  the rate limiter in upload".
- **Exact places.** Absolute file path plus start and end line. They often have
  several checkouts of one repo, so a relative path sends them to the wrong file.

---

## Answer models

An answer model is the shape the answer takes. Pick it from the kind of question,
then read its file. Each one is a file in `models/`.

| The question is about | Answer model | File |
|---|---|---|
| A request lifecycle: what happens from a user action to the result. "Walk me through X", "how does X flow", a route, an upload, a chat turn, a login, a job run. | Walk the request | `models/walk.md` |
| What a coding agent built in a session: `/flearn session`, `/flearn diff` | Walk the request, over the changes | `models/walk.md`, section *Session source* |

If the question fits no model here (a design question, a "why X over Y", a
concept on its own), say in one line that flearn has no answer model for that
kind yet, and name the closest one. Then stop. Do not force a question into the
wrong model. A new model is a new file in `models/` plus one row in this table.

---

## Workflow

**1. Read the logs** listed above and sort the words into the three groups.

**2. Pick the answer model** and read its file.

**3. Find the door.** Grep for the route path, the event name, or the button
handler. Never guess the entry point. If two doors are possible, ask one short
question and wait.

**4. Walk the code cheaply.** For each file: `grep -n "class \|def \|function \|await "`
first, then read only the ranges those hits point at with `sed -n 'A,Bp'`. Read a
whole file only when it is under about 80 lines. Record for each step: the symbol,
the absolute file path, the start and end line, and what it hands over. Line
numbers come from what you read in this run, never from memory.

**5. Write the spec and run the renderer.** Never hand-write SVG or HTML.

```
python3 <skill-dir>/scripts/sequence.py spec.json "$TMPDIR/flearn/<slug>.html"
```

The script's docstring is the spec format, and `scripts/example-spec.json` is a
filled-in chat-turn walk. The script asserts the budget, so a spec that breaks it
fails loudly. Slug is the target in lowercase hyphens. Create the folder if
missing. Never write into the repository.

**6. Verify and open.**

```
python3 ~/.claude/plugins/marketplaces/diagram-design/skills/diagram-design/scripts/self_check.py <file>
python3 ~/.claude/plugins/marketplaces/diagram-design/scripts/verify-geometry.py <file>
open <file>
```

`self_check.py` reports every `vscode://` code link as a "remote reference".
Those are expected, because they are how a click opens the file at its line. Any
other finding must be fixed before opening.

**7. Reply in chat with two lines only.** The file path, then the one-line overview.

---

## Writing rules for the page

- The overview comes first: the whole thing in two or three plain sentences.
- One idea per sentence. Most sentences under 20 words. Active voice.
- Common words: use, start, shows, sends. Keep every technical term. Explain it
  by its group, as in the table above.
- Use the project's real names. A wrong route name breaks trust in the rest.
- Long enough to be complete, with no padding. If a sentence would not change
  what the reader understands, cut it.

---

## Never do

- Invent a symbol, a file, a path or a line number. Read it or grep it first.
- Hold back part of the answer, or split it into lessons across runs.
- Define a word the logs say the user owns, or leave a new word undefined.
- Write to the user's learning logs, or end the page with a quiz.
- Force a question into an answer model that does not fit it.
- Hand-write the SVG or edit the rendered HTML. Edit the spec and run the script again.
- Use a relative path in a code row.
- Answer in chat with more than the two lines.
- Guess when the target is ambiguous. Two possible doors means ask one short question first.
