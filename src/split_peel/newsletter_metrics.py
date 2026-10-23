"""Issue-level operational reports and best-effort, explicitly qualified engagement."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from split_peel.artifacts import atomic_json, identity, read_json

APP = 'https://final-whistle.app'


def app_request(path, body=None):
    token = os.environ.get('FINAL_WHISTLE_ADMIN_TOKEN', '').strip()
    if not token:
        raise ValueError('Set FINAL_WHISTLE_ADMIN_TOKEN for newsletter tracking')
    request = Request(APP + path, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                      data=json.dumps(body).encode() if body is not None else None)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def register_issue(plan):
    if plan.get('click_tracking'):
        return app_request('/api/admin/newsletter-issue', {
            'id': plan['episode_id'], 'title': plan['title'], 'youtubeUrl': plan['watch_url'],
            'recipients': [{'subscriberId': m['subscriber_id'], 'token': m['link_token']} for m in plan['messages']]})


def report_issue(plan, state, out=None, refresh=False, provider=None, fetch_app=app_request):
    totals = dict(planned=len(plan['messages']), accepted=0, unknown=0, not_submitted=0,
                  delivered=0, bounced=0, complained=0, opened=0, provider_unavailable=0)
    incidents = []
    for message in plan['messages']:
        receipt = state / identity({'episode': plan['episode_id'], 'email': message['to']}) / 'delivery.json'
        if not receipt.exists():
            totals['not_submitted'] += 1
            continue
        value = read_json(receipt)
        if value.get('status') != 'complete':
            totals['unknown'] += 1
            incidents.append({'subscriber_id': message['subscriber_id'], 'status': value.get('status'), 'error_type': value.get('error_type')})
            continue
        totals['accepted'] += 1
        if refresh:
            try:
                if provider is None:
                    from split_peel.agentmail import AgentMailClient
                    provider = AgentMailClient()
                message_id = value['result']['message_id']
                remote = provider.request(f"/inboxes/{quote(plan['inbox'], safe='')}/messages/{quote(message_id, safe='')}")
                labels = set(remote.get('labels') or [])
                for label in ('delivered', 'bounced', 'complained', 'opened'):
                    totals[label] += int(label in labels)
            except Exception as error:
                totals['provider_unavailable'] += 1
                incidents.append({'subscriber_id': message['subscriber_id'], 'status': 'provider-status-unavailable', 'error_type': type(error).__name__})
    clicks = {'status': 'not-collected', 'reason': 'Run stats --refresh after the tracked links are deployed.'}
    if refresh and plan.get('click_tracking'):
        try:
            clicks = fetch_app('/api/admin/newsletter-stats?issue=' + quote(plan['episode_id']))
        except Exception as error:
            clicks = {'status': 'unavailable', 'error_type': type(error).__name__}
    elif not plan.get('click_tracking'):
        clicks = {'status': 'disabled'}
    result = {'version': 1, 'issue_id': plan['episode_id'], 'title': plan.get('title'),
              'observed_at': datetime.now(timezone.utc).isoformat(), 'counts': totals,
              'provider_status': ('partial' if totals['provider_unavailable'] else 'checked') if refresh else 'not-refreshed',
              'clicks': clicks, 'needs_review_count': len(plan.get('needs_review', [])), 'incidents': incidents,
              'limits': ['Acceptance is not inbox delivery.', 'Unavailable or uncollected metrics are not zero engagement.',
                         'Link requests include scanners and bots; they do not prove views or follows.',
                         'Open counts require provider support and tracking configuration; no pixel is enabled here.',
                         'Replies, YouTube watch time and X follows are not attributed automatically.']}
    if not refresh or totals['provider_unavailable'] == totals['accepted']:
        for label in ('delivered', 'bounced', 'complained', 'opened'):
            result['counts'][label] = None
    # Shared agentmail.to inbox has no custom-domain open tracking configured.
    result['counts']['opened'] = None
    target = out or state / 'issues' / (plan['episode_id'] + '.json')
    atomic_json(target, result)
    history = state / 'issue-history' / plan['episode_id'] / (identity(result) + '.json')
    atomic_json(history, result)
    return result
