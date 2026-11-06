---
name: test-python
description: "Use BEFORE writing, editing, reviewing or auditing any Python test (pytest unit, integration, structure or eval tests, fixtures, fakes, conftest.py), and before saying Python code is tested or safe under load. Covers honest tests and the production failures tests must catch: timeouts, bounded concurrency, event-loop blocking, retries, partial failure, silent failure, output caps, secret leaks, unbounded growth, state leaking between requests, cancellation and resource cleanup. Load it when a change ships with tests, when the user says \"write tests\", \"add tests\", \"test this\", \"are these tests enough\", \"is this safe under load\", or runs /test-python, and before fixing any test finding. Repair mode runs after any review, audit or incident that found a bug the tests missed: it fixes the tests and adds a rule to this file."
---

# test-python: tests that fail when the code is wrong

A test exists to fail when behaviour breaks. A test that passes while the code is wrong
is worse than no test, because it tells the reader the code works.

Every change must survive two questions:

1. **"If I broke the line this test is about, would a test fail?"**
2. **"If a guard this code needs were missing, would a test fail?"** A missing timeout,
   bound, cap, log line or redact has no line to break. The production catalogue below
   names every guard. Each one that applies gets a test.

If the honest answer to either question is no, the tests are not done.

Scale changes what "rare" means. At 20 million requests per second, a one-in-a-million
input arrives 20 times every second. Rare is never a reason to skip a test.

---

## Modes

- **Write mode.** Default. You are about to write or change tests. Follow "Write mode process".
- **Audit mode.** The user asks whether existing tests are enough, or whether code is safe
  under load. Run the required breaks against the existing suite and report every escape.
  Report only, unless told to fix. Follow "Audit mode process".
- **Repair mode.** A review, an audit, an incident or a bug report found a problem the tests
  should have caught. The tests were slop. Follow "Repair mode process". It ends with an
  edit to this file.

## Read first

- The project's CLAUDE.md, all of it. Not only its testing rules. The production standards,
  code quality rules and constraints hold the failures the tests must catch. Every rule that
  says "every", "never" or "always" about runtime behaviour is a test obligation. Copy each
  one into the plan.
- `tests/conftest.py` and every other `conftest.py` under `tests/`. Reuse what exists.
- The test tool config: pytest options, the linter's selected rules, the warning filters.

Project rules win when they are stricter. When the project and this file disagree about
anything else, follow the one that makes the test assert more real behaviour, and tell the
user about the conflict in one line.

## Harness gates

Check these before writing a production test. Each one turns a silent failure into a red
test. If one is missing, tell the user it blocks the production tests, and propose the config
change. Never work around a missing gate.

In a repo you do not own (an open-source contribution), add no gates and no config. Follow
the repo's own harness, `conftest.py` and test layout. Say once which gates are missing.

- **A per-test time limit.** `pytest-timeout` with `timeout = 30` or lower in the pytest
  config. Without it, a missing timeout hangs CI instead of failing a test.
- **Warnings are errors.** `filterwarnings = ["error", ...]`. Each ignored third-party warning
  is named, with a comment saying why. Without this, "coroutine was never awaited" and
  unclosed-resource warnings pass.
- **No real network.** An autouse fixture in `tests/conftest.py` makes `socket.socket.connect`,
  `socket.socket.connect_ex` and `socket.getaddrinfo` raise, records each attempt, and fails
  at teardown when any was made. A broad `except` in the code under test swallows the raise,
  so the raise alone is not enough. See "Test patterns" and L14.
- **Lint rules that find killers.** Ruff `ASYNC` (blocking calls in async code), `BLE` (blind
  except), `S110` and `S112` (except that passes), `RUF006` (dropped task), `B006` and `B008`
  (shared mutable defaults).
- **The type checker**, in the mode the project runs in CI.

```toml
[tool.pytest.ini_options]
timeout = 30
filterwarnings = [
    "error",
    # Raised by LangGraph at import time, not by our code.
    "ignore::langgraph.warnings.LangGraphDeprecatedSinceV10",
]

[tool.ruff]
lint.extend-select = ["ASYNC", "BLE", "S110", "S112", "RUF006", "B006", "B008"]
```

---

## Hard standards

### What a test asserts

- Assert the outcome: a return value, a state change, a written record, a raised error, a log
  record, the size of what the run produced.
- A call to a fake counts as an outcome only when the call is the effect itself: the message
  sent, the row written, the request that leaves the process. Assert the whole call.
- Never assert that a value you passed in reached a middle layer unchanged. That is plumbing.
  It stays green when the run ignores the value. See L3.
- Assert the whole value. `assert result == {"a": 1, "b": 2}`, not `assert "a" in result`.
  `"5" in prompt` passes on any stray 5. Assert the whole phrase.
- No weak asserts: `is not None`, `hasattr`, `isinstance` or `len(x) > 0` alone prove nothing.
- Never assert the setup of your own mock. A test that configures a fake to return 3 and then
  asserts 3 tests the fake.
- `pytest.raises` always takes `match=` with the real message, or the test catches the
  wrong error.
