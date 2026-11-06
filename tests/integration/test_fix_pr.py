"""Fix-PR tool against a local bare git repo and a stubbed GitHub API (tasks.md A02, T15).

The git side is real: a bare origin, a clone standing in for the agent's workdir, and real pushes.
The GitHub side is an httpx.MockTransport, so no test reaches the network.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.containment import FakeContainment
from tripwire_agent.tools import open_fix_pr as open_fix_pr_module
from tripwire_agent.tools.open_fix_pr import (
    GIT_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    MAX_PATCH_CHARS,
    FixPrError,
    FixPrTool,
    GitHubPulls,
    GitRepo,
)

PR_URL = "https://github.com/acme/app/pull/7"
SECRET = "ghp_test_only_secret_1234"
ORIGINAL = "one\ntwo\n"
PATCH = """--- a/app.txt
+++ b/app.txt
@@ -1,2 +1,2 @@
 one
-two
+TWO
"""


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "seed",
        "GIT_AUTHOR_EMAIL": "seed@example.invalid",
        "GIT_COMMITTER_NAME": "seed",
        "GIT_COMMITTER_EMAIL": "seed@example.invalid",
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env
    ).stdout


class FakeGitHub:
    """Stands in for api.github.com and records every request the tool sends."""

    def __init__(self, status: int = 201, *, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.requests: list[tuple[str, str, dict[str, Any], str]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.requests.append((request.method, request.url.path, body, request.headers.get("authorization", "")))
        if self.error is not None:
            raise self.error
        if self.status != 201:
            return httpx.Response(self.status, json={"message": "Validation Failed"})
        return httpx.Response(201, json={"html_url": PR_URL})


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin whose `main` holds app.txt, and a clone that stands in for the agent's workdir."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    workdir = tmp_path / "workdir"
    _git(tmp_path, "init", "--bare", "-q", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    (seed / "app.txt").write_text(ORIGINAL)
    _git(seed, "add", "app.txt")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", str(origin), "main")
    _git(tmp_path, "clone", "-q", str(origin), str(workdir))
    return origin, workdir


def _open_incident(containment: FakeContainment, clock: FakeClock) -> str:
    incident = containment.open_incident("loop", "order-lookup", clock.now())
    containment.update(incident.id, root_cause="The loop repeats the list call.")
    return incident.id


def _tool(containment: FakeContainment, workdir: Path, github: FakeGitHub) -> FixPrTool:
    pulls = GitHubPulls(token=SECRET, owner="acme", repo="app", transport=github.transport())
    return FixPrTool(containment=containment, git=GitRepo(workdir), pulls=pulls)


def test_T15_pr_opens_with_patch_on_branch(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """The reviewer sees the patched file on the incident branch, and the PR targets the base branch."""
    origin, workdir = repos
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)

    result = _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    assert result == f"PR opened: {PR_URL}"
    assert _git(origin, "show", "tripwire/INC-1:app.txt") == "one\nTWO\n"
    assert _git(origin, "log", "-1", "--format=%s", "tripwire/INC-1").strip() == "INC-1: Stop repeated list calls"
    assert [(m, p, b["head"], b["base"]) for m, p, b, _ in github.requests] == [
        ("POST", "/repos/acme/app/pulls", "tripwire/INC-1", "main")
    ]


def test_T15_no_approval_or_merge_requested(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """Opening a PR changes no containment state and sends no request beyond the PR creation."""
    _, workdir = repos
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)
    log_before = list(containment.log)

    _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    incident = containment.get(incident_id)
    assert (incident.state, incident.action, incident.approver) == ("detected", None, None)
    assert containment.log == log_before
    assert [(m, p) for m, p, _, _ in github.requests] == [("POST", "/repos/acme/app/pulls")]


def test_T15_pr_url_stored_on_incident(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """The incident keeps the PR URL, so the thread and the detector can find the fix."""
    _, workdir = repos
    incident_id = _open_incident(containment, clock)

    _tool(containment, workdir, FakeGitHub()).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    assert containment.get(incident_id).pr_url == PR_URL


def test_T15_token_stays_out_of_results(
    containment: FakeContainment,
    clock: FakeClock,
    repos: tuple[Path, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The token travels only in the Authorization header, never in the result, the logs or the incident."""
    _, workdir = repos
    caplog.set_level(logging.DEBUG)
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)

    result = _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    assert github.requests[0][3] == f"Bearer {SECRET}"
    assert SECRET not in result
    assert SECRET not in caplog.text
    assert SECRET not in repr(containment.get(incident_id))


