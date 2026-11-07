"""Fix-PR tool: open a pull request with an incident's proposed patch (A02, tasks.md section 5).

The tool branches `tripwire/INC-<n>` off the base branch, commits the patch, pushes the branch, opens a pull
request whose body links the incident, and stores the PR URL with `update_incident(pr_url=...)`. It never asks
for approval and never merges. The GitHub token comes from `GITHUB_TOKEN` and goes only into the Authorization
header.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from tripwire.contracts.models import Incident
from tripwire.contracts.ports import ContainmentRefused
from tripwire_agent.text import cap_text

logger = logging.getLogger(__name__)

INCIDENT_ID = re.compile(r"INC-[1-9][0-9]{0,8}")
GITHUB_API = "https://api.github.com"
GIT_TIMEOUT_SECONDS = 60.0
HTTP_TIMEOUT_SECONDS = 15.0
MAX_PATCH_CHARS = 200_000
MAX_TITLE_CHARS = 200
MAX_BODY_CHARS = 4_000
MAX_GIT_DETAIL_CHARS = 300
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Tripwire",
    "GIT_AUTHOR_EMAIL": "tripwire@localhost",
    "GIT_COMMITTER_NAME": "Tripwire",
    "GIT_COMMITTER_EMAIL": "tripwire@localhost",
}


class FixPrError(Exception):
    """A step of the fix-PR flow failed. The message names the step and never holds the token."""


class PullRequests(Protocol):
    def open_pull(self, *, title: str, head: str, base: str, body: str) -> str: ...


class FixPrContainment(Protocol):
    def get(self, incident_id: str) -> Incident: ...

    def update(self, incident_id: str, **fields: Any) -> Incident: ...


@dataclass(frozen=True)
class GitHubPulls:
    """The one GitHub call this tool makes: open a pull request. Merging is not here on purpose."""

    token: str = field(repr=False)
    owner: str
    repo: str
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def open_pull(self, *, title: str, head: str, base: str, body: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(
                base_url=GITHUB_API,
                headers=headers,
                timeout=HTTP_TIMEOUT_SECONDS,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"/repos/{self.owner}/{self.repo}/pulls",
                    json={"title": title, "head": head, "base": base, "body": body},
                )
        except httpx.HTTPError as exc:
            raise FixPrError(f"GitHub request failed: {type(exc).__name__}") from exc
        if response.status_code != 201:
            raise FixPrError(f"GitHub refused the pull request: HTTP {response.status_code}")
        try:
            url = response.json()["html_url"]
        except (ValueError, KeyError, TypeError) as exc:
            raise FixPrError("GitHub returned no pull request URL") from exc
        if not isinstance(url, str) or not url:
            raise FixPrError("GitHub returned no pull request URL")
        return url


class GitRepo:
    """The agent's clone. Each git call has a timeout and no shell, so model text never reaches a shell."""

    def __init__(self, path: Path, *, remote: str = "origin", base: str = "main") -> None:
        self._path = path
        self._remote = remote
        self._base = base

    @property
    def base(self) -> str:
        return self._base

    def push_patch_branch(self, branch: str, patch: str, message: str) -> None:
        """Commit `patch` on a fresh `branch` off the base and push it. Leaves no worktree behind."""
        with tempfile.TemporaryDirectory(prefix="tripwire-fix-") as scratch:
            tree = Path(scratch) / "tree"
            self._git(self._path, "fetch", "--quiet", self._remote, self._base)
            self._git(
                self._path,
                "worktree", "add", "--quiet", "-B", branch, str(tree), f"{self._remote}/{self._base}",
            )
            try:
                self._git(tree, "apply", "--index", stdin=patch.encode())
                self._git(tree, "commit", "--quiet", "-m", message)
                self._git(tree, "push", "--quiet", self._remote, f"{branch}:refs/heads/{branch}")
            finally:
                self._remove_worktree(tree)

    def _remove_worktree(self, tree: Path) -> None:
        try:
            self._git(self._path, "worktree", "remove", "--force", str(tree))
        except FixPrError as exc:
            logger.warning("could not remove fix worktree: %s", exc)

    def _git(self, cwd: Path, verb: str, *args: str, stdin: bytes | None = None) -> None:
        env = {**os.environ, **GIT_IDENTITY, "GIT_TERMINAL_PROMPT": "0"}
        try:
            result = subprocess.run(
                ["git", verb, *args],
                cwd=cwd,
                input=stdin,
                capture_output=True,
                env=env,
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FixPrError(f"git {verb} timed out") from exc
        if result.returncode != 0:
            detail = cap_text(result.stderr.decode(errors="replace").strip(), MAX_GIT_DETAIL_CHARS)
            raise FixPrError(f"git {verb} failed: {detail}")


class FixPrTool:
    """Tool body. Returns refusals as text, the way the other tools return service refusals."""

    def __init__(self, containment: FixPrContainment, git: GitRepo, pulls: PullRequests) -> None:
        self._containment = containment
        self._git = git
        self._pulls = pulls

    def open_fix_pr(self, incident_id: str, title: str, patch: str) -> str:
        """Open a pull request for the incident's patch. Containment approval is a separate step."""
        if not INCIDENT_ID.fullmatch(incident_id):
            return f"refused: {incident_id!r} is not an incident id"
        subject = " ".join(title.split())[:MAX_TITLE_CHARS]
        if not subject:
            return "refused: title is empty"
        if not patch.strip():
            return "refused: patch is empty"
        if len(patch) > MAX_PATCH_CHARS:
            return f"refused: patch is over {MAX_PATCH_CHARS} characters"
        try:
            incident = self._containment.get(incident_id)
        except ContainmentRefused as exc:
            return exc.reason
        if incident.pr_url:
            return f"refused: {incident_id} already has a pull request: {incident.pr_url}"

        branch = f"tripwire/{incident_id}"
        commit_message = f"{incident_id}: {subject}"
        body = cap_text(
            f"Opened by Tripwire for incident {incident_id}.\n\nRoot cause: {incident.root_cause or 'not recorded'}",
            MAX_BODY_CHARS,
        )
        try:
            self._git.push_patch_branch(branch, patch, commit_message)
            url = self._pulls.open_pull(title=commit_message, head=branch, base=self._git.base, body=body)
        except FixPrError as exc:
            return f"refused: {exc}"
        try:
            self._containment.update(incident_id, pr_url=url)
        except ContainmentRefused as exc:
            return f"pull request opened at {url} but not recorded: {exc.reason}"
        logger.info("opened fix PR for %s", incident_id)
        return f"PR opened: {url}"