- Every test has at least one assert, or one `pytest.raises`.
- Assert the fields the requirement names (the issue's acceptance criteria, the consumer's
  contract). A field the consumer derives from one you already assert adds noise. See L18.
- Never assert prompt prose. A test that a sentence is in the prompt breaks on any rewording
  and catches no bug. Assert the structure the code builds around untrusted text: the fence,
  the defused tag, the slot that holds it.

### One behaviour per test

- The test name is tight: subject, then outcome. Aim for 3 to 6 words after `test_`.
  Good: `test_budget_stops_new_questions`, `test_timeout_is_transient`,
  `test_deep_tier_keeps_caller_batch`.
  Too long: `test_a_pass_the_budget_stopped_still_reports_accuracy_for_what_ran`.
  Say it as `test_budget_stop_reports_accuracy`.
- Cut filler words: `a`, `the`, `that`, `it`, `is_recorded_as`, `still`, `every`. Keep the
  words that change the meaning. The file name already names the module, so do not repeat it.
- The why goes in the docstring, not the name. A name that needs a clause is two tests or a
  docstring.
- Never vague: `test_config`, `test_it_works`, `test_1`, `test_success`, `test_login_ok`.
  Tight is not vague. The name still says what happens.
- If a second assert checks a different claim, split the test.
- A docstring says why the behaviour matters, never what the code does.

### Coverage that matters

- Test every failure the dependency can produce, not only the ones the code handles. The
  dependency failure matrix in "Write mode process" lists them. The failure the code does
  not handle is the one that takes the server down.
- Test every guard in the production catalogue that applies to the code. See P1 to P16.
- Test each entry path. Code reached by an in-process caller and by a served request needs
  a test for each. See L4.
- Test each layer combination. When two rules can both change one value (a tier and a caller
  limit, an env value and a request value), test them together. See L5.
- Test every field a record promises, with a non-default value, on the success path and on
  the failure path. A counter that stays 0 in every test is untested. See L6 and P15.
- Test that old stored data still reads after a stored shape changes. See L7.
- Test security boundaries from the attacker's side: the request tries to set it, and the
  test asserts it did not take. See L2 and P14.
- Test an error classifier with the real error object, and with a near miss: text that holds
  the keyword but is a different failure. A generic-failure stand-in must not belong to a
  class the code treats specially. See L19.

### Setup, fixtures and fakes

- Repeated setup belongs in a fixture or a helper. The same two lines in two tests is a
  fixture you did not write. See L8.
- One fake per real thing, in `tests/conftest.py`. Shared capture fixtures live there too,
  the log sink included. A second fake of the same thing drifts.
- A fake mirrors every field of the thing it stands in for. A fake that only fills half the
  fields hides the other half. See L6.
- A fake mirrors the real thing's failures too. It is async when the real call is async. It
  raises the real library's exception classes, with their headers, for example the SDK's
  rate-limit error carrying `Retry-After`. A fake that raises a bare `Exception` hides the
  code that sorts errors.
- Every fake of an outbound call can answer, hang forever, and raise each real error class.
- Fake at the transport the real client uses. Check the SDK's HTTP library first: `anthropic`
  2.x sends through `httpx2`, so `respx` (an `httpx` mock) sees nothing. Hand the SDK a client
  built on that library's mock transport. See L17.
- Read span names, attribute keys and other library-made values from one real run before
  writing an assert. Never guess them. See L6.
- Inject time. The code takes its `sleep` and its clock as parameters. Never patch a module
  global such as `asyncio.sleep` or `time.monotonic` to skip a wait. Patching `asyncio.sleep`
  also removes every `sleep(0)` yield in the process, so concurrency tests stop seeing
  overlap. If the code has no injection point, the code needs one. See L11. The autouse
  network block is the one global patch allowed, because its job is to refuse, not to skip.
- Fixtures set values through the path the operator uses, never the path an attacker uses.
  See L2.
- Build test data with the real types (`Decision(...)`, `Row(...)`), not loose dicts, when
  the code under test takes those types.
- Never read or write a private name (`_thing`) from a test.
- A test that needs to reset module state has found shared state. Module-level state that
  requests write is a production bug (P10). Report it. Never add a reset to hide it. Only a
  process-wide cache of constants, such as settings, may expose a public reset like
  `get_settings.cache_clear()`.

### Isolation and determinism

- Use `monkeypatch` for env vars, attributes and `sys.path`. Never `os.environ[...] =`,
  never `os.environ.setdefault`, never a hand-written save and restore in `try`/`finally`.
- After changing env vars that a cached settings object reads, clear that cache in the same
  helper, or the test reads stale settings.
- Fixture teardown runs in reverse setup order. When another fixture's teardown needs a patch
  (a stubbed exporter, a blocked network), list `monkeypatch` before that fixture in the
  parameters, or the patch is undone first. See L17.
- No network, no DNS, no real clock, no real sleep. The autouse network block enforces the
  first two. Mock the model, the search API and the fetcher.
