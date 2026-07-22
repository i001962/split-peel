import urllib.error

import pytest

from split_peel.espn import build_scoreboard_overlays, download_match_logos, normalize_scoreboard, scoreboard_url_for_league


def test_scoreboard_url_for_league_builds_soccer_url():
    assert (
        scoreboard_url_for_league("fifa.world")
        == "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    )
    assert (
        scoreboard_url_for_league(" fra.1 ")
        == "https://site.api.espn.com/apis/site/v2/sports/soccer/fra.1/scoreboard"
    )


def test_normalize_scoreboard_extracts_featured_match():
    scoreboard = {
        "leagues": [{"id": "700", "name": "English Premier League", "abbreviation": "Premier League"}],
        "events": [
            {
                "id": "1",
                "date": "2026-08-21T19:00Z",
                "name": "Coventry City at Arsenal",
                "shortName": "COV @ ARS",
                "status": {"type": {"state": "pre", "description": "Scheduled", "detail": "Fri at 3:00 PM"}},
                "venue": {"displayName": "Emirates Stadium"},
                "competitions": [
                    {
                        "details": [
                            {
                                "clock": "12'",
                                "type": {"text": "Goal"},
                                "text": "Bukayo Saka scores",
                                "team": {"displayName": "Arsenal"},
                            }
                        ],
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "0",
                                "form": "LWWWW",
                                "team": {
                                    "id": "359",
                                    "displayName": "Arsenal",
                                    "shortDisplayName": "Arsenal",
                                    "abbreviation": "ARS",
                                    "logo": "https://example.com/ars.png",
                                },
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "form": "WWWDD",
                                "team": {
                                    "id": "388",
                                    "displayName": "Coventry City",
                                    "shortDisplayName": "Coventry",
                                    "abbreviation": "COV",
                                    "logo": "https://example.com/cov.png",
                                },
                            },
                        ]
                    }
                ],
            }
        ],
    }

    context = normalize_scoreboard(scoreboard)

    assert context["league"]["name"] == "English Premier League"
    assert context["match"]["shortName"] == "COV @ ARS"
    assert context["match"]["venue"]["name"] == "Emirates Stadium"
    assert context["match"]["teams"][0]["abbreviation"] == "ARS"
    assert context["match"]["keyMoments"][0]["text"] == "Bukayo Saka scores"
    assert context["match"]["keyMoments"][0]["team"] == "Arsenal"
    assert len(context["matches"]) == 1
    assert context["match"] is context["matches"][0]


def test_normalize_scoreboard_flattens_espn_soccer_detail_objects():
    scoreboard = {
        "leagues": [{"id": "2", "name": "UEFA Champions League", "abbreviation": "UCL"}],
        "events": [
            {
                "id": "1",
                "date": "2026-07-22T19:00Z",
                "name": "Arsenal at Paris Saint-Germain",
                "shortName": "ARS @ PSG",
                "status": {"type": {"state": "post", "description": "Final"}},
                "competitions": [
                    {
                        "details": [
                            {
                                "type": {"id": "70", "text": "Goal"},
                                "clock": {"value": 302.0, "displayValue": "6'"},
                                "team": {"id": "359"},
                                "scoreValue": 1,
                                "athletesInvolved": [{"shortName": "K. Havertz"}],
                            },
                            {
                                "type": {"id": "94", "text": "Yellow Card"},
                                "clock": {"value": 2760.0, "displayValue": "46'"},
                                "team": {"id": "160"},
                                "scoreValue": 0,
                                "athletesInvolved": [{"displayName": "Ousmane Dembélé"}],
                            },
                        ],
                        "competitors": [
                            {
                                "homeAway": "away",
                                "team": {"id": "359", "displayName": "Arsenal", "abbreviation": "ARS"},
                            },
                            {
                                "homeAway": "home",
                                "team": {"id": "160", "displayName": "Paris Saint-Germain", "abbreviation": "PSG"},
                            },
                        ],
                    }
                ],
            }
        ],
    }

    context = normalize_scoreboard(scoreboard)

    assert context["match"]["keyMoments"] == [
        {"clock": "6'", "type": "Goal", "text": "K. Havertz: Goal", "team": "ARS", "score": 1},
        {
            "clock": "46'",
            "type": "Yellow Card",
            "text": "Ousmane Dembélé: Yellow Card",
            "team": "PSG",
            "score": None,
        },
    ]


def test_normalize_scoreboard_selects_explicit_match_id():
    scoreboard = {
        "leagues": [{"id": "700", "name": "MLS", "abbreviation": "MLS"}],
        "events": [
            _scoreboard_event("1", "Early Match", "EAR @ ONE", "2026-08-21T19:00Z"),
            _scoreboard_event("2", "Chosen Match", "TWO @ CHO", "2026-08-21T22:00Z"),
        ],
    }

    context = normalize_scoreboard(scoreboard, match_id="2")

    assert context["match"]["id"] == "2"
    assert context["match"]["shortName"] == "TWO @ CHO"
    assert [match["id"] for match in context["matches"]] == ["1", "2"]


def test_normalize_scoreboard_errors_for_missing_match_id():
    scoreboard = {
        "leagues": [{"id": "700", "name": "MLS", "abbreviation": "MLS"}],
        "events": [_scoreboard_event("1", "Early Match", "EAR @ ONE", "2026-08-21T19:00Z")],
    }

    with pytest.raises(ValueError, match="ESPN match id 9 was not found"):
        normalize_scoreboard(scoreboard, match_id="9")


