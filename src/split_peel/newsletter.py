"""Final Whistle Match Reports: shared research, deterministic assembly, reviewed delivery."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from split_peel.artifacts import atomic_json, digest, identity, job_lock, read_json, require_approval
from split_peel.publishing import publish_once
from split_peel.newsletter_design import render_email

APP = "https://final-whistle.app"
FPL = "https://fantasy.premierleague.com/api"


def now():
    return datetime.now(timezone.utc).isoformat()


def get_json(url, token=None):
    headers = {"User-Agent": "final-whistle-newsletter/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def subscribers(app=APP):
    token = os.environ.get("FINAL_WHISTLE_ADMIN_TOKEN", "")
    if not token:
        raise ValueError("Set FINAL_WHISTLE_ADMIN_TOKEN for the subscriber export")
    parsed = urlparse(app)
    if parsed.scheme != "https" or parsed.hostname != "final-whistle.app":
        raise ValueError("Subscriber export must use https://final-whistle.app")
    return get_json(app.rstrip("/") + "/api/admin/export", token)["subscribers"]


def memberships(row):
    # The extended app export contains every selected league, not just the primary.
    return sorted({int(x["league_id"]) for x in row.get("leagues", [])} |
                  ({int(row["league_id"])} if row.get("league_id") else set()))


def active(rows):
    return [r for r in rows if r.get("subscribed") in (1, True)]


def public_text(value):
    text = str(value).strip()
    if not text or re.search(r"/Users/|/private/|messageId|source-handoff|\.sqlite|\.json\b|\.md\b", text, re.I):
        raise ValueError("Public copy is empty or contains internal provenance")
    return text


def validate_exhaust(data):
    if data.get("version") != 1 or not data.get("season") or not isinstance(data.get("gameweek"), int):
        raise ValueError("Exhaust requires version=1, season and integer gameweek")
    seen = set()
    for fact in data.get("facts", []):
        if not fact.get("id") or fact["id"] in seen:
            raise ValueError("Fact IDs must be present and unique")
        seen.add(fact["id"])
        public_text(fact["text"])
        if fact.get("scope") not in ("global", "league"):
            raise ValueError("Each fact requires global or league scope")
        if fact["scope"] == "league" and not fact.get("league_id"):
            raise ValueError("League facts require league_id")
        if not fact.get("verified") or not str(fact.get("source", "")).startswith("https://"):
            raise ValueError("Facts require verified=true and a primary source URL")
        start = datetime.fromisoformat(fact["observed_at"])
        end = datetime.fromisoformat(fact["expires_at"])
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("Fact timestamps must be timezone-aware and expiry after observation")
    return data


def init_exhaust(season, gameweek, out):
    value = {"version": 1, "season": season, "gameweek": gameweek, "created_at": now(),
             "facts": [], "ideas": [], "callout_candidates": []}
    if out.exists():
        raise ValueError("Exhaust already exists; edit it rather than overwriting research")
    atomic_json(out, value)
    return {"out": str(out)}


def snapshot(rows, fetch=get_json):
    """Fetch shared metadata once; only registered managers' squads, with full standings pagination."""
    rows = active(rows)
    if not any(r.get("fpl_entry_id") for r in rows):
        return {"version": 1, "season": None, "gameweek": None, "observed_at": now(), "final": False,
                "managers": {}, "leagues": {}, "warnings": [], "episode_callout_eligible_leagues": []}
    boot = fetch(FPL + "/bootstrap-static/")
    event = next((e for e in boot["events"] if e.get("is_current")), None)
    if not event:
        raise ValueError("No current FPL gameweek; do not infer an unpublished squad")
    first = boot["events"][0]["deadline_time"][:4]
    result = {"version": 1, "season": first, "gameweek": event["id"], "observed_at": now(),
              "final": bool(event.get("data_checked")), "managers": {}, "leagues": {}, "warnings": []}
    players = {p["id"]: p for p in boot["elements"]}
    for entry_id in sorted({int(r["fpl_entry_id"]) for r in rows if r.get("fpl_entry_id")}):
        try:
            entry = fetch(f"{FPL}/entry/{entry_id}/")
            picks = fetch(f"{FPL}/entry/{entry_id}/event/{event['id']}/picks/")
            leagues = [l["id"] for l in entry["leagues"]["classic"] if
                       l.get("league_type") != "a" and l.get("admin_entry") is not None and
                       not re.fullmatch(r"Overall|Gameweek \d+|Second Chance", l["name"])]
            result["managers"][str(entry_id)] = {
                "name": entry["name"], "league_ids": leagues,
                "player_ids": [p["element"] for p in picks["picks"]],
                "source": f"{FPL}/entry/{entry_id}/event/{event['id']}/picks/",
                "squad_notes": [f"{players[p['element']]['web_name']}: {players[p['element']]['news']}"
                                for p in picks["picks"] if players[p["element"]].get("news")],
            }
        except Exception as error:
            result["warnings"].append({"entry_id": entry_id, "status": "unavailable", "error_type": type(error).__name__})
    for league_id in sorted({l for r in rows for l in memberships(r)}):
        try:
            table, page = [], 1
            while True:
                if page > 100:
                    raise ValueError("Standings pagination budget exceeded")
                data = fetch(f"{FPL}/leagues-classic/{league_id}/standings/?page_standings={page}")
                table.extend(data["standings"]["results"])
                if not data["standings"].get("has_next"):
                    break
                page += 1
            result["leagues"][str(league_id)] = {"name": data["league"]["name"], "standings": table}
        except Exception as error:
            result["warnings"].append({"league_id": league_id, "status": "unavailable", "error_type": type(error).__name__})
    counts = {}
    for row in rows:
        manager = result["managers"].get(str(row.get("fpl_entry_id")), {})
        for league_id in set(memberships(row)).intersection(manager.get("league_ids", [])):
            counts.setdefault(league_id, set()).add(row["fpl_entry_id"])
    result["episode_callout_eligible_leagues"] = [league_id for league_id, entries in counts.items() if len(entries) >= 3]
    return result