- One real wait is allowed: a deadline set through configuration to under 0.1 seconds,
  against a fake that never answers. It cannot flake, because the fake never answers.
- Never use 0 as a timeout or deadline in a test. `asyncio.timeout(0)` fires before the first
  await, and `if timeout:` reads 0 as "no timeout". See L12.
- `await asyncio.sleep(0)` and `asyncio.Event` waits are not the clock. Use them to order tasks.
- Freeze dates through configuration, never by patching `datetime`.
- No unseeded randomness. Inject the random source. Never assert two random draws differ.
- No order dependence. Every test passes alone and in any order. Run each new test file
  alone before you say it is done.
- Async tests run on the event loop through pytest-asyncio. Never wait on wall-clock time.

### Structure and guard-rail tests

- A guard-rail test walks the filesystem and is parametrized over every package. Never pin it
  to one known name.
- A guard-rail test fails when the thing it guards is missing. It never skips. See L1.
- A guard-rail test asserts its file list is not empty. `parametrize` over an empty list
  skips, which hides a broken glob. See L1.
- Every guard-rail test has a paired test that feeds it one bad snippet and asserts the guard
  flags it. A guard that cannot fail proves nothing.
- Parse source with `ast`. Never count occurrences of source text. Resolve import aliases, so
  `from time import sleep` still counts as `time.sleep`.
- Never weaken, skip or edit a guard-rail test to make new code pass. Fix the code.
- Production guards that `ast` can check, one guard-rail test each:
  - a blocking call inside `async def`, outside any nested sync `def` or `lambda`:
    `time.sleep`, `open`, `socket.getaddrinfo`, `socket.gethostbyname`, `subprocess.*`,
    `requests.*`, `urllib.request.urlopen`, and the project's sync SDK clients;
  - an outbound client built or called with no `timeout=`, for each client the project uses;
  - an `except` whose body is only `pass`, `continue` or `return None`;
  - `except BaseException` or `except asyncio.CancelledError` with no `raise` in its body;
  - a module-level name under `src/` bound to a mutable container (`{}`, `[]`, `set()`,
    `dict()`, `list()`, `defaultdict(...)`). Constants use `tuple`, `frozenset` or
    `MappingProxyType`;
  - `@lru_cache` or `@cache` on a function that takes parameters, with no numeric `maxsize`;
  - `asyncio.Queue()` with no `maxsize`.

### Shape

- Parametrize tests that differ only by input, with readable `ids=`.
- Arrange, act, assert, separated by one blank line each.
- Unit tests call the function directly. Integration tests run the compiled whole with the
  network mocked. Do not mix the two in one file.
- Tests follow the module they test. When code moves to another module, its tests move too.
- Delete a test when its behaviour is deleted. Never keep a test alive for dead code.

---

## Production catalogue

Each entry names a failure that takes down a busy server, the test that catches it, and the
breaks that test must catch. Every entry that applies to the changed code gets its test. An
entry that does not apply gets a one-line reason in the plan. "Hard to test" is not a reason.

An entry applies when the code has the thing it is about:

- an outbound call: P1, P3, P4, P5, P12, P13;
- a loop or fan-out over a list the caller or the model controls: P2, P5, P16;
- an `except`: P6, P11;
- text that reaches a prompt, a log line or the caller: P7, P8;
- code that can see a credential: P8;
- state kept across rounds, requests or calls, a cache or a queue: P2, P9, P10;
- an `await`: P11;
- a field the request can set: P14;
- a result record, counter or metric: P15.

**P1. Timeouts.** One slow dependency holds a worker forever. Workers run out and the service stops.
- Test: the fake hangs. The deadline comes from configuration, under 0.1 seconds, never 0.
  Assert the item gets its timeout result and the batch still returns. One test per timeout
  layer: per request, per item, per batch, per model call.
- When the timeout lives inside a third-party client that no test can run without the network
  (a model SDK, for example), build the real client and assert the timeout it holds. That
  client is the last object before the network, so its setting is the effect, not plumbing.
- Breaks: remove the timeout. Set it to `None`. Replace the configured value with a literal.
  The per-test time limit turns each break into a failure.

**P2. Bounded concurrency.** A fan-out over a caller's list opens thousands of calls at once.
The provider rate-limits everyone, or the worker runs out of sockets.
- Test: start at least `bound + 3` items against a `PeakGauge` fake, then `settle()`. Assert
  the number in flight equals the bound exactly. "At most the bound" passes code that runs
  one call at a time.
- A queue between a producer and a consumer has a `maxsize`. Test that a full queue makes
  the producer wait or refuse.
- Breaks: raise the bound to `10**9`. Set it to 1. Remove the semaphore.

**P3. Event-loop blocking.** One sync call inside `async def` stalls every request on the worker.
- Test: fake each sync function the code must run off the loop (DNS, file read, heavy parse,
  sync SDK) with the `off_loop` fake. Drive the async path and assert its result.
- Break: replace `await asyncio.to_thread(f, x)` with `f(x)`.

