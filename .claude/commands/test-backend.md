---
description: Write pytest tests for the current backend changes, including concurrency tests, run them, and summarize
argument-hint: (optional focus, e.g. "just trial.py", or "refine" to only update this file)
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(find backend/tests:*), Bash(cd:*), Bash(uv run pytest:*), Bash(pytest:*), Bash(uv run ruff check:*), Bash(ruff check:*), Bash(uv run mypy:*), Bash(mypy:*), Bash(mkdir -p ~/.cache/test-backend/skill-backups:*), Bash(cp ~/.claude/commands/test-backend.md ~/.cache/test-backend/skill-backups/:*), Read, Edit, Write, Grep, Glob
---

Write proper pytest tests for the backend changes currently in progress, run them, and
report back. $ARGUMENTS

Modes:
- **Write mode.** Default. Follow the steps below.
- **Refine mode.** The argument is `refine`. Write no tests. Run "Refine this file" at the end of
  this file on what happened earlier in this conversation, then stop.

Context to gather first:
- Changed backend files: !`git status --short -- backend`
- Diff of those changes: !`git diff -- backend`
- Existing test layout for style/conventions: !`find backend/tests -name "*.py" -not -path "*__pycache__*"`

Steps:
1. Read every changed/new backend file in the diff above in full (not just the diff hunks)
   to understand what actually changed and why.
2. Look at `backend/tests/unit` and `backend/tests/integration` to match this project's existing
   test style (fixtures from conftest.py, naming, async patterns, how mocks/cassettes are used).
   Prefer fakes/stubs that implement real behavior over mocks that just assert calls, if that's
   the project's existing style.
3. Before writing a new test, check whether an existing helper/builder function in the target test
   file already constructs the thing under test. If so, extend its signature with an optional
   parameter (default preserving current behavior) instead of duplicating the construction inline
   or writing a parallel helper.
