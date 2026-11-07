"""HTTP `ContainmentClient`: one method per route of the containment service (section 3 of tasks.md).

Refusals (404/409/422 with a `reason`) raise `ContainmentRefused(reason)`. Any other error status
or a network failure propagates as the httpx exception.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from tripwire.contracts.models import Incident, incident_from_dict
from tripwire.contracts.ports import ContainmentRefused

REFUSAL_STATUSES = frozenset({404, 409, 422})
DEFAULT_TIMEOUT_SECONDS = 5.0


class ContainmentHTTPClient:
    """Implements `ContainmentClient` over HTTP.

    Pass `http` to reuse a client (tests pass a `TestClient`); otherwise one is built against `base_url`
    with an explicit timeout.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8700",
        *,
        http: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._http = http if http is not None else httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    # ---- incidents -------------------------------------------------------

    def open_incident(self, rule: str, route: str, opened_at: datetime) -> Incident:
        body = {"rule": rule, "route": route, "opened_at": opened_at.isoformat()}
        return self._incident(self._send("POST", "/incidents", json=body))

    def get(self, incident_id: str) -> Incident:
        return self._incident(self._send("GET", f"/incidents/{incident_id}"))

    def list(self, open_only: bool = True) -> list[Incident]:
        data = self._send("GET", "/incidents", params={"open_only": "true" if open_only else "false"})
        return [incident_from_dict(item) for item in data]

    def update(self, incident_id: str, **fields: Any) -> Incident:
        body = {name: value.isoformat() if isinstance(value, datetime) else value for name, value in fields.items()}
        return self._incident(self._send("PATCH", f"/incidents/{incident_id}", json=body))

    def reopen(self, incident_id: str) -> Incident:
        return self._incident(self._send("POST", f"/incidents/{incident_id}/reopen", json={}))

    # ---- actions ---------------------------------------------------------

    def apply(
        self,
        incident_id: str,
        action: str,
        source: str,
        approver: str | None,
        spend_usd: float,
    ) -> dict[str, Any]:
        body = {
            "incident_id": incident_id,
            "action": action,
            "source": source,
            "approver": approver,
            "spend_usd": spend_usd,
        }
        return self._send("POST", "/actions", json=body)

    def revert(self, incident_id: str, by: str) -> dict[str, Any]:
        return self._send("POST", "/revert", json={"incident_id": incident_id, "by": by})

    def flags(self) -> dict[str, Any]:
        return self._send("GET", "/flags")

    # ---- helpers ---------------------------------------------------------

    def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._http.request(method, path, **kwargs)
        if response.status_code in REFUSAL_STATUSES:
            raise ContainmentRefused(_reason(response))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _incident(data: dict[str, Any]) -> Incident:
        return incident_from_dict(data)


def _reason(response: httpx.Response) -> str:
    try:
        reason = response.json().get("reason")
    except ValueError:
        reason = None
    return str(reason) if reason else f"HTTP {response.status_code}"
