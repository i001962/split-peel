import json

from split_peel.feed import DEFAULT_FOOTBALL_FEED_URL, fetch_feed, football_feed_url, match_terms_from_context, rank_match_relevant_casts


def test_match_terms_from_context_includes_team_names_and_abbreviations():
    context = {
        "match": {
            "shortName": "COV @ ARS",
            "teams": [{"name": "Arsenal", "abbreviation": "ARS"}, {"name": "Coventry City", "abbreviation": "COV"}],
        }
    }

    terms = match_terms_from_context(context)

    assert {"arsenal", "ars", "coventry", "cov"} <= terms


def test_rank_match_relevant_casts_falls_back_when_no_match_hits():
    feed = {
        "casts": [
            {
                "text": "General football chatter",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "fan"},
                "reactions": {"likes_count": 1},
                "replies": {"count": 0},
            }
        ]
    }
    context = {"match": {"teams": [{"name": "Arsenal", "abbreviation": "ARS"}]}}

    ranked = rank_match_relevant_casts(feed, context)

    assert ranked[0].username == "fan"
    assert ranked[0].match_hits == 0


def test_football_feed_url_encodes_parent_url():
    assert football_feed_url(limit=10) == (
        "https://haatz.quilibrium.com/v2/farcaster/feed/parent_urls"
        "?parent_urls=chain%3A%2F%2Feip155%3A1%2Ferc721%3A0x7abfe142031532e1ad0e46f971cc0ef7cf4b98b0"
        "&limit=10"
    )


def test_fetch_feed_uses_default_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"casts": []}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("split_peel.feed.urlopen", fake_urlopen)

    assert fetch_feed(DEFAULT_FOOTBALL_FEED_URL) == {"casts": []}
    assert calls == [DEFAULT_FOOTBALL_FEED_URL]