def youtube_url(receipt):
    value = receipt.get("result", receipt)
    if receipt.get("status") != "complete" or value.get("dry_run"):
        raise ValueError("A completed YouTube publication receipt is required")
    status = (value.get("response") or {}).get("status", {})
    if status.get("privacyStatus") != "public" or status.get("publishAt"):
        raise ValueError("Newsletter requires a public, unscheduled YouTube release")
    video_id = value.get("video_id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(video_id)):
        raise ValueError("YouTube receipt has no valid video ID")
    if value.get("response", {}).get("id", video_id) != video_id:
        raise ValueError("YouTube receipt video ID disagrees with upload response")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def assemble(brief, exhaust, rows, evidence, youtube, out, tracking=True, instructions=None):
    validate_exhaust(exhaust)
    watch, episode = youtube_url(youtube)
    title, hook = public_text(brief["title"]), public_text(brief["hook"])
    if instructions and brief.get("editorial_instructions_sha256") != digest(instructions):
        raise ValueError("Apply the newsletter instructions to the public brief and record editorial_instructions_sha256 before preparing")
    editorial_sections = [{"heading": public_text(section["heading"]), "paragraphs": [public_text(p) for p in section["paragraphs"]]} for section in brief.get("sections", [])]
    timestamp = datetime.now(timezone.utc)
    facts = [f for f in exhaust.get("facts", []) if
             datetime.fromisoformat(f["observed_at"]) <= timestamp < datetime.fromisoformat(f["expires_at"])]
    usable = evidence and str(evidence.get("season")) == str(exhaust["season"]) and evidence.get("gameweek") == exhaust["gameweek"]
    if usable:
        age = (timestamp - datetime.fromisoformat(evidence["observed_at"])).total_seconds()
        usable = 0 <= age <= 4 * 86400
    messages, review = [], []
    addresses = {}
    for row in active(rows):
        email = str(row.get("email") or "").strip().lower()
        if email:
            addresses.setdefault(email, []).append(row)
    for row in active(rows):
        email = str(row.get("email") or "").strip().lower()
        if not email:
            review.append({"subscriber_id": row["id"], "reason": "social-only; no email; no automatic DM"})
            continue
        if len(addresses[email]) != 1:
            review.append({"subscriber_id": row["id"], "reason": "duplicate email identity; resolve in app"})
            continue
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not row.get("manage_token"):
            review.append({"subscriber_id": row["id"], "reason": "invalid email or missing unsubscribe token"})
            continue
        shared_facts, league_sections = [], []
        link_token = secrets.token_urlsafe(32)
        tracked_watch = f"{APP}/n/{link_token}/youtube" if tracking else watch
        tracked_x = f"{APP}/n/{link_token}/x" if tracking else "https://x.com/closertoyes"
        lines = [hook, "", f"Watch Split & Peel: {tracked_watch}", ""]
        for section in editorial_sections:
            lines.extend([section["heading"], *section["paragraphs"], ""])
        manager = (evidence or {}).get("managers", {}).get(str(row.get("fpl_entry_id")), {}) if usable else {}
        player_ids = set(manager.get("player_ids", []))
        for fact in facts:
            if fact["scope"] == "global" and (not fact.get("player_ids") or player_ids.intersection(fact["player_ids"])):
                lines.append(fact["text"])
                shared_facts.append(fact["text"])
        for league_id in memberships(row):
            if not usable or league_id not in manager.get("league_ids", []):
                review.append({"subscriber_id": row["id"], "league_id": league_id, "reason": "membership or snapshot unavailable; shared edition only"})
                continue
            league = evidence["leagues"].get(str(league_id))
            if not league:
                continue
            lines.extend(["", public_text(league["name"])])
            own = next((r for r in league["standings"] if r["entry"] == row["fpl_entry_id"]), None)
            if own:
                lines.append(f"Your position: {own['rank']}. GW points: {own['event_total']}. Total: {own['total']}.")
            lines.append(f"GW{evidence['gameweek']} snapshot: {evidence['observed_at']} ({'final' if evidence['final'] else 'provisional'}).")
            lines.extend(f["text"] for f in facts if f["scope"] == "league" and f["league_id"] == league_id)
            lines.append(f"League report: {APP}/report/{league_id}")
            league_sections.append({"name": public_text(league["name"]), "own": own,
                                    "notes": [f["text"] for f in facts if f["scope"] == "league" and f["league_id"] == league_id],
                                    "url": f"{APP}/report/{league_id}"})
        if manager.get("squad_notes"):
            lines.extend(["", "Your last published squad — FPL notes as of " + evidence["observed_at"] + ":", *map(public_text, manager["squad_notes"])])
        unsub = APP + "/api/unsubscribe?" + urlencode({"token": row["manage_token"]})
        lines.extend(["", "Follow Split: " + tracked_x, "", "Unsubscribe: " + unsub])
        text = "\n".join(lines)
        messages.append({"subscriber_id": row["id"], "entry_id": row.get("fpl_entry_id"), "league_ids": memberships(row),
                         "link_token": link_token, "to": email, "subject": "Final Whistle: " + title, "text": text,
                         "html": render_email(title=title, hook=hook, watch=tracked_watch, unsubscribe=unsub,
                                              thumbnail=f"https://i.ytimg.com/vi/{episode}/hqdefault.jpg",
                                              sections=editorial_sections, x_url=tracked_x,
                                              facts=shared_facts, leagues=league_sections,
                                              squad_notes=list(map(public_text, manager.get("squad_notes", []))),
                                              snapshot_label=(f"GW{evidence['gameweek']} · {evidence['observed_at']} · " + ('final' if evidence['final'] else 'provisional')) if usable else '')})
    plan = {"version": 1, "episode_id": episode, "watch_url": watch, "created_at": now(),
            "title": title, "click_tracking": tracking, "editorial_instructions_sha256": digest(instructions) if instructions else None,
            "inbox": "finalwhistle@agentmail.to", "messages": messages, "needs_review": review}
    atomic_json(out, plan)
    html_dir = out.parent / (out.stem + "-previews")
    html_dir.mkdir(parents=True, exist_ok=True)
    for message in messages:
        (html_dir / (str(message["subscriber_id"]) + ".html")).write_text(message["html"], encoding="utf-8")
    preview = out.with_suffix(".preview.txt")
    preview.write_text("\n\n---\n\n".join(m["subject"] + "\n\n" + m["text"] for m in messages), encoding="utf-8")
    return {"plan": str(out), "preview": str(preview), "emails": len(messages), "needs_review": len(review), "html_previews": str(html_dir)}


def deliver(plan_path, state, approval=None, send=False, load_subscribers=subscribers, provider=None):
    plan = read_json(plan_path)
    if not send:
        return {"dry_run": True, "emails": len(plan["messages"]), "episode_id": plan["episode_id"]}
    if not approval:
        raise ValueError("Live delivery requires approval of the exact newsletter plan")
    require_approval(plan_path, approval, "publish")
    if plan.get("version") != 1 or plan.get("inbox") != "finalwhistle@agentmail.to":
        raise ValueError("Unsupported newsletter plan or sender")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(plan["created_at"])).total_seconds()
    if not 0 <= age < 86400:
        raise ValueError("Newsletter plan expired; rebuild and review fresh copy")
    if provider is None:
        from split_peel.agentmail import AgentMailClient
        provider = AgentMailClient()
    from split_peel.newsletter_metrics import register_issue
    register_issue(plan)
    sent, skipped = 0, 0
    for message in plan["messages"]:
        # Fetch authoritative state immediately before EACH delivery. Never use the preparation export.
        rows = active(load_subscribers())
        current = next((r for r in rows if r["id"] == message["subscriber_id"]), None)
        if (not current or str(current.get("email") or "").lower() != message["to"] or
                current.get("fpl_entry_id") != message["entry_id"] or memberships(current) != message["league_ids"]):
            skipped += 1
            continue
        receipt = state / identity({"episode": plan["episode_id"], "email": message["to"]}) / "delivery.json"
        request = {"inbox": plan["inbox"], "message": message}
        def submit():
            response = provider.request(f"/inboxes/{quote(plan['inbox'], safe='')}/messages/send", body={
                "to": message["to"], "subject": message["subject"], "text": message["text"], "html": message["html"]})
            if not response.get("message_id"):
                raise ValueError("AgentMail returned no message ID; reconcile before retrying")
            return {"message_id": response["message_id"], "accepted_at": now()}
        try:
            publish_once(receipt, request, submit)
        finally:
            from split_peel.newsletter_metrics import report_issue
            report_issue(plan, state)
        sent += 1
    from split_peel.newsletter_metrics import report_issue
    result = report_issue(plan, state)
    result["last_run"] = {"accepted_or_previously_accepted": sent, "suppressed_or_changed": skipped}
    atomic_json(state / "issues" / (plan["episode_id"] + ".json"), result)
    return result["last_run"]