def test_build_scoreboard_overlays_uses_local_logos():
    context = {
        "match": {
            "teams": [
                {"homeAway": "home", "abbreviation": "ARS", "name": "Arsenal", "localLogo": "runs/latest/ars-logo.png"},
                {"homeAway": "away", "abbreviation": "COV", "name": "Coventry", "localLogo": "runs/latest/cov-logo.png"},
            ]
        }
    }

    manifest = build_scoreboard_overlays(context)

    assert [overlay["file"] for overlay in manifest["overlays"]] == [
        "runs/latest/ars-logo.png",
        "runs/latest/cov-logo.png",
    ]
    assert manifest["overlays"][0]["x"] == 0.18
    assert manifest["overlays"][1]["x"] == 0.82
    assert len(manifest["overlays"]) == 2


def test_download_match_logos_continues_when_logo_download_fails(tmp_path, monkeypatch):
    def fail_urlopen(request, timeout):
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr("split_peel.espn.urllib.request.urlopen", fail_urlopen)
    context = {
        "match": {
            "teams": [
                {
                    "abbreviation": "ARS",
                    "name": "Arsenal",
                    "logo": "https://example.com/ars.png",
                }
            ]
        }
    }

    downloaded = download_match_logos(context, tmp_path)

    assert downloaded == []
    assert "timeout" in context["match"]["teams"][0]["logoDownloadError"]
    assert not (tmp_path / "ars-logo.png").exists()


def _scoreboard_event(event_id, name, short_name, date):
    return {
        "id": event_id,
        "date": date,
        "name": name,
        "shortName": short_name,
        "status": {"type": {"state": "pre", "description": "Scheduled", "detail": "Fri at 3:00 PM"}},
        "venue": {"displayName": "Test Stadium"},
        "competitions": [{"competitors": []}],
    }


def test_build_scoreboard_overlays_adds_final_score_for_completed_match(tmp_path):
    home_logo = tmp_path / "ars-logo.png"
    away_logo = tmp_path / "cov-logo.png"
    home_logo.write_bytes(b"fake")
    away_logo.write_bytes(b"fake")
    context = {
        "match": {
            "status": {"state": "post", "description": "Final"},
            "teams": [
                {
                    "homeAway": "home",
                    "abbreviation": "ARS",
                    "name": "Arsenal",
                    "score": "3",
                    "localLogo": str(home_logo),
                },
                {
                    "homeAway": "away",
                    "abbreviation": "COV",
                    "name": "Coventry",
                    "score": "1",
                    "localLogo": str(away_logo),
                },
            ],
        }
    }

    manifest = build_scoreboard_overlays(context)

    score_overlay = manifest["overlays"][2]
    assert score_overlay["name"] == "final score"
    assert score_overlay["x"] == 0.5
    assert score_overlay["y"] == 0.14
    assert score_overlay["file"] == str(tmp_path / "score-overlay.png")
    assert (tmp_path / "score-overlay.png").exists()


def test_build_scoreboard_overlays_adds_key_moments_center_panel(tmp_path):
    home_logo = tmp_path / "ars-logo.png"
    away_logo = tmp_path / "cov-logo.png"
    home_logo.write_bytes(b"fake")
    away_logo.write_bytes(b"fake")
    context = {
        "match": {
            "shortName": "COV @ ARS",
            "keyMoments": [{"clock": "78'", "text": "Winner from distance", "team": "Arsenal"}],
            "teams": [
                {"homeAway": "home", "abbreviation": "ARS", "name": "Arsenal", "localLogo": str(home_logo)},
                {"homeAway": "away", "abbreviation": "COV", "name": "Coventry", "localLogo": str(away_logo)},
            ],
        }
    }

    manifest = build_scoreboard_overlays(context)

    moments_overlay = manifest["overlays"][2]
    assert moments_overlay["name"] == "key moments"
    assert moments_overlay["x"] == 0.5
    assert moments_overlay["y"] == 0.31
    assert moments_overlay["file"] == str(tmp_path / "key-moments-overlay.png")
    assert (tmp_path / "key-moments-overlay.png").exists()


def test_build_scoreboard_overlays_adds_paged_game_week_slate(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"fake")
    matches = []
    for index in range(7):
        matches.append(
            {
                "id": str(index),
                "date": f"2026-08-{21 + index:02d}T19:00:00Z",
                "teams": [
                    {
                        "homeAway": "home",
                        "name": f"Home {index}",
                        "shortName": f"Home {index}",
                        "localLogo": str(logo),
                    },
                    {
                        "homeAway": "away",
                        "name": f"Away {index}",
                        "shortName": f"Away {index}",
                        "localLogo": str(logo),
                    },
                ],
            }
        )

    manifest = build_scoreboard_overlays({"matches": matches, "match": matches[0]}, episode_type="game-week-preview")

    assert [overlay["name"] for overlay in manifest["overlays"]] == ["game week slate 1", "game week slate 2"]
    assert manifest["overlays"][0]["start"] == 8
    assert manifest["overlays"][1]["start"] == 20
    assert manifest["overlays"][0]["x"] == 0.5
    assert manifest["overlays"][0]["y"] == 0.48
    assert (tmp_path / "game-week-slate-1.png").exists()
    assert (tmp_path / "game-week-slate-2.png").exists()
