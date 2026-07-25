from split_peel.topic_ideas import generate_topic_ideas


def test_generate_topic_ideas_uses_x_trends_and_farcaster_hooks():
    trends = {"data": [{"trend_name": "Bayern transfer", "tweet_count": 65000}, {"trend_name": "Random TV Show", "tweet_count": 12000}]}
    feed = {
        "casts": [
            {
                "text": "Bayern transfer rumors are already exhausting.",
                "timestamp": "2026-07-23T10:00:00.000Z",
                "author": {"username": "transferfan", "pfp_url": "https://example.com/pfp.png"},
                "reactions": {"likes_count": 8},
                "replies": {"count": 3},
            }
        ]
    }
    memory = [{"title": "The xG Ex-Girlfriend Bit", "beats": ["Peel misunderstood xG"], "sourceCastUsers": ["transferfan"]}]

    result = generate_topic_ideas(x_trends_payload=trends, feed=feed, memory=memory)

    idea = result["ideas"][0]
    assert result["ttsReady"] is False
    assert idea["ttsReady"] is False
    assert idea["topic"] == "Bayern transfer"
    assert idea["source"] == "x-trend"
    assert idea["suggestedEpisodeType"] == "general"
    assert idea["farcasterHooks"][0]["username"] == "transferfan"
    assert "X trend: Bayern transfer" in idea["whyNow"]


def test_generate_topic_ideas_uses_match_overlap_without_casts():
    trends = {"data": [{"trend_name": "Stuttgart", "tweet_count": 25000}]}
    context = {
        "match": {
            "shortName": "VFB @ MUN",
            "teams": [{"name": "Bayern Munich", "shortName": "Bayern"}, {"name": "VfB Stuttgart", "shortName": "Stuttgart"}],
        }
    }

    result = generate_topic_ideas(x_trends_payload=trends, feed={"casts": []}, match_context=context)

    assert result["ideas"][0]["title"] == "VFB @ MUN: Stuttgart Is Already A Bit"
    assert result["ideas"][0]["suggestedEpisodeType"] == "match-event"
    assert "stuttgart" in result["ideas"][0]["searchTerms"]


def test_generate_topic_ideas_falls_back_to_guided_probes():
    trends = {"data": [{"trend_name": "Korra"}, {"trend_name": "#loveisland"}]}
    context = {
        "match": {
            "shortName": "VFB @ MUN",
            "teams": [{"name": "Bayern Munich", "shortName": "Bayern"}, {"name": "VfB Stuttgart", "shortName": "Stuttgart"}],
        }
    }

    result = generate_topic_ideas(
        x_trends_payload=trends,
        feed={"casts": []},
        match_context=context,
        seed_terms=["transfer news"],
    )

    assert result["ideas"]
    assert result["ideas"][0]["source"] == "guided-probe"
    assert "Guided probe:" in result["ideas"][0]["whyNow"][0]