def reconcile(receipt, message_id, provider=None):
    """Resolve an unknown submission only against a matching actual AgentMail message."""
    if provider is None:
        from split_peel.agentmail import AgentMailClient
        provider = AgentMailClient()
    with job_lock(receipt.with_suffix(receipt.suffix + ".lock")):
        record = read_json(receipt)
        if record.get("status") not in ("unknown", "submitting"):
            raise ValueError("Only unknown or submitting deliveries need reconciliation")
        request = record["request"]
        remote = provider.request(f"/inboxes/{quote(request['inbox'], safe='')}/messages/{quote(message_id, safe='')}")
        expected = request["message"]
        recipients = remote.get("to") or []
        if isinstance(recipients, str):
            recipients = [recipients]
        from email.utils import parseaddr
        addresses = {parseaddr(str(address))[1].lower() for address in recipients}
        if (remote.get("message_id") != message_id or expected["to"] not in addresses or
                remote.get("subject") != expected["subject"] or remote.get("text") != expected["text"]):
            raise ValueError("AgentMail message does not match the unknown delivery")
        result = {"message_id": message_id, "reconciled_at": now()}
        atomic_json(receipt, {**record, "status": "complete", "result": result})
        return {"reconciled": True, "message_id": message_id}


def add_commands(subparsers):
    p = subparsers.add_parser("newsletter", help=__doc__)
    commands = p.add_subparsers(dest="newsletter_action", required=True)
    demo = commands.add_parser("examples")
    demo.add_argument("--out", type=Path, default=Path("runs/newsletter-examples"))
    test = commands.add_parser("test-send")
    test.add_argument("--to", required=True)
    test.add_argument("--example", default="all")
    test.add_argument("--send", action="store_true")
    test.add_argument("--state-dir", type=Path, default=Path("memory/newsletter-test-deliveries"))
    approve = commands.add_parser("approve")
    approve.add_argument("--plan", type=Path, required=True)
    approve.add_argument("--out", type=Path, required=True)
    init = commands.add_parser("init-exhaust")
    init.add_argument("--season", required=True)
    init.add_argument("--gameweek", type=int, required=True)
    init.add_argument("--out", type=Path, required=True)
    validate = commands.add_parser("validate-exhaust")
    validate.add_argument("--exhaust", type=Path, required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--subscribers", type=Path, help="Offline export; otherwise read the app")
    snap.add_argument("--out", type=Path, required=True)
    snap.add_argument("--refresh", action="store_true", help="Refresh before the normal 84-hour reuse limit")
    prep = commands.add_parser("prepare")
    for flag in ("brief", "exhaust", "youtube-receipt", "out"):
        prep.add_argument("--" + flag, type=Path, required=True)
    prep.add_argument("--subscribers", type=Path)
    prep.add_argument("--snapshot", type=Path)
    prep.add_argument("--instructions", type=Path)
    prep.add_argument("--no-click-tracking", action="store_true")
    stats = commands.add_parser("stats")
    stats.add_argument("--plan", type=Path, required=True)
    stats.add_argument("--state-dir", type=Path, default=Path("memory/newsletter-deliveries"))
    stats.add_argument("--out", type=Path)
    stats.add_argument("--refresh", action="store_true")
    rec = commands.add_parser("reconcile")
    rec.add_argument("--receipt", type=Path, required=True)
    rec.add_argument("--message-id", required=True)
    send = commands.add_parser("deliver")
    send.add_argument("--plan", type=Path, required=True)
    send.add_argument("--state-dir", type=Path, default=Path("memory/newsletter-deliveries"))
    send.add_argument("--approval", type=Path)
    send.add_argument("--send", action="store_true")


def run_command(args):
    action = args.newsletter_action
    if action == "examples":
        from split_peel.newsletter_design import write_examples
        result = write_examples(args.out)
    elif action == "test-send":
        result = test_send(args.to, args.example, args.state_dir, args.send)
    elif action == "approve":
        from split_peel.artifacts import approve_artifact
        result = approve_artifact(args.plan, args.out, "publish")
    elif action == "init-exhaust":
        result = init_exhaust(args.season, args.gameweek, args.out)
    elif action == "validate-exhaust":
        validate_exhaust(read_json(args.exhaust))
        result = {"valid": True}
    elif action in ("snapshot", "prepare"):
        rows = read_json(args.subscribers)["subscribers"] if args.subscribers else subscribers()
        if action == "snapshot":
            cached = read_json(args.out) if args.out.exists() else None
            signature = identity([{ "id": r["id"], "entry": r.get("fpl_entry_id"), "leagues": memberships(r)} for r in rows])
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached["observed_at"])).total_seconds() if cached else float("inf")
            reuse = cached and not args.refresh and 0 <= age < 84 * 3600 and cached.get("subscriber_signature") == signature
            if not reuse:
                value = snapshot(rows)
                value["subscriber_signature"] = signature
                atomic_json(args.out, value)
            result = {"snapshot": str(args.out), "reused": bool(reuse)}
        else:
            result = assemble(read_json(args.brief), read_json(args.exhaust), rows,
                              read_json(args.snapshot) if args.snapshot else None, read_json(args.youtube_receipt), args.out,
                              tracking=not args.no_click_tracking, instructions=args.instructions)
    elif action == "stats":
        from split_peel.newsletter_metrics import report_issue
        result = report_issue(read_json(args.plan), args.state_dir, args.out, args.refresh)
    elif action == "reconcile":
        result = reconcile(args.receipt, args.message_id)
    else:
        result = deliver(args.plan, args.state_dir, args.approval, args.send)
    print(json.dumps(result, indent=2))
    return 0


