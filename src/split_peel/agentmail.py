"""AgentMail inbox setup and read-only newsletter research ingestion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_URL = "https://api.agentmail.to/v0"
RAVEN_SOURCE = {
    "id": "men-in-blazers-raven",
    "name": "Men in Blazers — The Raven",
    "kind": "agentmail-newsletter",
    "url": "https://meninblazers.com/",
    "factCheckRequired": True,
    "role": "fact-leads",
}


class AgentMailClient:
    def __init__(self, timeout: int = 30):
        self.api_key = os.environ.get("AGENTMAIL_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError("Set AGENTMAIL_API_KEY in the environment or project .env file.")
        self.timeout = timeout

    def request(self, path: str, *, query=None, body=None) -> dict[str, Any]:
        url = API_URL + path
        if query:
            url += "?" + urlencode(query, doseq=True)
        request = Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            # Never put credentials, response bodies, or newsletter content in logs.
            raise RuntimeError(f"AgentMail request failed (HTTP {error.code}). Check key scope and permissions.") from None
        except URLError:
            raise RuntimeError("Could not reach AgentMail.") from None

    def pages(self, path: str, field: str, **query):
        seen_tokens = set()
        while True:
            payload = self.request(path, query={"limit": 100, **query})
            yield from payload.get(field, [])
            token = payload.get("next_page_token")
            if not token:
                return
            if token in seen_tokens:
                raise RuntimeError("AgentMail returned a repeated pagination token.")
            seen_tokens.add(token)
            query["page_token"] = token

    def list_inboxes(self) -> list[dict[str, Any]]:
        # Organization endpoint: no pod or inbox scope is added here.
        return list(self.pages("/inboxes", "inboxes"))

    def create_inbox(self, username: str, domain: str) -> dict[str, Any]:
        client_id = "banny-raven-" + hashlib.sha256(f"{username}@{domain}".encode()).hexdigest()[:24]
        return self.request("/inboxes", body={
            "username": username, "domain": domain,
            "display_name": "Banny Studio — The Raven", "client_id": client_id,
        })


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def fetch_raven_feed(*, timeout: int = 30, limit: int | None = 10, known_hashes: set[str] | None = None) -> dict[str, Any]:
    inbox_id = os.environ.get("AGENTMAIL_RAVEN_INBOX_ID", "").strip()
    sender = os.environ.get("AGENTMAIL_RAVEN_SENDER", "").strip().lower()
    if not inbox_id or not sender or "@" not in sender:
        raise ValueError("Set AGENTMAIL_RAVEN_INBOX_ID and AGENTMAIL_RAVEN_SENDER (exact newsletter email address).")
    if limit is not None and limit < 1:
        raise ValueError("Newsletter limit must be positive.")
    client = AgentMailClient(timeout)
    path = f"/inboxes/{quote(inbox_id, safe='')}/messages"
    casts = []
    seen = set()
    for summary in client.pages(path, "messages", **{"from": sender}):
        # API filters use substrings; enforce the actual sender locally as well.
        if parseaddr(str(summary.get("from", "")))[1].lower() != sender:
            continue
        # The flagship is now labeled Men in Blazers; issues need not say Raven.
        # Onboarding messages contain no editorial research material.
        if re.search(r"^welcome to men in blazers\b", str(summary.get("subject", "")).strip(), re.I):
            continue
        if set(summary.get("labels") or []) & {"spam", "blocked", "unauthenticated", "trash", "sent", "draft"}:
            continue
        message_id = summary["message_id"]
        message_hash = "agentmail:" + hashlib.sha256(f"{inbox_id}:{message_id}".encode()).hexdigest()
        if message_hash in (known_hashes or set()):
            continue
        if message_id in seen:
            continue
        seen.add(message_id)
        message = client.request(f"{path}/{quote(message_id, safe='')}")
        body = message.get("extracted_text") or message.get("text") or ""
        if not body:
            parser = _PlainText()
            parser.feed(message.get("extracted_html") or message.get("html") or "")
            body = "".join(parser.parts).strip()
        if not body.strip():
            continue
        casts.append({
            "hash": message_hash,
            "text": f"{message.get('subject') or summary.get('subject', '')}\n\n{body.strip()}",
            "timestamp": message.get("timestamp") or summary.get("timestamp", ""),
            "author": {"username": "men-in-blazers-raven"},
            "newsletter": {"messageId": message_id, "inboxId": inbox_id, "sender": sender},
            "researchSourceId": RAVEN_SOURCE["id"],
            "researchSource": RAVEN_SOURCE.copy(),
            "factCheckRequired": True,
        })
        if limit is not None and len(casts) >= limit:
            break
    return {"casts": casts}


def main(argv=None) -> int:
    from split_peel.config import load_dotenv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-inboxes")
    setup = commands.add_parser("setup-inbox", help="List all inboxes, then create the newsletter inbox.")
    setup.add_argument("--username", required=True)
    setup.add_argument("--domain", default="agentmail.to")
    fetch = commands.add_parser("fetch-raven")
    fetch.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    load_dotenv(args.env_file)
    try:
        if args.command == "fetch-raven":
            from split_peel.feed import write_json
            write_json(args.out, fetch_raven_feed())
            print(f"wrote {args.out}")
            return 0
        client = AgentMailClient()
        inboxes = client.list_inboxes()
        print(json.dumps({"inboxes": inboxes}, indent=2), flush=True)
        if args.command == "setup-inbox":
            print(json.dumps({"newsletterInbox": client.create_inbox(args.username, args.domain)}, indent=2))
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