def test_T15_token_comes_from_env(
    containment: FakeContainment,
    clock: FakeClock,
    repos: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production constructor reads GITHUB_TOKEN and sends it as the bearer token."""
    _, workdir = repos
    monkeypatch.setenv("GITHUB_TOKEN", SECRET)
    github = FakeGitHub()
    pulls = dataclasses.replace(GitHubPulls.from_env("acme", "app"), transport=github.transport())
    incident_id = _open_incident(containment, clock)

    FixPrTool(containment=containment, git=GitRepo(workdir), pulls=pulls).open_fix_pr(
        incident_id, "Stop repeated list calls", PATCH
    )

    assert github.requests[0][3] == f"Bearer {SECRET}"


def test_T15_missing_token_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing token stops the tool at construction, not on the first incident."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(FixPrError, match="GITHUB_TOKEN is not set"):
        GitHubPulls.from_env("acme", "app")


def test_T15_github_call_has_timeout(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """The GitHub request carries the configured read timeout, so a hung GitHub cannot hold a worker."""
    _, workdir = repos
    timeouts: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(201, json={"html_url": PR_URL})

    pulls = GitHubPulls(token=SECRET, owner="acme", repo="app", transport=httpx.MockTransport(handler))
    incident_id = _open_incident(containment, clock)

    FixPrTool(containment=containment, git=GitRepo(workdir), pulls=pulls).open_fix_pr(
        incident_id, "Stop repeated list calls", PATCH
    )

    assert timeouts == [HTTP_TIMEOUT_SECONDS]


def test_T15_every_git_call_has_timeout(
    containment: FakeContainment,
    clock: FakeClock,
    repos: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every git subprocess gets a timeout, so a hung remote cannot hold a worker forever."""
    _, workdir = repos
    seen: list[tuple[str, Any]] = []
    real_run = subprocess.run

    def recording_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.append((args[1], kwargs.get("timeout")))
        return real_run(args, **kwargs)

    monkeypatch.setattr(open_fix_pr_module.subprocess, "run", recording_run)
    incident_id = _open_incident(containment, clock)

    _tool(containment, workdir, FakeGitHub()).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    verbs = [verb for verb, _ in seen]
    assert verbs == ["fetch", "worktree", "apply", "commit", "push", "worktree"]
    assert all(timeout == GIT_TIMEOUT_SECONDS for _, timeout in seen)


def test_T15_github_refusal_stores_no_pr_url(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """A refused PR is reported as a refusal, and the incident keeps no PR URL."""
    _, workdir = repos
    incident_id = _open_incident(containment, clock)

    result = _tool(containment, workdir, FakeGitHub(status=422)).open_fix_pr(
        incident_id, "Stop repeated list calls", PATCH
    )

    assert result == "refused: GitHub refused the pull request: HTTP 422"
    assert containment.get(incident_id).pr_url is None


def test_T15_github_timeout_is_refused(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """A hung GitHub call ends as a refusal with its error class, not as a crash or a stored URL."""
    _, workdir = repos
    incident_id = _open_incident(containment, clock)
    github = FakeGitHub(error=httpx.ReadTimeout("no answer"))

    result = _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    assert result == "refused: GitHub request failed: ReadTimeout"
    assert containment.get(incident_id).pr_url is None


@pytest.mark.parametrize(
    "patch",
    ["", "   \n", "not a diff at all", "--- a/missing.txt\n+++ b/missing.txt\n@@ -1 +1 @@\n-x\n+y\n"],
    ids=["empty", "blank", "not-a-diff", "file-missing"],
)
def test_T15_bad_patch_pushes_nothing(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path], patch: str
) -> None:
    """A patch that does not apply leaves no branch on origin and makes no GitHub call."""
    origin, workdir = repos
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)

    result = _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", patch)

    assert result.startswith("refused: ")
    assert _git(origin, "branch", "--list", "tripwire/*") == ""
    assert github.requests == []


@pytest.mark.parametrize(
    "bad_id",
    ["INC-1; rm -rf /", "../INC-1", "INC-0", "inc-1"],
    ids=["shell", "traversal", "zero", "lowercase"],
)
def test_T15_bad_incident_id_refused(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path], bad_id: str
) -> None:
    """An id that is not INC-<n> never reaches a git ref, a branch name or GitHub."""
    origin, workdir = repos
    github = FakeGitHub()
    _open_incident(containment, clock)

    result = _tool(containment, workdir, github).open_fix_pr(bad_id, "Stop repeated list calls", PATCH)

    assert result == f"refused: {bad_id!r} is not an incident id"
    assert _git(origin, "branch", "--list", "tripwire/*") == ""
    assert github.requests == []


def test_T15_unknown_incident_returns_service_refusal(
    containment: FakeContainment, repos: tuple[Path, Path]
) -> None:
    """An incident the service does not know is refused with the service's own reason."""
    _, workdir = repos
    github = FakeGitHub()

    result = _tool(containment, workdir, github).open_fix_pr("INC-9", "Stop repeated list calls", PATCH)

    assert result == "unknown incident INC-9"
    assert github.requests == []


def test_T15_existing_pr_is_not_reopened(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """An incident that already has a PR gets no second branch and no second PR."""
    origin, workdir = repos
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)
    containment.update(incident_id, pr_url=PR_URL)

    result = _tool(containment, workdir, github).open_fix_pr(incident_id, "Stop repeated list calls", PATCH)

    assert result == f"refused: {incident_id} already has a pull request: {PR_URL}"
    assert _git(origin, "branch", "--list", "tripwire/*") == ""
    assert github.requests == []


def test_T15_oversize_patch_refused(
    containment: FakeContainment, clock: FakeClock, repos: tuple[Path, Path]
) -> None:
    """A patch past the size limit is refused before any git call."""
    origin, workdir = repos
    github = FakeGitHub()
    incident_id = _open_incident(containment, clock)

    result = _tool(containment, workdir, github).open_fix_pr(
        incident_id, "Stop repeated list calls", PATCH + "+" + "x" * MAX_PATCH_CHARS
    )

    assert result == f"refused: patch is over {MAX_PATCH_CHARS} characters"
    assert _git(origin, "branch", "--list", "tripwire/*") == ""
    assert github.requests == []
