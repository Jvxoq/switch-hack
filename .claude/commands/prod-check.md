---
description: Spin up the prod-parity environment for this repo, run every check CI runs (and a few it should), and give a strict go/no-go verdict for pushing to prod.
---

Run a full prod-parity verification pass on the current repo and report a go/no-go verdict. This command is generic — figure out the specifics of *this* project from what's actually in the repo, don't assume a stack. Don't skip a step because an earlier one failed; collect everything, then summarize.

## 0. Discover the project's actual setup

Before running anything, inspect the repo to find out what applies:

- Look for a prod-parity way to run the app: `Makefile` targets (`prod-up`, `prod-build`, etc.), `docker-compose*.yml` files (prefer one that looks like the leanest/prod-like config, not `dev`/`override`), a `Dockerfile` without a dev variant, or deploy config (`render.yaml`, `fly.toml`, `Procfile`, etc.) that hints at how it's actually built and run.
- Look for CI config (`.github/workflows/*.yml`, `.gitlab-ci.yml`, `circleci/`, etc.) — this is the ground truth for what "passing" means in this repo. Mirror those commands exactly rather than guessing your own; CI is the contract this project has already agreed to.
- Identify each buildable component (backend, frontend, workers, packages, monorepo apps — whatever exists) and its toolchain (uv/poetry/pip, npm/pnpm/yarn, cargo, go, etc.) from lockfiles and config files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`...).
- If nothing resembling a prod-parity stack exists (no compose file, no Dockerfile, no deploy config), say so explicitly in the report instead of inventing one, and fall back to running the strongest local checks available (lint/type/test/build).

## 1. Build & start the prod-parity stack (if one exists)

Bring up the most production-like local environment you found in step 0 (e.g. `make prod-up-d`, or `docker compose -f docker-compose.yml up --build -d` if that's the prod file, explicitly excluding any `-dev`/`override` overlays). Wait for every service to report healthy — poll `docker compose ps` / `docker ps` and any defined healthchecks, not just "container started." If a service exposes a health endpoint, curl it directly.

If a service fails to become healthy, pull its logs (`docker compose logs <service> --tail=100`) and record the failure, but keep going with the remaining checks so the final report is complete.

## 2. Run every check each component's CI runs

For each component identified in step 0, run its full CI-equivalent sequence, in the order CI runs it (install deps → lint → typecheck → test → build). Use the exact commands from the CI config where one exists, not approximations. Typical categories, adapt to what's present:

- **Dependency install** — clean install from the lockfile (`uv sync --all-groups`, `npm ci`, `pip install -e .[dev]`, `cargo build`, etc.), not an ad-hoc install that could silently update the lockfile.
- **Lint / static analysis** — must be zero warnings and zero errors. Do not treat "lint passed with warnings" as a pass.
- **Type check** — must be zero errors. Do not weaken strictness to make it pass.
- **Tests** — full suite, not a subset. If CI enforces a coverage floor, use that exact threshold; if none is defined but a coverage tool is configured, run with coverage reporting anyway and flag any glaring gaps (e.g. an untested new module).
- **Build** — production build must succeed with no errors. Flag build warnings too if the toolchain reports them (e.g. bundle-size warnings, unused-export warnings).
- **Security/dependency audit**, if the ecosystem has a standard one available (`npm audit`, `pip-audit`, `cargo audit`) — run it and report any high/critical findings. Don't fail the whole verdict on low-severity advisories, but list them.

## 3. Smoke test against the live containers (if the stack came up)

Hit the real endpoints of the running stack, not just unit tests: health/readiness endpoints, and at least one real request through the primary API/entrypoint if one exists (e.g. a signup/login flow, a root route, a CLI invocation). If the repo has its own smoke-test script (search for `test-docker-setup.sh`, `smoke.sh`, `e2e`, etc.), run that.

## 4. Check for things unit tests don't catch

- Any uncommitted or untracked changes that look like debug leftovers, commented-out code, `console.log`/`print` debugging, or secrets accidentally added to tracked files (do NOT read `.env` contents into the report — just flag if one is tracked in git when it shouldn't be, via `git status`/`.gitignore`).
- Any TODO/FIXME/XXX markers added in this diff that suggest incomplete work (`git diff` against the base branch, not the whole repo).
- Migrations: if there's a database migrations folder, confirm the latest migration actually applies cleanly against the prod-parity DB (don't just check the file exists).

## 5. Tear down

Stop whatever you started in step 1 (`make prod-down`, `docker compose down`, etc.) so the machine isn't left with a stack running.

## 6. Report

Give a strict, blunt TLDR. Default to **FAIL** unless every check in steps 1–4 that applies to this repo actually passed — "mostly passing" is not a PASS. Structure it like:

```
## Prod-parity check: <PASS / FAIL>

- Stack build/health: ...
- <Component A> lint: ...
- <Component A> types: ...
- <Component A> tests (coverage: X%): ...
- <Component A> build: ...
- <Component B> lint: ...
- ... (one line per applicable check, per component)
- Dependency audit: ...
- Live smoke test: ...
- Diff hygiene (debug code / secrets / TODOs): ...

**Verdict:** <Safe to push to prod / Not yet — fix X, Y before pushing>
```

Name the exact failing command and the exact error for anything that failed — never "some tests failed" or "lint had issues." If everything is genuinely green, say so plainly without hedging or manufacturing caveats.
