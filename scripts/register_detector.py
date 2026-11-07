"""Register the Tripwire detector as a Switch agent and store its credentials in .env (H-PREP).

Calls `POST {SWITCH_BASE_URL}/agents` with the registration key from the Gateway (API Keys page).
Switch returns `{id, api_key}` once. This script writes `SWITCH_AGENT_ID` and `SWITCH_TOKEN` (the agent key,
which the detector reads) into the env file, and prints only the agent id. The key never reaches the terminal.

Environment (never a flag, so the key stays out of shell history):
  SWITCH_BASE_URL          e.g. http://127.0.0.1:8000
  SWITCH_REGISTRATION_KEY  the registration key from Gateway > API Keys > Create Registration Key

Usage:
  SWITCH_BASE_URL=... SWITCH_REGISTRATION_KEY=... python scripts/register_detector.py
  ... --dry-run          print the request without sending it
  ... --overwrite        rotate the key when the name is already registered (409 otherwise)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx

NAME = "tripwire-detector"
CONNECTOR_TYPE = "tripwire-detector-py"
DESCRIPTION = "Tripwire detector: watches Langfuse traces and posts incident alerts to the room."
TIMEOUT_SECONDS = 10.0


class RegisterError(RuntimeError):
    """Switch refused the registration, or the inputs are missing."""


def registration_body(name: str = NAME, overwrite: bool = False) -> dict[str, Any]:
    """The POST /agents body. `session_passive`: the detector only posts, and nothing pushes to it."""
    body: dict[str, Any] = {
        "name": name,
        "description": DESCRIPTION,
        "connector_type": CONNECTOR_TYPE,
        "integration_profile": {
            "connection_model": "session_passive",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }
    if overwrite:
        body["overwrite"] = True
    return body


def register(
    base_url: str,
    registration_key: str,
    *,
    name: str = NAME,
    overwrite: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str]:
    """Register the agent and return `{id, api_key}`. Raises RegisterError with Switch's reason on failure."""
    with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS) as client:
        response = client.post(
            f"{base_url.rstrip('/')}/agents",
            json=registration_body(name, overwrite),
            headers={"Authorization": f"Bearer {registration_key}"},
        )
    if response.status_code == 409:
        raise RegisterError(f"'{name}' is already registered. Re-run with --overwrite to rotate its key.")
    if response.status_code >= 400:
        raise RegisterError(f"Switch refused the registration: HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if not data.get("id") or not data.get("api_key"):
        raise RegisterError("Switch answered without an id and api_key")
    return {"id": str(data["id"]), "api_key": str(data["api_key"])}


def set_env_values(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=VALUE lines in an env file, replacing existing ones and appending the rest. Mode 600."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0]
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env", help="env file to update (default .env)")
    parser.add_argument("--dry-run", action="store_true", help="print the request without sending it")
    parser.add_argument("--overwrite", action="store_true", help="rotate the key if the name is registered")
    args = parser.parse_args(argv)
    env = dict(os.environ if environ is None else environ)

    base_url = env.get("SWITCH_BASE_URL", "")
    key = env.get("SWITCH_REGISTRATION_KEY", "")
    if args.dry_run:
        print(f"POST {base_url.rstrip('/')}/agents")
        print(registration_body(overwrite=args.overwrite))
        return 0
    if not base_url or not key:
        print("error: set SWITCH_BASE_URL and SWITCH_REGISTRATION_KEY", file=sys.stderr)
        return 2
    try:
        agent = register(base_url, key, overwrite=args.overwrite)
    except RegisterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    set_env_values(Path(args.env_file), {"SWITCH_AGENT_ID": agent["id"], "SWITCH_TOKEN": agent["api_key"]})
    print(f"registered {NAME} as agent id {agent['id']}")
    print(f"SWITCH_AGENT_ID and SWITCH_TOKEN written to {args.env_file} (the key is not printed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
