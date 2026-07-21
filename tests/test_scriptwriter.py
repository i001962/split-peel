import json

from split_peel.scriptwriter import draft_script


def test_draft_script_returns_structured_dialogue():
    feed = {
        "casts": [
            {
                "text": "Spain won the World Cup final and Messi discourse is everywhere",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "fan"},
                "reactions": {"likes_count": 3},
                "replies": {"count": 1},
            }
        ]
    }

    script = draft_script(feed)

    assert script["title"] == "Spain Win, Farcaster Loses Its Mind"
    assert script["dialogue"]
    assert {"speaker", "line", "tone", "start"} <= set(script["dialogue"][0])
    assert script["dialogue"][0]["line"].startswith("Welcome to Match Replies.")
    assert "I'm Split" in script["dialogue"][0]["line"]
    assert "Peel" in script["dialogue"][0]["line"]
    assert "subscribe" in script["dialogue"][-1]["line"].lower() or "replies" in script["dialogue"][-1]["line"].lower()


def test_match_context_filters_unrelated_world_cup_casts():
    feed = {
        "casts": [
            {
                "text": "Spain won the World Cup final and Messi discourse is everywhere",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "worldcup"},
                "reactions": {"likes_count": 30},
                "replies": {"count": 10},
            },
            {
                "text": "Arsenal against Coventry is exactly the kind of fixture that makes form guides look silly",
                "timestamp": "2026-07-20T00:01:00.000Z",
                "author": {"username": "prem"},
                "reactions": {"likes_count": 1},
                "replies": {"count": 0},
            },
        ]
    }
    match_context = {
        "match": {
            "shortName": "COV @ ARS",
            "status": {"description": "Scheduled"},
            "teams": [{"name": "Arsenal", "abbreviation": "ARS"}, {"name": "Coventry City", "abbreviation": "COV"}],
        }
    }

    script = draft_script(feed, match_context=match_context)

    assert script["sourceCasts"][0]["username"] == "prem"
    assert "worldcup" not in [cast["username"] for cast in script["sourceCasts"]]
    assert script["fallbackCasts"] == []


def test_match_context_keeps_unmatched_casts_only_as_fallback_metadata():
    feed = {
        "casts": [
            {
                "text": "Spain won the World Cup final and Messi discourse is everywhere",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "worldcup"},
                "reactions": {"likes_count": 30},
                "replies": {"count": 10},
            }
        ]
    }
    match_context = {
        "match": {
            "shortName": "COV @ ARS",
            "status": {"description": "Scheduled"},
            "teams": [{"name": "Arsenal", "abbreviation": "ARS"}, {"name": "Coventry City", "abbreviation": "COV"}],
        }
    }

    script = draft_script(feed, match_context=match_context)

    assert script["sourceCasts"] == []
    assert script["fallbackCasts"][0]["username"] == "worldcup"


def test_match_context_keeps_relevant_world_cup_casts_for_spain_argentina():
    feed = {
        "casts": [
            {
                "text": "Spain won the World Cup final and Messi discourse is everywhere",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "worldcup"},
                "reactions": {"likes_count": 3},
                "replies": {"count": 1},
            }
        ]
    }
    match_context = {
        "match": {
            "shortName": "ARG @ ESP",
            "status": {"description": "Final"},
            "teams": [{"name": "Spain", "abbreviation": "ESP"}, {"name": "Argentina", "abbreviation": "ARG"}],
        }
    }

    script = draft_script(feed, match_context=match_context)

    assert script["sourceCasts"][0]["username"] == "worldcup"
    assert script["sourceCasts"][0]["matchHits"] > 0


def test_repeated_team_mentions_get_varied_or_deduped_lines():
    feed = {
        "casts": [
            {
                "text": "Spain Spain Spain",
                "timestamp": "2026-07-20T00:00:00.000Z",
                "author": {"username": "one", "pfp_url": "https://example.com/one.png"},
                "reactions": {"likes_count": 1},
                "replies": {"count": 0},
            },
            {
                "text": "Spain fans are talking again",
                "timestamp": "2026-07-20T00:01:00.000Z",
                "author": {"username": "two", "pfp_url": "https://example.com/two.png"},
                "reactions": {"likes_count": 1},
                "replies": {"count": 0},
            },
        ]
    }
    match_context = {
        "match": {
            "shortName": "ARG @ ESP",
            "status": {"description": "Final"},
            "teams": [{"name": "Spain", "abbreviation": "ESP"}, {"name": "Argentina", "abbreviation": "ARG"}],
        }
    }

    script = draft_script(feed, match_context=match_context)
    banter_lines = [line["line"] for line in script["dialogue"] if line.get("sourceUsername")]

    assert len(banter_lines) == len(set(banter_lines))
    assert script["sourceCasts"][0]["pfpUrl"]


def test_draft_script_uses_instructions_and_memory():
    feed = {"casts": []}
    memory = [{"title": "Previous Banter", "createdAt": "2026-07-20T00:00:00Z", "beats": ["Old bit"]}]

    script = draft_script(
        feed,
        episode_memory=memory,
        instructions="Call out Arsenal fans gently.",
    )

    assert script["instructions"] == "Call out Arsenal fans gently."
    assert script["memoryUsed"][0]["title"] == "Previous Banter"
    assert all("Producer note" not in line["line"] for line in script["dialogue"])
    assert all("Call out Arsenal fans gently" not in line["line"] for line in script["dialogue"])
    assert all("Previous Banter" not in line["line"] for line in script["dialogue"])


