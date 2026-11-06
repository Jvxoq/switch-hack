"""In-memory SwitchPoster that records every alert, status update and reply."""

from __future__ import annotations

from tripwire.contracts.models import Incident


class FakeSwitch:
    def __init__(self) -> None:
        self.alerts: list[dict] = []
        self.status_updates: list[dict] = []
        self.replies: list[dict] = []
        self._threads: set[str] = set()

    def post_alert(self, incident: Incident, text: str) -> str:
        thread_ref = f"thread-{len(self._threads) + 1}"
        self._threads.add(thread_ref)
        self.alerts.append({"thread_ref": thread_ref, "incident_id": incident.id, "text": text})
        return thread_ref

    def set_status(self, thread_ref: str, text: str) -> None:
        self._require_thread(thread_ref)
        self.status_updates.append({"thread_ref": thread_ref, "text": text})

    def reply(self, thread_ref: str, text: str) -> None:
        self._require_thread(thread_ref)
        self.replies.append({"thread_ref": thread_ref, "text": text})

    def _require_thread(self, thread_ref: str) -> None:
        if thread_ref not in self._threads:
            raise ValueError(f"unknown thread_ref {thread_ref!r}")
