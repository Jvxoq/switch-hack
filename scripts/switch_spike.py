"""Switch spike for H00: post one message addressing @tripwire, then try one edit.

Path (a) (preferred): the detector posts as its own Switch agent via
  POST {SWITCH_BASE_URL}/agents/{SWITCH_AGENT_ID}/message  {room_id, content}
  with Authorization: Bearer <SWITCH_AGENT_KEY>.
Path (b) (--fallback): post as a Slack bot user via chat.postMessage.

All secrets come from env vars. Nothing is hard-coded.
Edit support: Switch 0.31 has no message-edit operation (verified 2026-11-07: ops/update_message
answers 404). The edit attempt still runs and records the HTTP status; it never fails the run.
The REST post answers {"ok": true, "event_id": ...}; event_id is the message id used for the edit probe.
The REST route ignores thread_id, so the ping is a top-level message.

Usage:
  python scripts/switch_spike.py --dry-run
  python scripts/switch_spike.py              # path (a)
  python scripts/switch_spike.py --fallback   # path (b)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PING_TEXT = "@tripwire spike ping: please reply with OK (Tripwire H00 spike)."


def _call(method: str, url: str, headers: dict, body: dict | None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"missing env var {name}")
    return value


def path_a(dry_run: bool) -> dict:
    base = os.environ.get("SWITCH_BASE_URL", "")
    agent_id = os.environ.get("SWITCH_AGENT_ID", "")
    key = os.environ.get("SWITCH_AGENT_KEY", "")
    room = os.environ.get("SWITCH_ROOM_ID", "")
    msg_url = f"{base}/agents/{agent_id}/message"
    auth = {"Authorization": f"Bearer {key}"}
    if dry_run:
        return {"path": "a", "dry_run": True, "post_url": msg_url, "room_id": room, "content": PING_TEXT}
    if not (base and agent_id and key and room):
        raise SystemExit("path a needs SWITCH_BASE_URL, SWITCH_AGENT_ID, SWITCH_AGENT_KEY, SWITCH_ROOM_ID")
    status, body = _call("POST", msg_url, auth, {"room_id": room, "content": PING_TEXT})
    result = {"path": "a", "post_status": status, "post_body": body[:500]}
    if status // 100 == 2:
        try:
            message_id = json.loads(body).get("event_id")
        except (ValueError, AttributeError):
            message_id = None
        result["event_id"] = message_id
        # Switch 0.31 has no message-edit operation: expect 404 here (verified 2026-11-07).
        if message_id:
            edit_url = f"{base}/agents/{agent_id}/ops/update_message"
            e_status, e_body = _call("POST", edit_url, auth,
                                     {"room_id": room, "message_id": message_id,
                                      "content": PING_TEXT + " (edited)"})
            result["edit_status"] = e_status
            result["edit_body"] = e_body[:300]
    return result


def path_b(dry_run: bool) -> dict:
    channel = os.environ.get("SLACK_CHANNEL", "")
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if dry_run:
        return {"path": "b", "dry_run": True, "post_url": "https://slack.com/api/chat.postMessage",
                "channel": channel, "text": PING_TEXT}
    if not (channel and token):
        raise SystemExit("path b needs SLACK_CHANNEL and SLACK_BOT_TOKEN")
    auth = {"Authorization": f"Bearer {token}"}
    status, body = _call("POST", "https://slack.com/api/chat.postMessage", auth,
                         {"channel": channel, "text": PING_TEXT})
    result = {"path": "b", "post_status": status, "post_body": body[:500]}
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = {}
    if parsed.get("ok") and parsed.get("ts"):
        # chat.update was not confirmed from docs; attempt once.
        e_status, e_body = _call("POST", "https://slack.com/api/chat.update", auth,
                                 {"channel": channel, "ts": parsed["ts"],
                                  "text": PING_TEXT + " (edited)"})
        result["edit_status"] = e_status
        result["edit_body"] = e_body[:300]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fallback", action="store_true", help="use Slack bot user (path b)")
    parser.add_argument("--dry-run", action="store_true", help="print the request without sending")
    args = parser.parse_args()
    result = path_b(args.dry_run) if args.fallback else path_a(args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
