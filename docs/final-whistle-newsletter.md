# Final Whistle Match Report: setup and test

The newsletter is a self-contained Python add-on. It uses the existing AgentMail inbox, creates no inboxes, and does not need a running web server or a beehiiv subscription. The design borrows a readable editorial layout: navy/lime masthead, white reading surface, short sections, a clear YouTube button, league score cards, squad notes, and Split's X link.

## Preview three fictional examples

From this repository (Python 3.11+ recommended):

```bash
PYTHONPATH=src python3 -m split_peel.newsletter examples --out runs/newsletter-examples
```

Open `runs/newsletter-examples/index.html`. Checked-in copies are in `examples/newsletters/`. The companion website deploy exposes the same examples at `https://final-whistle.app/newsletter-examples/`. All sample manager data is fictional. Sample footer links do not unsubscribe anyone.

## Test mail to one address

Put the existing `AGENTMAIL_API_KEY` into the worker's private `.env`; never commit it. First inspect the dry run:

```bash
PYTHONPATH=src python3 -m split_peel.newsletter test-send --to YOUR_EMAIL
```

Then send only those three fictional examples to that address:

```bash
PYTHONPATH=src python3 -m split_peel.newsletter test-send --to YOUR_EMAIL --send
```

No subscriber DB is loaded by test-send. Subjects begin `[TEST]`. Delivery receipts live under `memory/newsletter-test-deliveries/`; rerunning unchanged examples does not send duplicates. An ambiguous API failure blocks retry. Acceptance by AgentMail does not establish Gmail inbox delivery. Check Inbox, Promotions and Spam, then open desktop and mobile versions. Check the watch button, X link, score cards, full footer and missing-image fallback. For a new design test change, receipts use the changed HTML identity. Do not delete live delivery receipts.

## Live newsletter preparation

The website is the subscription authority. Put `FINAL_WHISTLE_ADMIN_TOKEN` in the worker environment using the same value already configured on the website. The JSON export includes all selected league memberships after website PR #1. Newsletter output, addresses and manage tokens must stay inside ignored `runs/` and `memory/`, never in public examples.

```bash
PYTHONPATH=src python3 -m split_peel.newsletter snapshot --out memory/newsletter-snapshot.json
PYTHONPATH=src python3 -m split_peel.newsletter prepare --brief runs/EPISODE/newsletter-brief.json --exhaust runs/EPISODE/exhaust.json --snapshot memory/newsletter-snapshot.json --youtube-receipt runs/EPISODE/release/youtube.json --out runs/EPISODE/newsletter-plan.json
```

The daily Banny Studio writers' room supplies the exhaust and selected episode's public-safe title/hook. Snapshot collection deduplicates managers and paginates leagues; reuse lasts up to 84 hours unless registrations change or `--refresh` is supplied. Scores are marked provisional until FPL checks them. An unavailable snapshot produces the shared show edition. Three distinct registered managers unlock eligibility for episode call-outs only; newsletter sections are always allowed.

The exhaust schema is version 1, a season start year, integer gameweek and `facts` array. Each fact requires unique `id`, public-safe `text`, `scope` (`global` or `league`), `league_id` for league scope, `verified: true`, HTTPS primary `source`, and timezone-aware `observed_at` / `expires_at`. Optional `player_ids` filter to the recipient's last published squad. `ideas` and `callout_candidates` remain internal. Validate with `newsletter validate-exhaust --exhaust PATH`. Verification is editorial; schema validation is not fact-checking. No raw writers' room or external newsletter prose goes into emails.

A completed YouTube receipt must confirm public visibility, no scheduled publication, and a video ID. Private/unlisted/dry-run receipts are rejected. Preparation writes the plan, text preview, and one branded HTML file per recipient in `newsletter-plan-previews/`. One email combines selected leagues. Duplicate addresses and social-only profiles go to `needs_review` with no automatic DMs.

```bash
PYTHONPATH=src python3 -m split_peel.newsletter deliver --plan runs/EPISODE/newsletter-plan.json
# Only after reviewing and approving the exact edition:
PYTHONPATH=src python3 -m split_peel.newsletter approve --plan runs/EPISODE/newsletter-plan.json --out runs/EPISODE/newsletter-approval.json
PYTHONPATH=src python3 -m split_peel.newsletter deliver --plan runs/EPISODE/newsletter-plan.json --approval runs/EPISODE/newsletter-approval.json --send
```

