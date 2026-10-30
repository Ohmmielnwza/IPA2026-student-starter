"""Register or update the Webex messages/created webhooks for both rooms.

Usage:
  WEBEX_BOT_TOKEN=... python scripts/register_webhook.py https://<tunnel-host>

Rooms are looked up by title among the rooms the bot belongs to.
"""

import os
import sys

import requests

API = "https://webexapis.com/v1"
ROOMS = ("IPA2026", "IPA2026 Exam Room")


def main():
    base = sys.argv[1].rstrip("/")
    target = f"{base}/webhook"
    headers = {"Authorization": f"Bearer {os.environ['WEBEX_BOT_TOKEN']}"}

    def call(method, path, **kw):
        r = requests.request(method, API + path, headers=headers, timeout=10, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    rooms = {r["title"]: r["id"] for r in call("GET", "/rooms")["items"]}
    hooks = call("GET", "/webhooks")["items"]
    for title in ROOMS:
        room_id = rooms.get(title)
        if not room_id:
            print(f"SKIP: bot is not a member of '{title}'")
            continue
        filt = f"roomId={room_id}"
        body = {
            "name": f"ipa2026 {title}",
            "targetUrl": target,
            "resource": "messages",
            "event": "created",
            "filter": filt,
        }
        existing = next((h for h in hooks if h.get("filter") == filt), None)
        if existing:
            call("PUT", f"/webhooks/{existing['id']}", json={
                k: body[k] for k in ("name", "targetUrl")})
            print(f"updated '{title}'")
        else:
            call("POST", "/webhooks", json=body)
            print(f"created '{title}'")


if __name__ == "__main__":
    main()
