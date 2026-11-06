---
description: Write clean, focused tests for the latest frontend changes — for production safety, not coverage theater
argument-hint: (optional focus or path, e.g. "src/features/chat" or "just the session refresh logic")
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(find:*), Bash(cat:*), Bash(cd:*), Bash(npm run:*), Bash(npm test:*), Bash(npx vitest:*), Bash(npx jest:*), Bash(yarn test:*), Bash(pnpm test:*), Bash(pnpm run:*), Read, Edit, Write, Grep, Glob
---

Write proper tests for the frontend changes currently in progress, run them, and report
back. $ARGUMENTS

## 1. Find the frontend project

There's no fixed directory name to assume (`frontend/`, `web/`, `apps/web/`, `client/`, or the
repo root itself are all fair game). Locate it:

- If `$ARGUMENTS` names a path, start there.
- Otherwise find the nearest `package.json` that depends on a UI framework (react/vue/svelte/etc)
  or a bundler (vite/webpack/next) — `find . -maxdepth 4 -name package.json -not -path "*/node_modules/*"`
  then check each candidate's `dependencies`/`devDependencies`.
- If more than one plausible frontend exists, ask which one before doing anything else.

## 2. Gather context on the actual change

- `git status --short` and `git diff` scoped to that directory — read every changed/new file
  **in full**, not just the diff hunks, so you understand what changed and why, not just the lines
  that moved.
- Read `package.json` (`scripts`, `dependencies`, `devDependencies`) and the test config
  (`vite.config.ts`/`vitest.config.ts`/`jest.config.*`) to find out, for real, not by assumption:
  - Which runner (Vitest/Jest/etc) and how it's invoked.
  - Which environment is configured (`node` vs `jsdom`/`happy-dom`) — this determines whether
    component tests are even possible right now.
  - Whether a component-testing library (React Testing Library, Vue Test Utils, etc) and a
    fetch-mocking layer (MSW, nock) are actually installed — don't assume they exist because
    they're common; grep for them.
- Skim the existing test files (colocated `*.test.ts(x)` or a `__tests__`/`tests` dir) for this
  project's real conventions: naming, fixture/mock setup, how modules with side-effecting module
  state get reset between tests (e.g. `vi.resetModules()` for singletons), async patterns.
- If a CLAUDE.md or README documents testing conventions or known gotchas (module-level state,
  no-jsdom-by-design, etc), treat that as authoritative over generic best practice.

## 3. Decide what's actually worth testing

The goal is production safety and maintainability, not a coverage number. The categories below are
places to *look*, not a checklist to fulfill — finding a "data transform" in the diff is not itself
a reason to test it; a plausible way it could ship broken is. Before writing anything, triage the
diff and be able to state, for each test you're about to add, the specific bug in production it
would catch. If you can't state that in one sentence, don't write it.

**Write tests for:**
- Logic that can silently produce a wrong result: data transforms, parsers, formatters, reducers,
  derived state, validation, auth/token/session handling, retry or race-condition-prone code
  (single-flight guards, aborted requests, debounce).
- Boundary and failure conditions a real user or a flaky network will actually hit: empty/error/
  loading states, malformed API responses, expired/invalid tokens, concurrent calls.
- A component only when it carries real behavior (conditional rendering, form validation, a11y-
  relevant interaction) — and only if the environment/tooling to test it (jsdom + a component
  testing library) is already in place. If it isn't, say so as a gap instead of quietly bolting on
  new dependencies and config — that's a call for the user, not something to slip in.

**Don't write tests for:**
- Pure prop-drilling / presentational components with no branching.
- Things TypeScript already guarantees (don't test that a required prop is required).
- Trivial getters/setters or one-line wrappers around a library call.
- Snapshot tests as a default — they pass on drift, not on correctness, and rot fast. Only use one
  where the actual assertion of interest is "the rendered output," not implementation shape.
- Re-testing a third-party library's own behavior (React, the router, the fetch client) instead of
  your integration with it.
- Anything already exercised, at the same depth, by an existing test — read the current suite
  before adding, not just the diff.

If nothing in the diff meets the "worth it" bar, say so plainly rather than padding the PR with
filler tests.

## 4. Write the tests — tight, not exhaustive

- One behavior per test, one reason to fail. If a test's name needs "and" to describe what it
  checks, or its body has several unrelated assertion blocks, split it or cut the parts that don't
  pull weight.
- Don't multiply cases that exercise the same code path. `null`, `undefined`, and `""` hitting the
  same guard clause is one test, not three — pick the input most likely to occur for real (or use a
  single parameterized/table-driven test if the runner supports it and the cases genuinely differ in
  outcome, not just in input shape).
- Match the project's real runner, conventions, and file layout — colocate as `*.test.ts(x)` next
  to the source unless the project already uses a separate test directory.
- Assert behavior and observable output, not implementation details (internal state shape, class
  names, call counts on things that aren't the point). If a component test is hard to query by
  role/label, that's usually a sign the markup itself isn't accessible — don't paper over it with a
  `data-testid` as the first resort.
- Mock at the boundary (network layer), not by stubbing your own modules, unless the project's
  existing tests already establish a different pattern — match what's there.
- Cover the golden path plus the edge cases from step 3 that survived the "one sentence" bar.
  Nothing else.

## 5. Prune before you run

Re-read every test you just wrote, cold, as if reviewing someone else's PR. For each one, ask: does
this catch a production bug that no other test in this file already catches? Cut or merge any that
don't — it's easier to delete a redundant test now than to leave it as maintenance debt later. Then
run.

## 6. Run and iterate

Run the project's actual test command (check `package.json` scripts — don't assume `npm test`
is right) and iterate until the new tests pass and nothing else regresses.

## 7. Don't touch what isn't yours

Stay inside the frontend directory identified in step 1. Don't touch backend tests, unrelated
frontend files, or add/upgrade testing dependencies without flagging it to the user first.

## Finish with a short TL;DR

- What changed in the frontend (plain language, no jargon).
- What tests were added and what production risk each one guards against.
- Pass/fail result of the run.
- Anything you deliberately chose *not* to test and why (per step 3), and any real gaps (e.g. "no
  jsdom/RTL installed, so the new modal's keyboard-trap behavior is untested") worth flagging.