4. Write or extend tests that cover the new/changed behavior:
   - Unit tests for new functions/services/dependencies.
   - Integration tests for new/changed API routes.
   - Cover the golden path plus realistic edge cases (bad input, auth failures, missing data) —
     do not pad with trivial or redundant cases.
   - Assert observable behavior (return values, side effects, state changes), never a shape that
     would pass regardless of correctness — e.g. a bare length/truthiness check on a string or
     collection is not a test unless the length or emptiness is itself the contract.
   - When the same change is mechanically repeated across several sibling call sites (e.g. one new
     parameter threaded through three parallel use cases), don't write the identical behavioral
     assertion at every site. Test the code path that is genuinely distinct per site (e.g. "runs
     before any side effect happens" for each one, since each has different side effects to check),
     but write any test of a *shared, cross-site* contract (e.g. "this state is shared globally, not
     per-caller") exactly once, at the single most representative call site — not once per site.
   - When two tests differ only in one input value and assert the same outcome, merge them into one
     `@pytest.mark.parametrize` test rather than keeping near-duplicate bodies.
   - If the diff touches concurrency, also follow the Concurrency section below.
5. Run the backend test suite (`cd backend && uv run pytest` or `pytest` if uv isn't set up) and
   iterate until the new tests pass and nothing else regresses. Then run the project's linter and
   type checker too, if configured (e.g. `ruff check`, `mypy`) — a test file that passes pytest but
   fails lint/type-check is not done, and removing a test can leave an import unused.
   If a new test fails because the code is wrong, the test found a bug. Report the bug. Never
   change the test to match the bug.
6. Before finishing, re-read just the tests you added or changed and ask: would losing this test
   measurably increase the risk of shipping a real bug, or does it just repeat a contract another
   test already proves? Cut or merge anything that only repeats. Check them against every entry
   in Learned failures at the end of this file too.
7. Do not touch unrelated tests or files outside backend/ unless a shared fixture needs updating.
   Step 8 may edit this command file. That is the only other exception.
8. Run "Refine this file" at the end of this file.

Finish with a short TL;DR:
- What changed in the backend (plain language).
- What tests were added and what they cover.
- Pass/fail result of the run (tests, lint, type-check), and any bug a new test found in the code.
- For each race test, whether you watched it fail on the broken code.
- Concurrency tests or suite setup this change needs that you did not add, and why.
- Any gaps you'd suggest covering next (e.g. missing error case, no test for X), if any.

## Concurrency

Apply this section when the diff touches any of these: state shared between requests or tasks,
database writes or transactions, locks or semaphores, caches, queues or background jobs,
idempotency keys or one-time tokens, rate limits, retries, timeouts, cancellation, connection
pools, or code that runs on threads (`def` routes, `to_thread`). Skip it otherwise.

What to write and what to list:
- Pick only the items this change can actually break. Write the ones that run in CI with no
  outside network and no real clock. A local Postgres or Redis counts, if the suite already runs one.
- A test that needs real load, many machines, network faults or a deploy runs on real
  infrastructure. Do not write it here. List the ones this change needs in the TL;DR.
- Some items set up the whole suite, for example blockbuster, asyncio debug mode, ruff's ASYNC
  rules, the leak-check fixture, pytest-timeout, pytest-xdist, pytest-randomly, Hypothesis and
  Schemathesis. Use each one the suite already has. Do not add a missing one in this run, because
  it changes every other test or adds a dependency. Name it in the TL;DR.
- Items marked **(fleet)** matter only when production runs more than one instance. Some also
  need more than one region, for example at 20 million requests per second. Suggest one only
  when production runs that way.

### 1. Ground rules. These stop the mistakes an AI makes when it tests concurrency.
- A race test that passes once proves nothing. Run it many times, for example 200 loops, and require every run to pass. Loop inside the test, so one pytest run covers every loop. A test that drives the exact bad order by hand hits it every time, so one run is enough.
- Force the bad timing. Never hope for it. Line tasks up with an `asyncio.Barrier`, a point where tasks wait until all arrive.
- A fake with no await inside never gives up control. The tasks then run one after another, so the race never happens. Put an await point in every fake used in a race test. `await asyncio.sleep(0)` gives control back to the loop for one step, so it works as that await point.
- Never use a timed sleep to create a race or to wait for one. It makes tests slow and flaky.
- Assert a rule that must always hold. That is an invariant. For example "the balance never goes below zero" or "exactly one row exists". "No exception" is not an assertion.
- Prove the test can fail. Run it against the broken version first and watch it fail. A race test that passes on buggy code is worthless. To do that, run `git diff -- <file>` and keep the output. Remove the guard for a moment (the lock, the unique check, the `FOR UPDATE`). Run the test and watch it fail. Restore the guard, then confirm `git diff -- <file>` prints the same output as before.
- Every concurrency test has a timeout, for example with pytest-timeout. A deadlock then fails the test instead of hanging CI. Without pytest-timeout, wrap the test body in `asyncio.timeout`.
- A flaky concurrency test has found a race. Never retry it until it turns green. Find the race.

### 2. Where each bug shows up. Pick the layer that can actually show the bug.
- Unit tests with fakes catch logic bugs and interleaving bugs inside one process.
- Database races and deadlocks need real Postgres with separate connections. A mock or SQLite cannot lock rows like Postgres.
- Per-process state bugs need a real server with two or more workers. ASGITransport runs one process, so it hides them.
- Throughput limits, whether the real pool size is enough, and hot keys only show under real load.
- Timeouts, retries and circuit breakers only show with injected failures.
- If production uses PgBouncer in transaction mode, integration tests go through it too. Prepared statement errors show only there.
- **(fleet)** Network partitions, clock skew and gray failures need many machines across regions. One machine never shows them.
- **(fleet)** Operating system limits need real connection counts. File descriptors, ephemeral ports and the kernel's connection table run out only there.
- **(fleet)** Some bugs only show on real traffic. No staging copy is as big as 20 million requests per second. Canary releases catch these bugs.
- If the layer a bug needs is missing from this repo's tests, say so in the TL;DR. Never test it with a mock that cannot show the bug.

### 3. Blocking calls.
- Turn on blockbuster for every async test in `conftest.py`. It catches blocking input and output. It does not catch CPU work.
- Run tests in asyncio debug mode with `slow_callback_duration` at 50 ms. Debug mode then logs any step that holds the loop longer. An autouse fixture fails the test when that log appears.
- Send the largest allowed body through the real route, and call any route that hashes a password. Debug mode shows whether that CPU work holds the loop.
- Turn on ruff's ASYNC rules. They catch `time.sleep`, `open()` and sync HTTP inside `async def` before any test runs.
- Fill the thread pool with blocked calls. Then assert an async route still answers. An async route with a def dependency needs a pool thread, so it hangs here.
- Under load, watch event loop lag. A spike means something blocks. Find it with py-spy, a profiler that reads a live process's stack.

### 4. Race conditions. Each test fires the same action at once and checks an invariant.
- Drive two transactions by hand in the bad order. Session A reads, session B reads, A writes and commits, then B writes and commits. This hits the race every time, with no timing luck.
- Check-then-act: two tasks create the same unique item at once. Assert exactly one row and one 409.
- Read-modify-write: 50 tasks change one balance at once. Assert the final balance matches every successful change.
- Double spend: fire the same one-time token, coupon or reset link twice at once. Assert exactly one succeeds.
- Rate limit bypass: fire 100 requests at once at a limit of 10. Assert exactly 10 succeed. **(fleet)** Spread the requests across two or more instances. A counter kept per instance lets 10 through on each one.
- Idempotency: send the same key twice at once. Assert one effect and the same response for both. Then send the same key with a different body. Assert it is rejected.
- Queue redelivery: run the handler twice on one message. Assert one effect.
- Out of order: shuffle events before you feed them in. Assert the final state matches the in-order result.
- Cache stampede: 100 requests miss the same key at once. Assert the loader ran once. **(fleet)** Repeat it across two or more instances. A lock inside one process lets every instance load once.
- Cache order: interleave a slow reader with a writer. Assert the cache never keeps a value older than the write.
- Shared client leak: two users call at once. Assert each downstream call carried its own user's token. Check the headers the fake received.
- contextvar leak: fire concurrent requests. Assert each log line carries its own request's correlation ID.
- Replica lag: use a replica that returns old data. Assert a read right after a write still sees the write.
- Redis lock expiry: delete the lock key mid-work to act as expiry. Assert a fencing token still blocks the second effect. A fencing token is a number that rises with each lock grant. The database rejects any write with an older number.
- Threads: def routes and `to_thread` run on real threads. The GIL, Python's global interpreter lock, does not make `x += 1` safe. Test shared objects there with many threads.

### 5. Deadlocks and hangs.
- Lock two rows in opposite order from two sessions by hand. Assert the code locks in a fixed order, or retries the deadlock error until both succeed.
- Set `deadlock_timeout` to about 100 ms in the test database. Postgres waits that long before it looks for a deadlock. The default of 1 second slows tests.
- Read `pg_stat_database.deadlocks`, Postgres's deadlock counter, before and after each load test. Any increase fails the run.
- Pool deadlock: set the pool size to 1 and send 20 requests. A request that needs two connections at once hangs here.
- Nested semaphore: an outer call takes a slot, then an inner call needs the same semaphore. Enough outer calls hold every slot and wait forever. Run it with a semaphore of 1.
- `asyncio.Lock` is not reentrant. A task that takes it twice waits on itself forever. Run every path that holds a lock under a test timeout.
- A task that awaits a queue or an Event that nobody fills hangs forever. Wrap every such wait in a test with `asyncio.timeout`.
- When a test hangs, read the stacks. pytest-timeout dumps every thread's stack. `python -m asyncio pstree <pid>` shows the waiting tasks, on Python 3.14 or later. `pg_blocking_pids()` shows which query blocks which.

### 6. Database under concurrency.
- Race tests never use the "one rolled-back transaction per test" fixture. That fixture runs on one connection, so no race or deadlock can happen. Commit for real, then clean up by unique IDs.
- Use the production isolation level in tests. Under SERIALIZABLE, fire conflicting transactions and assert the retry succeeds.
- Assert the connection goes back to the pool before a slow call. Make the fake upstream wait, then check `engine.pool.checkedout()` is zero during the wait.
- Exhaust the pool. Assert the next request fails fast with 503 within the pool checkout timeout.
- Hold a lock from a second session to trigger `lock_timeout` and `statement_timeout`. Assert each one returns a clean error, not a hang.
- Count queries per request with a SQLAlchemy event listener. Assert the count is the same for 1 row and 100 rows. That catches N+1 queries, one extra query for every row.
- Seed production-sized tables. Run EXPLAIN, Postgres's query plan, on each hot query. Assert it uses an index. Ten rows hide a full table scan.
- Run each migration while load runs against the old code. Assert no request fails.

### 7. Cancellation, timeouts and retries.
- Cancel the operation at each await point in turn. After each cancel, assert no open transaction and no connection out of the pool.
- Assert `CancelledError` still rises after cleanup. A swallowed cancel keeps the task running and breaks `asyncio.timeout`.
- Make a fake upstream hang forever, with a tiny timeout in config. Assert the request returns the timeout error.
- Fail one child in a TaskGroup. Assert the other children stop and clean up.
- Track the peak number of in-flight calls in the fake. Assert it never passes the semaphore size.
- Test backoff with a fake sleep that records each wait. Assert each wait follows the backoff formula, for example the base doubles on each attempt. Assert Retry-After wins over the computed wait. Assert the total stops at the ceiling.
- Pass a seeded `random.Random` into the code for jitter, never a global seed. The test then gets the same waits every run.
- Count calls at every layer when a dependency fails. Assert the total stays inside the retry budget. Three layers that each try 3 times send 27 calls.
- Fail a dependency until the circuit breaker opens. Assert later calls fail fast without touching it. Then heal it and assert calls resume.

### 8. Resource leaks. An autouse fixture checks these after every test.
- The pool has zero connections checked out.
- No asyncio task is still pending.
- No Postgres session is "idle in transaction" in `pg_stat_activity`.
- Warnings become errors. That catches a never-awaited coroutine and an unclosed client.
- A destroyed pending task only logs an error through the `asyncio` logger. It raises no warning, so fail the test on that log.

### 9. Failure injection. Break dependencies on purpose and check the system degrades cleanly.
- Put Toxiproxy between the app and Postgres, Redis and upstreams. Toxiproxy is a proxy that adds delay, drops and resets on command.
- Inject a slow database, a connection reset mid-query, an upstream 500 and an upstream that never answers. For each one, assert a clean error, a fast response and no leaked connection afterward.
- Kill a worker while it holds a job. Assert the queue redelivers the job and its effect happens once.
- Crash between the database commit and the message send. Assert the outbox still sends the message. The outbox is a table that the same commit writes the message into.
- Fail over the Postgres primary. Assert the app reconnects and errors stop within a set time.
- Fail one item in a batch. Assert the batch returns with that slot marked as failed.
- **(fleet)** Cause a network partition between two regions. Assert each side keeps its invariants. After the network heals, assert the data agrees again.
- **(fleet)** Skew one machine's clock by minutes. Assert lock expiry, token expiry and rate limit windows still hold. Fake clocks in unit tests cannot show this.
- **(fleet)** Cause a gray failure in one instance. Assert the load balancer stops sending it traffic within a set time.
- **(fleet)** Take down a whole region. Assert the other regions take its traffic without overload.

### 10. Load tests.
- **(fleet)** One machine cannot generate 20 million requests per second. Run many load generators across regions. Merge their histograms, because an average of percentiles is a wrong number.
- Measure one worker's max rate at your p99 target. Then prove scaling is linear with 1, 2, 4 and 8 instances. Flat scaling means a shared bottleneck.
- Use an open load model, where requests arrive at a fixed rate. k6's constant-arrival-rate does this. A closed model waits for slow responses before it sends more. That hides slowness and is called coordinated omission.
- Report p50, p99, p99.9, **(fleet)** p99.99 and max from a histogram. Never report an average. At 20 million requests per second, 0.01% is 2,000 slow requests every second.
- Use a skewed key mix like real traffic, where a few keys get most requests. Uniform random keys hide hot keys and fake the cache hit rate.
- Match production: same instance size, pool sizes, PgBouncer, TLS and load balancer. Localhost numbers lie.
- Watch the load generator's CPU. If it is full, you are measuring the generator.
- **(fleet)** Open new connections in the test, not only keep-alive ones. File descriptors, ephemeral ports and the kernel's connection table only run out then.
- **(fleet)** Reconnect storm: restart a load balancer so every client reconnects at once. Assert the TLS handshake CPU keeps p99 under target. Assert errors stop within a set time.
- Run four shapes. Step load finds the breaking point. A spike tests sudden 10x traffic. A soak runs steady load for hours. Memory, open files, connections and tasks must stay flat. Growth in any of them is a leak. A cold start with an empty cache tests the stampede after a deploy.
- Push load past capacity. Assert the server returns 429 or 503 fast, and accepted requests keep their p99.
- After the overload ends, assert the system returns to normal within a set time. A system that stays broken after the trigger ends has a metastable failure. Retries usually cause it.
- Collect server numbers: event loop lag, pool wait, lock waits, deadlocks, Redis latency and garbage collector pauses. The load tool's numbers alone do not say why.
- Run a short load test on every change. Fail the build if p99 or throughput drops past a set margin from the last baseline.

### 11. Deploy and shutdown tests.
- Restart every instance one by one under load. Assert zero failed requests.
- Send SIGTERM with requests in flight. Assert `/ready` turns false first and every in-flight request finishes.
- Send low traffic with idle gaps through the real load balancer. Assert no request fails with a connection reset. The keep-alive race only fires on an idle connection.
- Run the old and new versions at once against one database and queue. Assert both work.
- **(fleet)** Ship every release as a canary. Compare its error rate and p99 with the old version. Assert it rolls back on its own when either gets worse.

### 12. Generated tests. These find edge cases a person would not think to write.
- Use Hypothesis for property-based tests. These check a rule over many generated inputs. Hypothesis shrinks a failure to the smallest case.
- Use Hypothesis stateful tests for ordering bugs. They run random sequences of operations and check invariants after each step.
- Run Schemathesis against the OpenAPI schema. It sends generated requests and fails on any 500 or schema mismatch.
- Test every size limit at max, max plus one, empty, a huge body and unusual Unicode.

### 13. Test hygiene.
- Each test uses fresh unique IDs, for example a new tenant ID. Parallel tests then never collide.
- Run tests in parallel with pytest-xdist and in random order with pytest-randomly. That exposes hidden shared state.
- Keep test pool sizes at 1 or 2. Leaks and pool deadlocks then show fast.
- Check the installed pytest-asyncio version. Its loop scope rules changed across recent versions. A mismatch gives "attached to a different loop" errors.
- Pass a fake clock into code that handles timeouts and expiry. Never patch datetime.

## Learned failures

Tests this command wrote that failed a review, a user correction or the prove-it-fails check.
Each entry names the tell, what it hid, and the rule. Never write these again.

None yet.

## Refine this file

Run this at the end of every write-mode run, and as the whole job in refine mode.

1. **Collect signals.** Use only what happened in this conversation:
   - The user corrected, rejected or rewrote a test.
   - A review, for example an /sfinder report, flagged a test, or a bug a test should have caught.
   - A new test passed on the broken code and had to be rewritten.
   - A race test flaked, hung, or never hit the race.
   - A rule in this file was wrong or unclear, or sent you the wrong way.
   - You needed a rule this file does not have.

   No signal means no change. Never add a rule from a guess.
2. **Diagnose.** Name each signal's tell in one line. Match it to a rule or a learned failure in
   this file. If nothing matches, it is new.
3. **Back up** before any edit:
   `mkdir -p ~/.cache/test-backend/skill-backups && cp ~/.claude/commands/test-backend.md ~/.cache/test-backend/skill-backups/test-backend-$(date +%F-%H%M).md`
4. **Edit.**
   - A rule was wrong or unclear: fix that rule where it lives.
   - A known failure repeated: sharpen its rule so it is harder to miss, and add the new tell.
   - A new failure: add the next `L<n>` entry to Learned failures with the date, the tell, what
     it hid and the rule.
   - Prefer changing an existing rule over adding one. Keep each rule generic enough for another
     project. Name the project detail only as the example.
   - Keep the file under about 350 lines. Past that, merge overlapping rules first.
   - Never weaken a rule or delete a learned failure unless the user asks.
5. **Log** one dated line in Skill changes.
6. **Tell the user** in one line, as the last TL;DR line in write mode: "test-backend updated:
   <what changed>. Backup in ~/.cache/test-backend/skill-backups." If they say
   `undo skill change`, copy the newest backup back over this file and log it.

## Skill changes

- 2026-07-25: created as a global command for backend tests.
- 2026-08-13: added lessons from the talk-to-the-web backend tests.
- 2026-09-19: added the concurrency checklist and this refine process.
