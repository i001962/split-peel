from __future__ import annotations

import json
import re
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont


DEFAULT_ESPN_LEAGUE = "eng.1"
ESPN_SOCCER_SCOREBOARD_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
DEFAULT_ESPN_SCOREBOARD_URL = f"{ESPN_SOCCER_SCOREBOARD_BASE_URL}/{DEFAULT_ESPN_LEAGUE}/scoreboard"


def scoreboard_url_for_league(league: str = DEFAULT_ESPN_LEAGUE) -> str:
    league = league.strip().strip("/")
    if not league:
        raise ValueError("ESPN league slug cannot be empty")
    return f"{ESPN_SOCCER_SCOREBOARD_BASE_URL}/{league}/scoreboard"


def fetch_scoreboard(url: str = DEFAULT_ESPN_SCOREBOARD_URL, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "split-peel/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_scoreboard(scoreboard: dict[str, Any], match_id: Optional[str] = None) -> dict[str, Any]:
    events = scoreboard.get("events") or []
    if not events:
        return {"league": _league_context(scoreboard), "match": None}

    event = _select_event(events, match_id)
    competition = (event.get("competitions") or [{}])[0]
    status = event.get("status") or competition.get("status") or {}
    venue = event.get("venue") or competition.get("venue") or {}

    return {
        "league": _league_context(scoreboard),
        "match": {
            "id": event.get("id"),
            "name": event.get("name"),
            "shortName": event.get("shortName"),
            "date": event.get("date"),
            "status": {
                "state": ((status.get("type") or {}).get("state")),
                "description": ((status.get("type") or {}).get("description")),
                "detail": ((status.get("type") or {}).get("detail")),
                "shortDetail": ((status.get("type") or {}).get("shortDetail")),
            },
            "venue": {
                "name": venue.get("displayName") or venue.get("fullName"),
                "city": ((venue.get("address") or {}).get("city")),
                "country": ((venue.get("address") or {}).get("country")),
            },
            "teams": [_normalize_competitor(competitor) for competitor in competition.get("competitors") or []],
        },
    }


def download_match_logos(match_context: dict[str, Any], asset_dir: Path) -> list[dict[str, Any]]:
    match = match_context.get("match")
    if not match:
        return []

    asset_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    for team in match.get("teams") or []:
        logo_url = team.get("logo")
        if not logo_url:
            continue
        suffix = Path(urllib.parse.urlparse(logo_url).path).suffix or ".png"
        filename = f"{_slug(team.get('abbreviation') or team.get('name') or 'team')}-logo{suffix}"
        path = asset_dir / filename
        request = urllib.request.Request(logo_url, headers={"User-Agent": "split-peel/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                path.write_bytes(response.read())
        except (TimeoutError, OSError, urllib.error.URLError) as error:
            team["logoDownloadError"] = str(error)
            continue
        team["localLogo"] = str(path)
        downloaded.append({"team": team.get("name"), "path": str(path)})
    return downloaded


def build_scoreboard_overlays(match_context: dict[str, Any]) -> dict[str, Any]:
    match = match_context.get("match")
    if not match:
        return {"overlays": []}

    teams = match.get("teams") or []
    overlays: list[dict[str, Any]] = []
    positions = {
        "home": {"x": 0.18, "y": 0.14},
        "away": {"x": 0.82, "y": 0.14},
    }
    fallback_positions = [{"x": 0.18, "y": 0.14}, {"x": 0.82, "y": 0.14}]

    for index, team in enumerate(teams[:2]):
        logo = team.get("localLogo")
        if not logo:
            continue
        position = positions.get(str(team.get("homeAway")), fallback_positions[index])
        overlays.append(
            {
                "name": f"{team.get('abbreviation') or team.get('name')} logo",
                "file": logo,
                "start": 0,
                "dur": "full",
                "x": position["x"],
                "y": position["y"],
                "scale": 0.16,
            }
        )

    score_overlay = _score_overlay(match, teams[:2])
    if score_overlay:
        overlays.append(score_overlay)

    return {"overlays": overlays}


def _score_overlay(match: dict[str, Any], teams: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if len(teams) < 2 or not _match_completed(match):
        return None
    first_score = teams[0].get("score")
    second_score = teams[1].get("score")
    if first_score is None or second_score is None:
        return None

    asset_dir = _score_asset_dir(teams)
    if asset_dir is None:
        return None
    asset_dir.mkdir(parents=True, exist_ok=True)
    path = asset_dir / "score-overlay.png"
    _render_score_overlay(f"{first_score} - {second_score}", path)
    return {
        "name": "final score",
        "file": str(path),
        "start": 0,
        "dur": "full",
        "x": 0.5,
        "y": 0.14,
        "scale": 0.18,
    }


def _match_completed(match: dict[str, Any]) -> bool:
    status = match.get("status") or {}
    state = str(status.get("state") or "").lower()
    description = " ".join(
        str(status.get(key) or "").lower()
        for key in ("description", "detail", "shortDetail")
    )
    return state == "post" or "final" in description or "full time" in description or "completed" in description


def _score_asset_dir(teams: list[dict[str, Any]]) -> Optional[Path]:
    for team in teams:
        local_logo = team.get("localLogo")
        if local_logo:
            return Path(str(local_logo)).expanduser().parent
    return None


def _render_score_overlay(score: str, path: Path) -> None:
    width, height = 520, 150
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 24, width - 18, height - 24), radius=26, fill=(4, 8, 18, 218), outline=(255, 255, 255, 120), width=3)
    font = _score_font(76)
    bbox = draw.textbbox((0, 0), score, font=font, stroke_width=2)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        ((width - text_width) / 2, (height - text_height) / 2 - 7),
        score,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 200),
    )
    image.save(path)


def _score_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in (
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _league_context(scoreboard: dict[str, Any]) -> dict[str, Any]:
    league = (scoreboard.get("leagues") or [{}])[0]
    return {
        "id": league.get("id"),
        "name": league.get("name"),
        "abbreviation": league.get("abbreviation"),
        "season": league.get("season"),
    }


def _select_featured_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    state_rank = {"in": 0, "post": 1, "pre": 2}
    return sorted(
        events,
        key=lambda event: (
            state_rank.get((((event.get("status") or {}).get("type") or {}).get("state")), 3),
            str(event.get("date") or ""),
        ),
    )[0]


def _select_event(events: list[dict[str, Any]], match_id: Optional[str] = None) -> dict[str, Any]:
    if match_id:
        requested = str(match_id)
        for event in events:
            if str(event.get("id")) == requested:
                return event
        available = ", ".join(str(event.get("id")) for event in events if event.get("id"))
        raise ValueError(f"ESPN match id {requested} was not found in scoreboard events. Available ids: {available}")
    return _select_featured_event(events)


def _normalize_competitor(competitor: dict[str, Any]) -> dict[str, Any]:
    team = competitor.get("team") or {}
    records = competitor.get("records") or []
    return {
        "id": team.get("id") or competitor.get("id"),
        "homeAway": competitor.get("homeAway"),
        "name": team.get("displayName") or team.get("name"),
        "shortName": team.get("shortDisplayName"),
        "abbreviation": team.get("abbreviation"),
        "score": competitor.get("score"),
        "winner": competitor.get("winner"),
        "form": competitor.get("form"),
        "record": records[0].get("summary") if records else None,
        "color": team.get("color"),
        "alternateColor": team.get("alternateColor"),
        "logo": team.get("logo"),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