def test_send(recipient, selection, state, send=False, provider=None):
    """Send fictional previews to ONE explicit address, without loading subscribers."""
    from split_peel.newsletter_design import examples
    from html import unescape
    recipient = recipient.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient):
        raise ValueError("Provide one valid test email address")
    choices = examples()
    if selection != "all":
        if selection not in choices:
            raise ValueError("Unknown example; choose all or " + ", ".join(choices))
        choices = {selection: choices[selection]}
    if not send:
        return {"dry_run": True, "to": recipient, "examples": list(choices)}
    if provider is None:
        from split_peel.agentmail import AgentMailClient
        provider = AgentMailClient()
    for name, data in choices.items():
        html = render_email(**data)
        body = {"to": recipient, "subject": "[TEST] Final Whistle — " + data["title"], "html": html,
                "text": unescape(re.sub(r"<[^>]+>", " ", html))}
        request = {"kind": "newsletter-design-test", "body": body}
        receipt = state / identity({"to": recipient, "example": name, "html": html}) / "delivery.json"
        def submit():
            response = provider.request("/inboxes/finalwhistle%40agentmail.to/messages/send", body=body)
            if not response.get("message_id"):
                raise ValueError("No AgentMail message ID; inspect before retrying")
            return {"message_id": response["message_id"], "accepted_at": now()}
        publish_once(receipt, request, submit)
    return {"accepted_or_previously_accepted": len(choices), "to": recipient}


def main(argv=None):
    import sys
    from split_peel.config import load_dotenv
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    add_commands(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(["newsletter", *(sys.argv[1:] if argv is None else argv)])
    try:
        return run_command(args)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