**P4. Retries.** Retries in lockstep multiply traffic against a provider that is already failing.
One test per line:
- each family (rate limit, transient, bad response) keeps its own counter and budget.
  Exhaust one family, then assert the other still retries;
- the exact list of backoff waits, from an injected sleep recorder and an injected random source;
- jitter is in the wait: rolls of 0 and of 1 give the exact two waits the formula promises;
- a `Retry-After` header sets the floor of the wait;
- a provider that always rate-limits ends with the gave-up result, and the recorded waits add
  up to no more than the ceiling;
- a bad model response is retried with no wait;
- a retry prompt keeps every earlier correction, in order;
- a retried call that writes (a row, a message, a charge) writes once;
- the SDK's own retries are off, or the counters include them. Stacked retries multiply;
- when the code promises a circuit breaker or load shedding, it opens at the threshold and
  then refuses without calling the dependency.
- Breaks: one shared counter. No jitter. `Retry-After` ignored. No ceiling. Backoff on a bad
  response. The prompt rebuilt from the original. SDK retries turned on.

**P5. Partial failure.** One bad item fails the whole batch, and the batch retry multiplies the load.
- Test: a batch of at least three where the middle item fails, once for each way it can fail:
  it raises, it hangs past its deadline, it returns a body that does not parse. Assert every
  other slot holds its own result, in order, and the failed slot holds its error.
- Breaks: move the parse outside the item's `try`. Let one item's error escape the `gather`
  or the `TaskGroup`.

**P6. No silent failure.** Errors happen and nobody sees them until the outage or the bill.
- Test: for every `except` that does not re-raise, capture logs with the `log_records`
  fixture. Assert the whole list of records at WARNING and above: level, message, and that
  the exception is attached when the code uses `logger.exception`.
- A second test asserts the returned value can be told apart from success.
- On the success path, assert the whole record list too. One log line per item is a flood
  at scale.
- Breaks: delete the log call. Return the success value from the `except`.

**P7. Bounded output.** One huge page or error body lands in a prompt, a log line or a response.
Cost and memory spike on every request that sees it.
- Test: feed the limit, the limit plus one, and a hundred times the limit. Assert the length
  is at most the limit and the cut mark is present. Cover error messages and log lines, not
  only results. A provider error can carry the whole response body.
- Measure the text that reaches the prompt, after every step that runs after the cap: escaping,
  defusing, wrapping. Feed hostile text that the step grows, at the limit. Never assert a length
  over the limit as expected. (2026-10-30: `&lt;` escaping after the cut put a page of tags 60%
  over its ceiling, and a test named `..._cut_before_defusing` locked the overflow in.)
- Break: remove the cap at the call site. Breaking the cap function alone only proves the helper.
  Make a later step grow the text.

**P8. Secrets.** A key in a log line, an error or a trace is a leaked key.
- Test: use a distinctive fake secret. Drive the failure path whose error quotes the request.
  Assert the secret appears in none of: the log records, the returned error, the returned
  state, the trace metadata.
- Break: remove the redact call.

**P9. Bounded growth.** Memory or prompt size grows with rounds or with traffic until the worker dies.
- Test: run the loop for 2 rounds and for 6 rounds with same-size inputs. Assert the prompt
  size at round 6 equals the size at round 2. For a cache, call it with more distinct keys
  than its `maxsize` and assert its size stays at `maxsize`.
- Breaks: switch a replace reducer to `operator.add`. Remove the `maxsize`.

**P10. Isolation between requests.** One user's data shows up in another user's answer, or one
request's counters charge another.
- Test: run at least two requests at the same time through the same compiled object, with
  different inputs, and different session or thread ids where the framework has them. Assert
  each result holds only its own data and its own counters.
- Breaks: keep per-request data in a module-level dict. Share one counter object between runs.

**P11. Cancellation.** A client disconnects. The server keeps working, holds the slot, or
swallows the cancel.
- Setup: fakes built on `PeakGauge` that record each call. Start the call as a task,
  `settle()`, note the calls so far, cancel the task, `settle()` again. One test each:
  - awaiting the task raises `CancelledError`;
  - the gauge shows 0 in flight;
  - a new call started after the cancel gets the slot;
  - the fakes received no new call after the cancel. Work stopped, it did not retry;
  - the cancel wrote no ERROR log and no error result. A cancel is not a failure.
- Breaks: an `except BaseException` that logs and returns a value. A retry loop that catches
  `asyncio.CancelledError` and goes on.

**P12. Resource lifetime.** A new client per request opens a new connection pool per request.
Sockets and file handles run out.
- Test: the fake client counts builds and closes. Run a batch of N. Assert the build count
  the code promises (once per batch, or once per process) and that closes equal builds.
- Breaks: build the client inside the per-item function. Drop the close.

**P13. Hostile input.** A malformed payload crashes the worker. At scale, malformed input
arrives every second.
- Test: a parametrized table for every parser of outside data (model output, HTTP body, JSON,
  file): empty, blank, truncated mid-token, missing closing tag, wrong type, extra keys,
  duplicate keys, huge, invalid UTF-8. Assert each gives the typed error result and no other
  exception escapes. Duplicate keyword arguments raise `TypeError`, not `ValidationError`.
