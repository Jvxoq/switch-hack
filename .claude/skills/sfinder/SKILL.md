---
name: sfinder
description: Use when the user invokes /sfinder, or asks to find AI slop, bullshit code, LLM-generated code smells, or check whether code is production quality — covers shitty logic, shitty abstraction, shitty tests, bad variable and test names, deep nesting, comment noise, overengineering, and security leftovers. General purpose, any language. Generates candidates mechanically, verifies each by reading context, then reports every confirmed finding as one blunt line that names the tell and gives a concrete fix. Report-only unless told to fix.
---

# sfinder — find the slop, name it, move on

Slop is code that compiles, passes its tests, and dies in a senior engineer's review.
It was written to look finished, not to be maintained.

Your job has three parts. Find it. Name it. Report it. Nothing else.

---

## Modes

- `/sfinder` — review the uncommitted diff (`git diff HEAD`) plus new untracked files.
- `/sfinder <path>` — review that file or folder.
- Clean tree and no path given — check for commits ahead of the base branch first. If there
  are some, review `git diff $(git merge-base origin/main HEAD)` (use the repo's base branch).
  Ask what to scan only when that diff is empty too. One line.
- `<path>` names one file of a larger change set: scan it, then say in one line which other
  changed files were not scanned. (2026-10-26: a scan of one test file missed a lazy import
  slop in `registry.py` from the same commit.)

In diff mode, newly added slop gets full treatment. Pre-existing slop gets one
summary line with a count, not a catalogue, unless asked.

---

## Process

Signals generate candidates. Candidates are not findings.

1. Run the mechanical sweep over the scope.
2. Read the changed files. For every candidate, read enough context to be sure.
3. For each changed function, ask three questions:
   - Does the name match what the body does?
   - Can every branch actually run?
   - Which line would a senior engineer delete?
4. Verify or kill each candidate. One wrong finding burns more trust than ten right
   ones earn. If you did not read the context, you have no finding.
5. Name the tell. Every finding carries a category and the specific tell from this
   catalogue, because a named pattern can be searched for and prevented next time.
6. Rank: hides a bug first, lies to the reader second, noise last.
7. Report. Fix nothing until told "fix them".

---

## The catalogue

### 1. Logic

- Silent `except Exception: pass` / `except: continue` — failure becomes silence.
- Fallback defaults that hide bugs: `config = load() or DEFAULT` turns a broken load
  into wrong-but-plausible behaviour.
- Boolean flag parameters (`send(email, is_priority=False)`) — one function pretending
  to be two.
- Magic numbers in comparisons. Name the state or use an enum.
- Branches that cannot run, or conditions nobody can parse without a comment.
- Mutating the caller's input.
- Bug-shaped classics — these are bugs wearing clean syntax:
  - Precedence trap: `if x == 1 or 2:` — always true.
  - Float equality: `result == 0.3`.
  - `is` used for value comparison instead of `==`.
  - Mutating a list or dict while iterating it.
  - Naive `datetime.now()` mixed with timezone-aware datetimes.
  - Dead stores: assigned, never read.
  - Builtin shadowing: `list = []`, `id = user.id`.
  - Unreachable code after `return` or `raise`.
  - Silent coercion of user input: bare `int(value)` around a try that swallows.

### 2. Error handling

- Catching X, raising generic Y("something went wrong") — destroys debugging.
- `try` wrapped around the whole function instead of the risky line.
- Catch-log-continue loops that silently drop poisoned items from a batch.
- `raise Exception("invalid")` — unnamed errors force callers to catch blind.
- C-style error returns (`return -1`, None-as-error) in languages with exceptions.
- Mixed failure styles inside one module: raises here, returns None there.

### 3. Async / concurrency

- `async def` that never awaits — fake async.
- Blocking calls inside async: `time.sleep`, sync HTTP clients, heavy CPU loops.
- Fire-and-forget tasks whose exceptions nobody will ever see.
- Sequential `await` in a loop over independent items — an N+1 in disguise.
- Unbounded `gather` over arbitrary-length input.

### 4. Types

- Bare `# type: ignore` / `@ts-ignore` with no reason. Coded ignores are discipline;
  bare ones are silencing.
- `Any` / `any` as a parameter or return type where a real type exists.
- `dict[str, Any]` grab-bag parameters — an untyped bag pretending to be an API.
- Casts whose only purpose is shutting the checker up.
- Optional-chaining chains ending in silent defaults (`a?.b?.c ?? ""`) that hide
  missing required data.

### 5. Naming

- Single letters outside tiny loops and math-heavy comprehensions.
- `data`, `result`, `temp`, `info`, `obj`, `stuff`.
- Numbered names: `data2`, `result_final`, `new_list`.
- Dead verbs: `process`, `handle`, `doWork` — say nothing about the outcome.
- Lying names: `get_user()` that also writes; `users` holding one user.
- Type-encoded names: `strName`, `userList`, `intCount`.
- Two naming conventions mixed within one file — usually two generation sessions merged.
- Constants that lie: `MAX_RETRIES = 1`.
- Abbreviation soup: `usr_mgr_hdlr`.
- Test names — judged by specificity, never by prefix:
  - Empty: `test_it_works`, `test_1`, `test_login_ok`.
  - Vague: `test_login` — works how? refuses what?
  - Dishonest: name says X, assertions check Y.
  - `test_it_refuses_a_mismatched_number_of_vectors` is a good name. Leave it alone.

### 6. Structure

- Nesting deeper than three levels — the arrow anti-pattern. Early returns fix it.
- Functions doing five jobs, or 200 lines long.
- Function definitions nested inside loops.
- Seven-plus parameters — the function wants an object or a smaller job.
- Copy-pasted `elif` branches differing by one literal — a lookup table is missing.
- `if x: return True else: return False` — return the expression.
- `else` after `return`, `raise`, or `continue`.
- Import inside a function, or only under `TYPE_CHECKING`, for a declared runtime dependency
  that the codebase imports at module top elsewhere. Check `pyproject.toml` and grep other
  modules before reporting. Optional dependencies imported late on purpose are fine.

### 7. Comments and docs

- Narrating comments: `# Loop through users` above a loop through users.
- Docstrings restating the function name.
- `# Step 1:` scaffolding left in shipped code.
- Commented-out code blocks.
- Emoji in logs or comments.
- TODO / "for now" promises nobody intends to keep.
- Banner separators in application code. Exempt: maintained index sections in token
  or stylesheet files.
- Changelog comments: "Fixed the bug where…", "Updated for v2".
- Hedging style: "Note that…", "It's worth noting…" — say the thing or cut it.
- Docstrings promising behaviour the code does not have.
- Javadoc on trivial getters while real complexity nearby has none.

### 8. Tests

- Testing mocks instead of behaviour — passes even when the logic is wrong.
- Weak asserts: `assert result is not None` as the only claim.
- Happy path only; the failure paths the code handles are untested.
- Asserting internal call order or log text — couples tests to implementation.
- Tautological tests asserting the mock configuration just set up.
- Five copy-pasted tests differing only by input — one parametrized test is missing.
- Calling private methods directly.
- Coverage theatre: tickling branches without claiming any behaviour.
- Fixed `sleep`s instead of waiting on a condition.
- Order dependence or shared mutable state between tests.
- Unseeded randomness — flaky by construction.
- No assertion at all.

### 9. Abstraction and overengineering

- `Manager` / `Handler` / `Helper` / `Utils` / `Wrapper` grab-bags.
- An interface with exactly one implementation, used once.
- Pass-through wrappers that add nothing but a frame in the stack.
- Speculative config knobs nobody sets.
- Premature base classes; plugin or registry systems with one entry.
- Copy-paste with a two-line variation instead of a parameter or function.
- Retry logic, circuit breakers, or caching nobody asked for.
- Re-validating input the boundary already validated.
- Logging every step like a trace dump.
- Custom exception classes raised exactly once.
- Compatibility shims for versions nobody runs.

### 10. Security leftovers

- Hardcoded secrets or placeholder keys: `"changeme"`, `sk-…`, test tokens.
- Disabled safety: `verify=False`, SSL checks off, `shell=True` near user input.
- String-interpolated SQL instead of parameters.
- CORS wildcard combined with credentials.
- Debug prints and `console.log` left in production paths.

---

## Mechanical sweep

All patterns need word boundaries. Every hit is a candidate only — read context before
reporting. These caught real false positives during calibration; the whitelist below
handles them.

```text
\bexcept\s*(Exception|BaseException)?\s*:
\bprint\(                                  # prod paths; fingerprint matched without \b once
\b(TODO|FIXME|HACK)\b|for now
#\s*type:\s*ignore(?!\[)                   # bare ignore; coded [arg-type] is fine
:\s*(any|Any)\b
\bconsole\.(log|debug)\(
verify\s*=\s*False | shell\s*=\s*True | allow_origins.*\*
def \w+\([^)]*=\s*(\[|\{)                  # mutable default arguments
\btime\.sleep\(                             # prod stalls; tests go flaky
class \w+(Manager|Handler|Helper|Utils|Wrapper)\b
def (process|handle)\b                     # needs \b — once matched document_to_domain
def test_(it_works|works|basic|simple|ok|success|\d)
range\(len\(                               # candidate only — often legitimate
```

Non-greppable tells (nesting depth, fake async, lying names, weak asserts, tautological
tests) come from reading. That is why reading is not optional.

---

## Whitelist — never report

- Cleanup, then re-raise: rollback in a UoW, discarding a half-written file. Correct code.
- Outermost boundary handlers converting errors into responses.
- Coded type ignores (`[arg-type]`, `[import-untyped]`) in small numbers.
- Generated code: migrations, lockfiles, vendored output.
- Existing project conventions, even when a textbook disagrees — including descriptive
  `test_it_*` test names.
- Deliberate indexed walks using `range(len(...))`.
- Section banners in organized token or CSS files.
- Single letters in math-heavy comprehensions and lambdas.
- Scratch and throwaway scripts: mention their existence once, do not catalogue them.

---

## Cross-file checks

- The same helper reinvented in two files — the most common real-repo slop. Report both
  sites and name the shared home they want.
- Dead files: `_old.py`, `.bak`, modules nothing imports within the scope.
- Twin configs that must agree (route lists, env var names, proxy paths): grep both,
  report the drift.

---

## Output contract

Brutal means blunt, not verbose. Every verified finding is shown.

One line per finding:

```
file:line — [category] <what is wrong>. Fix: <concrete replacement>.
```

Worst first. Then a verdict of at most two lines. No paragraphs. No hedging. No lecture.
A clean scope gets one line saying so. Never invent findings to look useful.

Report-only. Edit nothing until told "fix them".

When told to fix, and the report holds any Python test finding, or a bug the existing tests
should have caught, load the `test-python` skill first. It runs in repair mode: it fixes the
tests and records the slop in its own Learned failures so the agent stops writing it.

---

## Calibration example

Input:

```python
def process_data(data):
    result = []
    try:
        for item in data:
            if item["status"] == 1:
                result.append(transform(item))
    except Exception:
        pass
    return result

async def fetch_all(urls):
    out = []
    for u in urls:
        out.append(await http.get(u))
    return out

def test_it_works():
    svc = Service(Mock())
    assert svc.process_data([]) is not None
```

Expected report:

```
svc.py:3  — [logic] except/pass turns any failure into a silent empty list. Fix: let it raise.
svc.py:4  — [logic] magic number 1 for status. Fix: name the state.
svc.py:11 — [naming] process_data says nothing about what it produces. Fix: name the output.
svc.py:12 — [async] awaits each url in sequence; independent calls stall each other. Fix: gather.
tests/test_svc.py:17 — [test] test_it_works names no behaviour. Fix: test_returns_only_active_items.
tests/test_svc.py:18 — [test] asserts against a Mock, and is-not-None passes while broken. Fix: fake repo, assert exact output.
verdict: the first two hide real production failures. Fix those before merge.
```

---

## Self-check before sending

1. Did every finding come from context I actually read?
2. Does every finding name its category and tell?
3. Did the whitelist kill anything that only looked like slop?
4. Is each line blunt and under twenty words?
5. Would a senior engineer nod at every line?
