from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from split_peel.artifacts import approve_artifact, atomic_json, read_json
from split_peel.newsletter import assemble, deliver, snapshot, validate_exhaust, youtube_url


@pytest.fixture
def inputs():
    clock = datetime.now(timezone.utc)
    facts = [{"id": "global", "text": "A shared football fact.", "scope": "global", "verified": True,
              "source": "https://fantasy.premierleague.com/", "observed_at": (clock-timedelta(hours=1)).isoformat(),
              "expires_at": (clock+timedelta(hours=1)).isoformat()}]
    facts += [{**facts[0], "id": "local", "text": "Farcaster league only.", "scope": "league", "league_id": 10}]
    rows = [{"id": 1, "email": "fan@example.com", "subscribed": 1, "fpl_entry_id": 100,
             "league_id": 10, "leagues": [{"league_id": 10}, {"league_id": 20}], "manage_token": "secret-token"}]
    evidence = {"season": "2026", "gameweek": 8, "observed_at": clock.isoformat(), "final": False,
                "managers": {"100": {"league_ids": [10, 20], "player_ids": [1], "squad_notes": []}},
                "leagues": {str(i): {"name": f"League {i}", "standings": [{"entry": 100, "rank": 25, "event_total": 40, "total": 500}]} for i in (10,20)}}
    receipt = {"status": "complete", "video_id": "abcdefghijk", "response": {"status": {"privacyStatus": "public"}}}
    return {"tracking": False, "brief": {"title": "The show", "hook": "A reason to watch."},
            "exhaust": {"version": 1, "season": "2026", "gameweek": 8, "facts": facts},
            "rows": rows, "evidence": evidence, "youtube": receipt}


def prepare(tmp_path, inputs):
    path = tmp_path / "plan.json"
    assemble(**inputs, out=path)
    return path


def test_one_combined_email_and_own_row_beyond_top_twenty(tmp_path, inputs):
    plan = read_json(prepare(tmp_path, inputs))
    assert len(plan["messages"]) == 1
    assert "/report/" not in plan["messages"][0]["text"]
    assert "/report/" not in plan["messages"][0]["html"]
    text = plan["messages"][0]["text"]
    assert "League 10" in text and "League 20" in text and "position: 25" in text
    assert "provisional" in text and "closertoyes" in text and "Unsubscribe:" in text
    assert text.index("Watch Split") < text.index("League 10")


def test_league_facts_never_cross_leagues(tmp_path, inputs):
    inputs["rows"][0]["league_id"] = 20
    inputs["rows"][0]["leagues"] = [{"league_id": 20}]
    assert "Farcaster league only" not in read_json(prepare(tmp_path, inputs))["messages"][0]["text"]