Live delivery re-fetches authoritative subscriber state before each recipient; unsubscribed or changed profiles are skipped. Plans expire after 24 hours. Keep the same durable `memory/newsletter-deliveries` directory across workers and reruns; unknown results require inspection, not automatic retry. `newsletter reconcile --receipt PATH --message-id ID` checks remote message contents before resolving an unknown result. Provider delivery/bounce/complaint labels and first-party link requests can be refreshed using the stats command below. Automatic provider webhook suppression is not included.

The existing richer Banny Studio release workflow has a local automatic newsletter preparation hook. This standalone add-on deliberately does not ship unrelated uncommitted renderer/production changes; on a VPS using the current published production baseline, invoke `prepare` after the finished show is public. Pulling this code alone never activates subscriber sends. The daily writers' room continues producing evidence only.

## Website VPS deployment

In the existing `final-whistle-app` checkout:

```bash
git pull --ff-only origin main
docker compose up -d --build
```

Open `/newsletter-examples/`, and confirm the protected `/api/admin/export` still returns 401 without authorization. In the separate `split-peel` checkout, pull main to obtain the newsletter commands. Its `.env` is separate from the website container's `.env`.


## Sections, thumbnails, and distribution instructions

Each real edition links the published video thumbnail to YouTube. The brief may include `sections`: an array of `{ "heading": "The talking point", "paragraphs": ["Reviewed public copy."] }`. These shared editorial sections sit before personalized league score cards and squad notes. No external model call is made by the renderer.

When the producer adds newsletter instructions at distribution time, save the exact instruction in a private `newsletter-instructions.txt` beside the release. Read and apply it when drafting the brief and selecting newsletter facts; do not publish the instruction itself. After applying it, record that file's SHA-256 in `newsletter-brief.json` under `editorial_instructions_sha256`, and pass `--instructions PATH` to `newsletter prepare`. Mismatched acknowledgements block preparation. The local richer release flow accepts `--newsletter-instructions PATH` and pins its hash alongside the brief. Retain the final approved content and input hashes for issue review.

## Issue records and engagement

Normal editions use opaque, random first-party links for YouTube and X. Before sending, the worker registers only the issue metadata and subscriber link tokens through the protected website `/api/admin/newsletter-issue` endpoint. These links work only after the companion website changes are deployed. Their redirects have fixed destinations, do not expose emails in URLs, store no IP addresses, and never accept arbitrary redirect targets. `--no-click-tracking` prepares direct links instead. Test-example emails use direct links and are excluded from subscriber issue statistics.

Every live delivery run writes `memory/newsletter-deliveries/issues/VIDEO_ID.json` and timestamped observations under `issue-history/VIDEO_ID/`, including planned count, accepted submissions, unknown outcomes, preparation review count, and operational incidents. Use:

```bash
PYTHONPATH=src python3 -m split_peel.newsletter stats --plan runs/EPISODE/newsletter-plan.json --refresh
```

This reads AgentMail message labels for indicated delivery, bounce and complaint status, and the protected website `/api/admin/newsletter-stats?issue=VIDEO_ID` for YouTube/X link requests and distinct subscriber links. Uncollected provider metrics stay unavailable. The shared agentmail.to inbox does not enable a custom-domain open pixel; opens are unavailable. Security scanners and bots can follow links, so click counts do not establish human readers, YouTube views, or X follows. Watch time, actual follows, and reply attribution remain unavailable. Review stats after distribution and during later writers' room reflections; treat them as measurements with these limits, not evidence that a joke worked.


## Newsletter-only readers and the exact uploaded show

Email-only registration on `/join` does not require an FPL entry or league. These readers receive all shared editorial sections, the published show's thumbnail and watch button, and Split's X link. They get no invented personalization and do not count toward league call-out thresholds. Linking a team later upgrades the same email profile without creating a second subscription. Rejoining the shared newsletter never clears an existing linked team or memberships. No FPL requests are made when a snapshot contains only newsletter-only readers.

Both thumbnail and watch button resolve to the exact video in the completed upload receipt, including when click tracking is enabled. They never use the channel or a latest-video lookup. Inconsistent receipt video IDs block preparation. Static examples link to one explicit example episode; real distribution uses its own just-published episode.


## Email-only Match Reports

League sections live inside the email. Never add a public “read your report” link or an online league-report preview. Existing report URLs redirect to subscription signup; the email keeps YouTube as its primary action and profile management in the footer. The website report-generation API requires admin authentication. This does not restrict subscribers' newsletter content or remove fictional design examples.