- Breaks: catch only `ValidationError`. Return the partial content of a truncated block.

**P14. Untrusted request fields.** A caller sets a credential, an endpoint or a ceiling.
- Test: the request tries to set it. Assert what the run did: the endpoint it called, the
  model it used, the batch size the tool received. See L2 and L3.
- Test: the request asks for more than a ceiling allows, a list longer than the largest batch
  included. Assert the run capped it or refused it.
- Break: let the request value win.

**P15. The failure path is measured.** A stopped run still reports its sizes, counters and waits.
- Test: stop a run on each failure path. Assert every counter and size in its record, with a
  non-default value. See L6.
- A pass that a guard stops early (a budget, a deadline, a lost item) still reports what it
  finished: its score, its counts, its spend. Test the report after the stop. See L16.
- Breaks: hardcode 0 when the run stops. Return before the summary on the stop path.

**P16. Work per request.** Code that calls a dependency again for every item it already
handled turns one request into thousands of calls.
- Test: a batch of 1,000 items against a fake that counts calls. Assert the exact count the
  code promises: once per item, or once per unique item when it removes duplicates.
- Breaks: call the dependency inside a loop over all items. Remove the duplicate check.

---

## Test patterns

`~/.claude/skills/test-python/patterns.py` holds the helpers the P entries need: `PeakGauge`,
`settle`, `hang`, `off_loop`, `SleepRecorder`, the `log_records` fixture with `logged`, and
the autouse `no_real_network` fixture. Each one was checked on 2026-09-19 against
research_agent/backend: it passed on the real code and failed on the break it exists for.
When a P entry applies, copy the helper it needs into `tests/conftest.py` once. Never write a
second version of one.

The bound test (P2):

```python
async def test_search_runs_exactly_its_bound_of_queries_at_once(install_search) -> None:
    gauge = PeakGauge()

    async def handler(query: str) -> dict[str, object]:
        await gauge.hold()
        return PAYLOAD

    install_search(handler)
    batch = asyncio.create_task(run_search(FIVE_QUERIES, concurrency=2))

    await settle()
    held = gauge.in_flight
    gauge.gate.set()
    await batch

    assert (held, gauge.peak) == (2, 2)
```

- `settle()` needs the real `asyncio.sleep`. That is one more reason never to patch it (L11).
- The path from the call to the fake must have no thread hop. Give any `to_thread` step an
  async fake in this test, or `settle()` can end before the thread returns.
- If the code awaits many times before it reaches the fake, raise the count in `settle()`.
  The count is right when raising it further changes nothing.
- The log assert (P6) compares `logged(log_records)` with the whole expected list, for example
  `[("ERROR", "search failed", True)] * len(QUERIES)`.

---

## Learned failures

These are slop tests this agent wrote. A reviewer or an audit caught every one. Each entry
names the tell, what it hid, and the rule. Never write these again.

**L1. The guard-rail that skipped.** (2026-09-17)
Tell: `if not declared: pytest.skip("declares no ROUND_LOOP_FIELDS")`.
Hid: a new agent that forgot the declaration passed the guard with nothing checked.
Rule: a guard-rail test asserts the declaration exists, then checks it. Missing means fail.
A `parametrize` over an empty list also skips, so assert the list is not empty.

**L2. The fixture that used the attacker's path.** (2026-09-17)
Tell: the shared `config` fixture put `think_model` in `configurable`, the HTTP request body.
The precedence test proved "the request wins" using `think_model`.
Hid: any caller could pick an expensive model on the operator's key. The tests locked the hole
in as expected behaviour.
Rule: before a test proves "the caller can set X", ask whether a stranger should set X. Precedence
tests use a field a caller is allowed to set. Operator values come from env in fixtures. Every
server-only field gets a test where the request tries to set it and fails.

**L3. The plumbing assertion.** (2026-09-17)
Tell: `assert fake_graph.configs[0]["configurable"]["max_rounds"] == Configuration().max_rounds`.
Hid: passing the whole config through the request re-capped the deep tier's batch size. The test
stayed green because it checked what went in, not what the run did.
Rule: never prove a feature by inspecting arguments handed to a fake. Run the real path and
assert the outcome, for example the batch size the tool actually received.
Repeat (2026-10-29): a structure test asserted that the rendered Dockerfile set
`ENV UV_CONSTRAINT` before the install. The build tool passed its own `-c`, and uv reads the
env var only when no flag is given, so the image still shipped unlocked versions with 16 tests
green. A test on config that builds an artifact proves the shape only. Build the artifact once
and check the outcome (here, installed versions against the lock), and keep that outcome check
where the artifact is built, in CI.

**L4. Only one entry path tested.** (2026-09-17)
Tell: every retry-counter test injected counters through `configurable`, the eval runner's path.
Hid: a served run has no injected counters, so every retry count was thrown away.
Rule: list every way a caller reaches the code. Write one test per path. In LangGraph, that is
an in-process `ainvoke` and a served run with a plain JSON request body.

