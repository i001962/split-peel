from split_peel.feed import match_terms_from_context, rank_match_relevant_casts


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
