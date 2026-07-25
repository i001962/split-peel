import json

import pytest

from split_peel.x_trends import XTrendsError, fetch_x_trends, normalize_x_trends, x_trends_url


def test_x_trends_url_uses_woeid_endpoint():
    assert x_trends_url("23424977") == "https://api.x.com/2/trends/by/woeid/23424977"


def test_fetch_x_trends_requires_bearer(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    with pytest.raises(XTrendsError, match="X_BEARER_TOKEN"):
        fetch_x_trends()


def test_fetch_x_trends_sends_bearer(monkeypatch):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"data": [{"trend_name": "Bayern", "tweet_count": 12000}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.headers["Authorization"], timeout))
        return FakeResponse()

    monkeypatch.setattr("split_peel.x_trends.urlopen", fake_urlopen)

    payload = fetch_x_trends("1", bearer_token="token", timeout=5)

    assert payload["data"][0]["trend_name"] == "Bayern"
    assert calls == [("https://api.x.com/2/trends/by/woeid/1", "Bearer token", 5)]


def test_normalize_x_trends_accepts_api_shape():
    trends = normalize_x_trends({"data": [{"trend_name": "#TransferNews", "tweet_count": "45000"}]})

    assert trends[0].name == "#TransferNews"
    assert trends[0].tweet_count == 45000