def test_espn_only_instructions_do_not_leak_prompt_or_social_references():
    feed = {"casts": []}
    match_context = {
        "match": {
            "shortName": "COV @ ARS",
            "status": {"description": "Scheduled", "detail": "Fri, August 21st at 3:00 PM EDT"},
            "venue": {"name": "Emirates Stadium"},
            "teams": [
                {"name": "Arsenal", "abbreviation": "ARS", "form": "LWWWW"},
                {"name": "Coventry City", "abbreviation": "COV", "form": "WWWDD"},
            ],
        }
    }

    script = draft_script(
        feed,
        match_context=match_context,
        instructions=(
            "Create an ESPN Premier League match-context episode only. Do not reference Farcaster, "
            "social posts, casts, usernames, or timeline reactions."
        ),
    )
    spoken = " ".join(line["line"] for line in script["dialogue"]).lower()

    assert "producer note" not in spoken
    assert "create an espn" not in spoken
    assert "last time" not in spoken
    assert "logged" not in spoken
    assert "episode" not in spoken
    assert "farcaster" not in spoken
    assert "social" not in spoken
    assert "cast" not in spoken
    assert "timeline" not in spoken
    assert "arsenal" in spoken
    assert "coventry" in spoken


def test_espn_only_match_scripts_vary_by_fixture_identity():
    feed = {"casts": []}
    instructions = "Create an ESPN match-context episode only. Do not reference Farcaster, casts, social posts, or timeline reactions."
    arsenal_context = {
        "match": {
            "id": "ars-cov",
            "shortName": "COV @ ARS",
            "date": "2026-08-21T19:00Z",
            "status": {"description": "Scheduled", "detail": "Fri, August 21st at 3:00 PM EDT"},
            "venue": {"name": "Emirates Stadium"},
            "teams": [
                {"name": "Arsenal", "abbreviation": "ARS", "form": "LWWWW"},
                {"name": "Coventry City", "abbreviation": "COV", "form": "WWWDD"},
            ],
        }
    }
    marseille_context = {
        "match": {
            "id": "mar-str",
            "shortName": "STR @ OLM",
            "date": "2026-08-21T18:45Z",
            "status": {"description": "Scheduled", "detail": "Fri, August 21st at 2:45 PM EDT"},
            "venue": {"name": "Stade Vélodrome"},
            "teams": [
                {"name": "Marseille", "abbreviation": "OLM", "form": "WWLDL"},
                {"name": "Strasbourg", "abbreviation": "STR", "form": "WWDLL"},
            ],
        }
    }

    arsenal_lines = [line["line"] for line in draft_script(feed, match_context=arsenal_context, instructions=instructions)["dialogue"]]
    marseille_lines = [line["line"] for line in draft_script(feed, match_context=marseille_context, instructions=instructions)["dialogue"]]

    assert len(arsenal_lines) == len(marseille_lines)
    assert arsenal_lines[1].split(".")[0] != marseille_lines[1].split(".")[0]
    assert arsenal_lines[-1] != marseille_lines[-1]


def test_openai_script_provider_generates_structured_dialogue(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "dialogue": [
                                                {
                                                    "speaker": "split",
                                                    "line": "Marseille have turned the form guide into a tiny siren.",
                                                    "tone": "start clipped and forensic, then brighten into delighted alarm",
                                                },
                                                {
                                                    "speaker": "peel",
                                                    "line": "Strasbourg arrive carrying weather-warning energy and suspicious confidence.",
                                                    "tone": "fast whispered conspiracy with a triumphant final word",
                                                },
                                            ]
                                        }
                                    ),
                                }
                            ]
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SPLIT_PEEL_SCRIPT_MODEL", "gpt-test")
    monkeypatch.setattr("split_peel.scriptwriter.urllib.request.urlopen", fake_urlopen)

    script = draft_script(
        {"casts": []},
        match_context={
            "match": {
                "shortName": "STR @ OLM",
                "teams": [{"name": "Marseille"}, {"name": "Strasbourg"}],
            }
        },
        characters={
            "characters": [
                {"id": "split", "displayName": "Split", "personality": ["sharp"]},
                {"id": "peel", "displayName": "Peel", "personality": ["chaotic"]},
            ]
        },
        instructions="Do not reference Farcaster.",
        script_provider="openai",
    )

    assert captured["body"]["model"] == "gpt-test"
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert "Do not reference Farcaster" in captured["body"]["input"][1]["content"]
    assert "voice-performance direction" in captured["body"]["input"][1]["content"]
    assert "Do not write a show welcome" in captured["body"]["input"][1]["content"]
    assert [line["speaker"] for line in script["dialogue"]] == ["split", "split", "peel", "peel"]
    assert script["dialogue"][0]["line"].startswith("Welcome to")
    assert "tiny siren" in script["dialogue"][1]["line"]
    assert "delighted alarm" in script["dialogue"][1]["tone"]
    assert "subscribe" in script["dialogue"][-1]["line"].lower() or "replies" in script["dialogue"][-1]["line"].lower()