**L5. Layers tested alone, never together.** (2026-09-17)
Tell: one test for the deep tier, one test for a caller lowering a limit, no test for both.
Hid: the deep tier overwrote the caller's lower limit.
Rule: when two rules can change one value, test the pair. Write the table of combinations
first, then one test per row that the code treats differently.

**L6. Half a family tested, and a fake that filled half.** (2026-09-17)
Tell: the result line test checked `rate_limit_hits`. The fake graph only charged rate-limit
counters. `transient_retries` existed in the counters and never reached the result line.
Rule: for each record, list every field it promises. Each field needs a test with a non-default
value. The fake must set every field the real thing sets.
Repeat (2026-10-22): `getattr(runs[0], "url", None)` read a field LangChain's `Run` lacks, and
`runs[0]` was a model call, not the root. Every test line held `trace_url: None`, so no test
could fail. A value read from a third-party object is tested against what the real library
produced (here, the run the tracer posted), never against a hand-built stand-in.
Repeat (2026-10-26): asserted on a span named `"Messages"` from memory. The real span was
`"messages.create"`, and `anthropic` 2.x also emitted its own second span. Print one real
run's span names and attributes first.

**L7. A stored shape changed with no old-data test.** (2026-09-17)
Tell: new required fields added to a result-line schema. No test fed an older line.
Hid: an old line failed validation, so a resumed run would pay for finished questions again.
Rule: when a persisted or resumed shape changes, write a test that feeds the old shape and
asserts it still reads the way the code promises.

**L8. Copied setup between tests in one file.** (2026-09-17)
Tell: two manifest tests built the same registered-package set line for line. Two more
repeated the same resolve-and-import block.
Rule: the second copy is the signal. Extract a helper or fixture before writing the second test.

**L9. The unbounded fan-out nobody tested.** (2026-09-19)
Tell: no test started more items than the concurrency bound. The only concurrency test checked
that a bound of 0 was refused.
Hid: `asyncio.Semaphore(10**9)` in both search tools passed all 334 tests.
Rule: P2. Start more items than the bound and assert exactly the bound in flight.

**L10. The error nobody logged.** (2026-09-19)
Tell: every `except`-path test asserted the returned value only.
Hid: deleting `logger.exception` in the page fetcher, and again in the decision node, passed
all 334 tests.
Rule: P6. Capture the log and assert the whole record list.

**L11. The global sleep patch.** (2026-09-19)
Tell: `monkeypatch.setattr("core.retry.asyncio.sleep", skip)`, with a docstring that says
"the retrier's sleep". `core.retry.asyncio` is the `asyncio` module itself, so every
`asyncio.sleep` in the process became a no-op.
Hid: every `sleep(0)` yield vanished. A concurrency probe with a bound of 2 saw one call at a time.
Rule: inject sleep into the code. Never patch a module global to skip a wait. Patching
`a.b.name` changes `name` for everyone who shares `a.b`.

**L12. The zero deadline and no time limit.** (2026-09-19)
Tell: deadline tests passed `timeout_seconds=0`. The project had no per-test time limit.
Hid: with the deadline removed, the test waited 16 seconds of real time before an inner
timeout saved it. With both timeouts removed, CI would hang forever.
Rule: P1 and the harness gates. A small non-zero configured deadline, a hanging fake, and a
per-test time limit.

**L13. Only the code's own list was tested.** (2026-09-19)
Tell: the test plan came from reading the code, and the self-check compared only against L1 to L8.
Hid: 3 of 12 production breaks escaped. The 9 that were caught were caught because the project
CLAUDE.md asked for those tests, not because of this file.
Rule: the plan comes from the code, the dependency failure matrix, the production catalogue
and the project's runtime rules. Every required break is run, not reasoned about.

**L14. Tests written before the network gate existed.** (2026-09-20)
Tell: a new runner test called `main()` without installing the judge fake. The project had no
autouse network block, and step 2 of write mode was skipped.
Hid: the test sent a request to api.openai.com with a fake key. The judge's broad `except`
logged the 401 and the test still passed.
Rule: check the harness gates before the first new test, every time. A missing network gate
is added first. The gate fails at teardown, because a broad `except` swallows its raise.

**L15. A test that kept a dead branch alive.** (2026-09-20)
Tell: a parametrized case fed `httpx.ConnectError` to the retry classifier after every
retried client had moved to `httpx2`.
Hid: an entry in the transient-error tuple no caller could reach, and a comment claiming one could.
Rule: every error class a test feeds in must come from a real caller's cause chain. Prove it
by reading the client's imports. When the dependency moves, delete the case with the branch.

**L16. One test, three claims, and the stop path's report untested.** (2026-09-20)
Tell: `assert (code, out_path.exists(), error_log) == (1, False, [...])` under a name that
claimed only one of the three. No test read the summary after a budget stop.
Hid: the budget-stopped pass returned before logging accuracy, so paid results vanished from
the report.
Rule: a tuple assert is still one claim per element. Split them. Every early return in a
runner gets a test that asserts the summary it must still print (P15).

