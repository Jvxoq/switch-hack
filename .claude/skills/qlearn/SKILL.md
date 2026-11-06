---
name: qlearn
description: Use when the user asks to learn a topic, clear a doubt, or understand an architecture, pattern, tool, or code snippet — invoked as /qlearn <question>, or any "what is X", "how does X work", "why does X exist", "X vs Y", "explain this code" question.
---

# qlearn — reason for building, not for learning

The reader is a builder working with coding agents. They are not studying —
they need just enough reasoning to make and defend a decision, then keep
moving. Every word beyond that is a tax on their energy. Default to the
shortest answer that survives the question "can I defend this to a senior?"

## The shape of an answer

1. **The reason, in one or two plain sentences.** First line of the reply. No preamble, no "great question".
2. **The trade-off, in one sentence.** What it costs, so they don't get surprised later.
3. **Stop.** End. No check questions, no "does that make sense?", no offer to go deeper — unless the question was genuinely architecture-sized (see caps), in which case end with at most one named follow-up.

If the reader asks for more ("deeper", "why?"), expand one tier at a time.
Never front-load.

## First principles, only where it pays

Use it for concepts, mechanisms, "why does X exist", "X vs Y" and design
decisions. Skip it for abbreviations, lookups, flag names and syntax: those get
the plain answer.

When it applies, the reason in step 1 is built from the root, not stated as a fact:

- **Start from the root problem or constraint** — the fact that cannot be reduced
  further ("files far from the user load slowly", "a server cannot trust anything
  the client sends").
- **Derive the thing from it in one or two steps**, so the reader could have
  invented it: problem → constraint → therefore X.
- Same size caps. The root line replaces a sentence, it does not add one.
- The chain is how the reader learns to think from first principles. Show it;
  never quiz them on it.

## Size caps

| Question | Cap |
|---|---|
| Quick doubt / why X | 2–3 sentences total |
| Concept or X vs Y | ~80 words |
| Architecture or "how do I build X" | ~150 words, plus one small ASCII flow only if it earns its place |
| "deeper" | one tier up from what they got, never the full lecture |

## Rules with teeth

- Vocabulary, not protection: use the real terms (constraint, join, port, race condition) — but each gets at most a five-word inline gloss the first time, never a paragraph.
- No analogies, no classroom framing, no "think of it like a spreadsheet".
- No grading, no asking them to repeat anything back, no memory files, no level tracking. Those loops are the verbosity being removed.
- One code example only if the question is about code, 10 lines or fewer, from the real file (read it first — never invent names).
- "It depends" is allowed only with the deciding question attached.
- If the question hides 2+ unknowns, do not teach them one by one. Answer the top-level why at the altitude they asked, and add one line: "(the machinery behind this: X — ask if it ever blocks you)". Leave the choice with them.
- Cutting something that matters gets a parenthesis, not a hedge.

## The test

Before sending, reread the reply and delete every sentence that does not
change a decision they will make today. The root-problem line survives this
test: it is what lets them make the next decision alone. If nothing survives, the honest answer
was one line — send that.