def test_stale_snapshot_falls_back_to_shared(tmp_path, inputs):
    inputs["evidence"]["observed_at"] = (datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
    plan = read_json(prepare(tmp_path, inputs))
    assert "position:" not in plan["messages"][0]["text"]
    assert plan["needs_review"]


def test_expired_facts_excluded(tmp_path, inputs):
    inputs["exhaust"]["facts"][0]["expires_at"] = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    assert "shared football fact" not in read_json(prepare(tmp_path, inputs))["messages"][0]["text"]


@pytest.mark.parametrize("privacy", ["private", "unlisted"])
def test_private_youtube_blocked(inputs, privacy):
    inputs["youtube"]["response"]["status"]["privacyStatus"] = privacy
    with pytest.raises(ValueError):
        youtube_url(inputs["youtube"])


def test_internal_prose_rejected(inputs):
    inputs["exhaust"]["facts"][0]["text"] = "Read /Users/private/research.json"
    with pytest.raises(ValueError):
        validate_exhaust(inputs["exhaust"])


def test_social_only_and_duplicate_email_go_to_review(tmp_path, inputs):
    inputs["rows"] += [{**inputs["rows"][0], "id": 2}, {**inputs["rows"][0], "id": 3, "email": None}]
    plan = read_json(prepare(tmp_path, inputs))
    assert not plan["messages"] and len(plan["needs_review"]) == 3


def test_dry_run_never_calls_provider_or_subscriber_api(tmp_path, inputs):
    def fail():
        pytest.fail("Dry run must be offline")
    assert deliver(prepare(tmp_path, inputs), tmp_path / "state", load_subscribers=fail)["dry_run"]


def test_live_requires_exact_approval(tmp_path, inputs):
    path = prepare(tmp_path, inputs)
    with pytest.raises(ValueError):
        deliver(path, tmp_path / "state", send=True)


def test_duplicate_runs_and_unsubscribe(tmp_path, inputs):
    path = prepare(tmp_path, inputs)
    approval = tmp_path / "approved.json"
    approve_artifact(path, approval, "publish")
    calls = []
    provider = SimpleNamespace(request=lambda *a, **kw: calls.append(kw) or {"message_id": "accepted"})
    for _ in range(2):
        deliver(path, tmp_path / "state", approval, True, lambda: inputs["rows"], provider)
    assert len(calls) == 1
    inputs["rows"][0]["subscribed"] = 0
    result = deliver(path, tmp_path / "state", approval, True, lambda: inputs["rows"], provider)
    assert result["suppressed_or_changed"] == 1


def test_unknown_outcome_never_retries(tmp_path, inputs):
    path = prepare(tmp_path, inputs)
    approval = tmp_path / "approved.json"
    approve_artifact(path, approval, "publish")
    calls = []
    def submit(*a, **kw):
        calls.append(1)
        raise TimeoutError()
    for error in (TimeoutError, ValueError):
        with pytest.raises(error):
            deliver(path, tmp_path / "state", approval, True, lambda: inputs["rows"], SimpleNamespace(request=submit))
    assert len(calls) == 1


def test_suppression_rechecked_between_recipients(tmp_path, inputs):
    inputs["rows"] += [{**inputs["rows"][0], "id": 2, "email": "second@example.com"}]
    path = prepare(tmp_path, inputs)
    approval = tmp_path / "approved.json"
    approve_artifact(path, approval, "publish")
    def submit(*a, **kw):
        inputs["rows"][1]["subscribed"] = 0
        return {"message_id": "first"}
    result = deliver(path, tmp_path / "state", approval, True, lambda: inputs["rows"], SimpleNamespace(request=submit))
    assert result["suppressed_or_changed"] == 1


def test_snapshot_paginates_and_fetches_each_manager_once(inputs):
    calls = []
    def fetch(url):
        calls.append(url)
        if "bootstrap-static" in url:
            return {"events": [{"id": 8, "is_current": True, "deadline_time": "2026-08-01", "data_checked": False}], "elements": [{"id": 1, "web_name": "Player", "news": ""}]}
        if "/picks/" in url:
            return {"picks": [{"element": 1}]}
        if "/entry/" in url:
            return {"name": "Team", "leagues": {"classic": [{"id": i, "name": "League", "admin_entry": 100} for i in (10,20)]}}
        return {"league": {"name": "League"}, "standings": {"has_next": "page_standings=1" in url, "results": []}}
    snapshot(inputs["rows"] * 2, fetch)
    assert sum("bootstrap-static" in u for u in calls) == 1
    assert sum("/picks/" in u for u in calls) == 1
    assert sum("page_standings=2" in u for u in calls) == 2


def test_reconcile_requires_matching_remote_message(tmp_path, inputs):
    from split_peel.newsletter import reconcile
    path = prepare(tmp_path, inputs)
    message = read_json(path)["messages"][0]
    receipt = tmp_path / 'unknown.json'
    atomic_json(receipt, {"status": "unknown", "request": {"inbox": "finalwhistle@agentmail.to", "message": message}})
    remote = {"message_id": "mail1", "to": [message["to"]], "subject": message["subject"], "text": "wrong body"}
    provider = SimpleNamespace(request=lambda *a: remote)
    with pytest.raises(ValueError, match="does not match"):
        reconcile(receipt, "mail1", provider)
    assert read_json(receipt)["status"] == "unknown"
    remote['text'] = message['text']
    reconcile(receipt, "mail1", provider)
    assert read_json(receipt)["status"] == "complete"


def test_branded_html_escapes_content_and_keeps_essential_links(tmp_path, inputs):
    inputs['brief']['title'] = '<script>alert(1)</script>'
    path = prepare(tmp_path, inputs)
    html = read_json(path)['messages'][0]['html']
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'https://x.com/closertoyes' in html
    assert 'Unsubscribe' in html and 'secret-token' in html
    assert 'role="presentation"' in html and 'max-width:600px' in html
    assert len(html.encode()) < 100_000
    assert (tmp_path / 'plan-previews' / '1.html').exists()


def test_design_test_send_has_one_explicit_recipient_and_no_subscriber_lookup(tmp_path, monkeypatch):
    from split_peel.newsletter import test_send as send_examples
    monkeypatch.setattr('split_peel.newsletter.subscribers', lambda: pytest.fail('Test must never load subscribers'))
    requests = []
    provider = SimpleNamespace(request=lambda path, **kwargs: requests.append(kwargs['body']) or {'message_id': str(len(requests))})
    assert send_examples('test@example.com', 'all', tmp_path, False, provider)['dry_run']
    assert not requests
    for _ in range(2):
        send_examples('test@example.com', 'all', tmp_path, True, provider)
    assert len(requests) == 3
    assert all(r['to'] == 'test@example.com' and r['subject'].startswith('[TEST]') and 'DESIGN EXAMPLE' in r['html'] for r in requests)


def test_html_rejects_non_https_links():
    from split_peel.newsletter_design import render_email
    with pytest.raises(ValueError, match='HTTPS'):
        render_email(title='Title', hook='Hook', watch='javascript:alert(1)', unsubscribe='https://final-whistle.app/')


def test_thumbnail_editorial_sections_and_instruction_guard(tmp_path, inputs):
    from split_peel.artifacts import digest
    instructions = tmp_path / 'instructions.txt'
    instructions.write_text('Lead with the captaincy story; keep the tone warm.')
    inputs['instructions'] = instructions
    inputs['brief']['sections'] = [{'heading': 'The talking point', 'paragraphs': ['Reviewed editorial copy.']}]
    with pytest.raises(ValueError, match='instructions'):
        prepare(tmp_path, inputs)
    inputs['brief']['editorial_instructions_sha256'] = digest(instructions)
    plan = read_json(prepare(tmp_path, inputs))
    html = plan['messages'][0]['html']
    assert 'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg' in html
    assert 'The talking point' in html and 'Reviewed editorial copy.' in html
    assert 'Lead with the captaincy' not in html


def test_tracking_uses_opaque_tokens_and_registers_before_send(tmp_path, inputs, monkeypatch):
    inputs['tracking'] = True
    path = prepare(tmp_path, inputs)
    plan = read_json(path)
    message = plan['messages'][0]
    assert '/n/' + message['link_token'] + '/youtube' in message['html']
    assert message['to'] not in message['html']
    events = []
    monkeypatch.setattr('split_peel.newsletter_metrics.register_issue', lambda p: events.append('register'))
    approve_artifact(path, tmp_path / 'approval.json', 'publish')
    provider = SimpleNamespace(request=lambda *a, **kw: events.append('send') or {'message_id': 'accepted'})
    deliver(path, tmp_path / 'state', tmp_path / 'approval.json', True, lambda: inputs['rows'], provider)
    assert events == ['register', 'send']


def test_issue_report_distinguishes_acceptance_delivery_and_unavailable_metrics(tmp_path, inputs):
    from split_peel.newsletter_metrics import report_issue
    path = prepare(tmp_path, inputs)
    plan = read_json(path)
    approve_artifact(path, tmp_path / 'approval.json', 'publish')
    provider = SimpleNamespace(request=lambda *a, **kw: {'message_id': 'accepted', 'labels': ['delivered']})
    deliver(path, tmp_path / 'state', tmp_path / 'approval.json', True, lambda: inputs['rows'], provider)
    report = report_issue(plan, tmp_path / 'state')
    assert report['counts']['accepted'] == 1 and report['counts']['delivered'] is None
    refreshed = report_issue(plan, tmp_path / 'state', refresh=True, provider=provider)
    assert refreshed['counts']['delivered'] == 1 and refreshed['counts']['opened'] is None
    assert list((tmp_path / 'state' / 'issue-history').rglob('*.json'))


@pytest.mark.parametrize('tracking', [False, True])
def test_thumbnail_and_button_both_open_exact_uploaded_episode(tmp_path, inputs, tracking, monkeypatch):
    import re
    from split_peel.newsletter_metrics import register_issue
    inputs['tracking'] = tracking
    inputs['youtube']['video_id'] = 'newShow123A'
    inputs['youtube']['response']['id'] = 'newShow123A'
    plan = read_json(prepare(tmp_path, inputs))
    html = plan['messages'][0]['html']
    image_link = re.search(r'<a href="([^"]+)"><img src="https://i.ytimg.com/vi/newShow123A/hqdefault.jpg"', html)[1]
    button_link = re.search(r'<a href="([^"]+)"[^>]*>▶ Watch Final Whistle on YouTube', html)[1]
    assert image_link == button_link
    assert plan['watch_url'] == 'https://www.youtube.com/watch?v=newShow123A'
    assert '@split-peel' not in image_link
    if tracking:
        requests = []
        monkeypatch.setattr('split_peel.newsletter_metrics.app_request', lambda path, body: requests.append(body))
        register_issue(plan)
        assert requests[0]['youtubeUrl'] == plan['watch_url']
    else:
        assert image_link == plan['watch_url']


def test_mismatched_upload_receipt_is_rejected(inputs):
    inputs['youtube']['response']['id'] = 'otherShow123'
    with pytest.raises(ValueError, match='disagrees'):
        youtube_url(inputs['youtube'])


def test_newsletter_only_subscriber_gets_shared_edition_without_fpl_calls(tmp_path, inputs):
    inputs['rows'][0].update(fpl_entry_id=None, league_id=None, leagues=[])
    evidence = snapshot(inputs['rows'], lambda url: pytest.fail('No FPL requests for newsletter-only readers'))
    assert not evidence['managers'] and not evidence['leagues']
    inputs['evidence'] = evidence
    plan = read_json(prepare(tmp_path, inputs))
    assert len(plan['messages']) == 1 and not plan['needs_review']
    html = plan['messages'][0]['html']
    assert 'A shared football fact.' in html
    assert 'YOUR LEAGUE' not in html and 'On your squad radar' not in html
    assert 'Unsubscribe' in html
