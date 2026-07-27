import json

from split_peel.feed import (
    DEFAULT_FALSENINE_BOT_FEED_URL,
    DEFAULT_FOOTBALL_FEED_URL,
    farcaster_user_casts_url,
    fetch_feed,
    fetch_research_feed,
    football_feed_url,
    match_terms_from_context,
    rank_match_relevant_casts,
)


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


def test_farcaster_user_casts_url_encodes_falsenine_bot_fid():
    assert farcaster_user_casts_url(limit=20) == (
        "https://haatz.quilibrium.com/v2/farcaster/feed/user/casts?fid=2477947&limit=20"
    )
    assert DEFAULT_FALSENINE_BOT_FEED_URL == farcaster_user_casts_url()


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


def test_fetch_research_feed_merges_and_labels_falsenine_bot(monkeypatch):
    def fake_fetch_feed(url, timeout=30):
        if url == DEFAULT_FOOTBALL_FEED_URL:
            return {
                "casts": [
                    {
                        "hash": "0xfan",
                        "text": "Fan texture about Bayern transfer rumor.",
                        "author": {"username": "fan"},
                    }
                ]
            }
        if url == DEFAULT_FALSENINE_BOT_FEED_URL:
            return {
                "casts": [
                    {
                        "hash": "0xbot",
                        "text": "Falsenine reports a Bayern transfer detail.",
                        "author": {"username": "falsenine"},
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr("split_peel.feed.fetch_feed", fake_fetch_feed)

    payload = fetch_research_feed()

    assert [cast["researchSourceId"] for cast in payload["casts"]] == ["football-channel", "falsenine-bot"]
    assert payload["casts"][0]["factCheckRequired"] is False
    assert payload["casts"][1]["factCheckRequired"] is True
    assert payload["researchSources"][1]["fid"] == "2477947"
    assert payload["sourceErrors"] == []
    assert payload["researchLoop"] == ["load", "extract", "graph", "index", "query", "memory", "produce-show", "update-learning"]
    assert {"source:football-channel", "source:falsenine-bot"} <= {node["id"] for node in payload["researchGraph"]["nodes"]}
    assert "bayern" in payload["researchIndex"]["terms"]


def test_fetch_research_feed_keeps_primary_feed_when_bot_source_fails(monkeypatch):
    def fake_fetch_feed(url, timeout=30):
        if url == DEFAULT_FOOTBALL_FEED_URL:
            return {"casts": [{"hash": "0xfan", "text": "Fan post", "author": {"username": "fan"}}]}
        raise RuntimeError("bot unavailable")

    monkeypatch.setattr("split_peel.feed.fetch_feed", fake_fetch_feed)

    payload = fetch_research_feed()

    assert len(payload["casts"]) == 1
    assert payload["casts"][0]["researchSourceId"] == "football-channel"
    assert payload["sourceErrors"][0]["sourceId"] == "falsenine-bot"