**L17. The patch undone before the teardown that needed it.** (2026-10-26)
Tell: `def instrumented(memory_exporter, monkeypatch)` stubbed the exporter. `monkeypatch`
was set up after `memory_exporter`, so it was undone first. The shutdown in
`memory_exporter`'s teardown then sent spans to a real port and retried for 30 seconds.
Same test: `respx` was the first pick, but `anthropic` 2.x uses `httpx2`, which `respx` cannot see.
Rule: order fixture parameters so every patch outlives the teardown that needs it. Fake the
transport the SDK really uses.

**L18. "Fails without the fix", said from memory.** (2026-10-26)
Tell: the PR body said the new tests fail without the fix. Against the base code, 1 of 4
failed. The end-to-end test covered the supported version, so it passed on base too. The
nesting test also asserted a span kind that the issue never asked for and the backend
derives from the model name.
Rule: run every new test against the base branch code and list which fail. A test of the
working path that passes on base is fine, but say so. Assert only what the requirement names.

**L19. The classifier test that fed the matcher its own keyword.** (2026-11-02)
Tell: `fail_with=RuntimeError("Completion provider failed: Request timed out.")`, written to
prove `"timed out" in text` maps to a timeout code. No case held the word "timeout" in a
different failure. Elsewhere, `TimeoutError("upstream went away")` stood in for "any failure".
Hid: any 400 body quoting a `timeout` parameter became a retryable timeout. Sorting by text
stayed green, because the test held exactly the string the matcher looked for.
Rule: drive a classifier with the error the real SDK raises, built with its cause chain. Add
a near-miss case: the keyword in a different failure. Pick generic stand-ins (for example
`ConnectionError`) that the code under test does not treat specially.

---

## Write mode process

1. **Read.** Follow "Read first".
2. **Check the harness gates.** Report any missing gate before writing production tests.
3. **Plan.** Build one table. Each row is one obligation and names its test, or says "does not
   apply" with a reason. Rows come from four sources:
   - the code: each behaviour, failure path, entry path, layer combination and written field;
   - the dependency failure matrix. For each outbound call (HTTP, model, search, DNS, file,
     subprocess, database), one row each: it answers, hangs, raises its timeout error, raises
     its connection error, rate-limits with and without `Retry-After`, returns a server error,
     returns an error inside a success body, returns a malformed body, returns an empty body,
     returns a huge body, and is cancelled mid-call;
   - the production catalogue, P1 to P16;
   - every runtime rule in the project's CLAUDE.md.
4. **Reuse.** Use existing fakes and fixtures. Copy any helper a P entry needs from
   `patterns.py`. Add a fake only if none exists, and put it in `tests/conftest.py`.
5. **Write** one test per row, with a tight subject-outcome name.
6. **Break.** In a scratch copy, never in the working tree, apply each break: one per new test,
   plus every break listed under each P entry that applies. Run the suite against the copy.
   Each break must turn a named test red. A break that stays green is an escape: write the
   missing test and break again. Also run the new tests against the base branch code and
   record which fail. Any claim about "fails without the fix" comes from that run. See L18.
7. **Run** the whole suite, the linter and the type checker. Run each new test file alone.
   Write a long or background run to a file (`> run.txt 2>&1`) and read the count from it.
   Never pipe a background run through `tail`. An empty result is not a pass.
8. **Self-check** with the list below.
9. **Report** the break table: each break, and the test it turned red. No table means the
   tests are not done.

### Break recipe

```bash
SCRATCH="<session scratchpad>/breaks"; rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
cp -R src tests pyproject.toml "$SCRATCH"/     # plus every other file or folder the tests read
cd "$SCRATCH"
sed -i '' 's/asyncio.Semaphore(concurrency)/asyncio.Semaphore(10**9)/' src/core/tools/web_search.py
diff -r <repo>/src src                          # must show exactly the one break
PYTHONPATH="$SCRATCH/src:$SCRATCH" perl -e 'alarm 120; exec @ARGV' \
    <repo>/.venv/bin/python -m pytest -q -p no:cacheprovider
```

- On Linux, GNU `sed` takes `-i` with no `''`.
- Check the tests import the copy. An editable install points at the real `src`, and
  `PYTHONPATH` must come first. Print one module's `__file__` once.
- One break at a time. Restore the copy before the next break.
- The `perl` alarm kills a run that hangs, because a break can hang when the per-test time
  limit is missing. A run the alarm killed is not a catch. It means the per-test time limit
  is missing, which is a finding of its own.
- Afterwards, `git status` in the real repo shows no change you did not make.

## Audit mode process

1. Read, as in write mode.
2. Check the harness gates. Each missing gate is a finding.
3. List every P entry that applies to the code under audit, with its breaks, and every runtime
   rule in the project's CLAUDE.md.
4. Run each break in a scratch copy with the break recipe. Record the test that turned red, or
   "escaped".
5. Report every escape with the break, the file and line, and the test that would catch it.
   Report only, unless told to fix.

## Repair mode process

Triggered by any finding the tests should have caught: an sfinder report, a code review, an
audit-mode escape, an incident, or a bug report. The finding is evidence that tests were slop.

1. **Collect.** Take every test finding. For every production finding, ask: which existing test
   should have caught this, and why did it pass?
2. **Diagnose.** Name the tell in one line. Match it to a standard, a P entry or a learned
   failure. If nothing matches, it is a new failure. A production finding with no P entry
   means the catalogue has a gap.
3. **Fix the tests.** Rewrite each slop test to the standards. Add the missing test for each
   production finding. Prove each one turns red against the broken code and green against the
   fix, with the break recipe.
4. **Update this file.** Back up first:
   `mkdir -p ~/.cache/test-python/skill-backups && for f in SKILL.md patterns.py; do cp ~/.claude/skills/test-python/$f ~/.cache/test-python/skill-backups/$(date +%F-%H%M)-$f; done`
   - A known failure repeated: sharpen that entry's rule so it is harder to miss. Add the
     new tell to the entry.
   - A new failure: add the next `L<n>` entry with date, tell, what it hid, and the rule. Add a
     line to the matching hard standard that points to it.
   - A production failure with no P entry: add the next `P<n>` with its failure, its test and
     its breaks. A helper it needs goes in `patterns.py`, checked with `ruff check`,
     `mypy --strict` and one run against a real suite and its break.
   - Keep entries generic enough to apply in another project. Name the project detail only
     as the example.
   - Keep this file under about 650 lines. Past that, merge overlapping entries first.
   - Never weaken a standard, delete a P entry or delete a learned failure unless the user asks.
5. **Log.** Add one dated line to "Skill changes" below.
6. **Tell the user** in one line: "test-python updated: <what changed>. Backup in
   ~/.cache/test-python/skill-backups." If they say `undo skill change`, restore the newest
   backup and log it.

## Self-check before you say tests are done

1. Did I read the whole project CLAUDE.md, and does each runtime rule in it have a plan row?
2. Does every P entry have a test, or a one-line reason it does not apply?
   Did I copy helpers from `patterns.py` instead of writing new versions?
3. Did every outbound call get its dependency failure matrix rows?
4. Did I run every break in a scratch copy, and did each one turn a named test red? Ran it,
   not reasoned about it.
5. Are the harness gates on? If not, did I tell the user?
6. Does any fake answer at once where the real thing can hang, or raise a plain `Exception`
   where the real thing raises its own class?
7. Did I patch a global to skip a wait, where I could inject?
8. Does any test use 0 as a timeout, or wait on real time other than a deadline under 0.1
   seconds against a hanging fake?
9. Is every test name 3 to 6 words, one behaviour, and does its assert check exactly that?
10. Did any fixture set a value through a path a stranger could use?
11. Did any assert inspect what I handed to a fake instead of what the run did?
12. Is any setup copied between two tests?
13. Does any guard-rail test skip, walk zero files, or lack its paired bad-snippet test?
14. Did I check the new tests against every learned failure?

---

## Skill changes

- 2026-09-17: created with standards and L1 to L8, from the IterResearch sfinder review.
- 2026-09-19: audit found 18 loose rules. 3 of 12 production breaks escaped the research_agent
  suite. Added the second question, "Read first", harness gates, production catalogue P1 to
  P16, `patterns.py`, audit mode, the break recipe, and L9 to L13. Resolved the fake-call
  contradiction. Replaced the public-reset rule. Backup in ~/.cache/test-python/skill-backups.
- 2026-09-20: sfinder review of the budget stop. Added L14 to L16, sharpened the network gate
  (fail at teardown) and P15 (report after an early stop). `no_real_network` in patterns.py
  now records attempts. Backup in ~/.cache/test-python/skill-backups.
- 2026-09-20: test names are tight, 3 to 6 words, subject then outcome. The why moves to
  the docstring. Asked for by the user.
- 2026-10-22: sfinder review of the eval runner's trace_url. Sharpened L6 with the
  getattr-default tell. Backup in ~/.cache/test-python/skill-backups.
- 2026-10-26: traceroot-py#201 tests. Added L17 (fixture teardown order, fake the SDK's real
  transport) and L18 ("fails without the fix" from memory, extra asserts). Sharpened L6 with
  the guessed span name. Added the open-source harness rule, the requirement-fields assert
  rule, base-branch runs in Break, and run-to-file in Run. Backup in
  ~/.cache/test-python/skill-backups.
- 2026-10-29: research_agent deploy image. Sharpened L3: a config-shape test stayed green
  while the built image ignored the config. Check the built artifact itself. Backup in
  ~/.cache/test-python/skill-backups.
- 2026-10-30: sfinder review of the prompt fence. Sharpened P7: measure the text after every
  step that runs after the cap. Added the no-prompt-prose assert rule. Backup in
  ~/.cache/test-python/skill-backups.
- 2026-11-02: sfinder review of chat reply timeouts. Added L19 (classifier test fed its own
  keyword, stand-in error from a special class) and the classifier line under "Coverage that
  matters". Backup in ~/.cache/test-python/skill-backups.
