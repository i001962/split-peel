from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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
        return {"league": _league_context(scoreboard), "match": None, "matches": []}

    matches = [_normalize_event(event) for event in events]
    selected_event = _select_event(events, match_id)
    selected_id = str(selected_event.get("id") or "")
    selected_match = next((match for match in matches if str(match.get("id") or "") == selected_id), matches[0])

    return {
        "league": _league_context(scoreboard),
        "match": selected_match,
        "matches": matches,
    }


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    competition = (event.get("competitions") or [{}])[0]
    status = event.get("status") or competition.get("status") or {}
    venue = event.get("venue") or competition.get("venue") or {}
    return {
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
        "keyMoments": _key_moments(event, competition),
    }


def download_match_logos(match_context: dict[str, Any], asset_dir: Path) -> list[dict[str, Any]]:
    matches = _context_matches(match_context)
    if not matches:
        return []

    asset_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in matches:
        for team in match.get("teams") or []:
            logo_url = team.get("logo")
            if not logo_url:
                continue
            team_key = str(team.get("id") or team.get("abbreviation") or team.get("name") or logo_url)
            if team_key in seen:
                existing = _existing_logo_path(match_context, team_key)
                if existing:
                    team["localLogo"] = existing
                continue
            seen.add(team_key)
            _download_team_logo(team, asset_dir, downloaded)
    return downloaded


def _context_matches(match_context: dict[str, Any]) -> list[dict[str, Any]]:
    matches = [match for match in match_context.get("matches") or [] if isinstance(match, dict)]
    match = match_context.get("match")
    if isinstance(match, dict) and match not in matches:
        matches.insert(0, match)
    return matches


def _existing_logo_path(match_context: dict[str, Any], team_key: str) -> Optional[str]:
    for match in _context_matches(match_context):
        for team in match.get("teams") or []:
            current_key = str(team.get("id") or team.get("abbreviation") or team.get("name") or team.get("logo") or "")
            if current_key == team_key and team.get("localLogo"):
                return str(team["localLogo"])
    return None


def _download_team_logo(team: dict[str, Any], asset_dir: Path, downloaded: list[dict[str, Any]]) -> None:
    logo_url = team.get("logo")
    if not logo_url:
        return
    suffix = Path(urllib.parse.urlparse(logo_url).path).suffix or ".png"
    filename = f"{_slug(team.get('abbreviation') or team.get('name') or 'team')}-logo{suffix}"
    path = asset_dir / filename
    request = urllib.request.Request(logo_url, headers={"User-Agent": "split-peel/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
    except (TimeoutError, OSError, urllib.error.URLError) as error:
        team["logoDownloadError"] = str(error)
        return
    team["localLogo"] = str(path)
    downloaded.append({"team": team.get("name"), "path": str(path)})


def build_scoreboard_overlays(match_context: dict[str, Any], episode_type: str = "match-event") -> dict[str, Any]:
    if episode_type == "game-week-preview":
        slate_overlays = _game_week_preview_overlays(match_context)
        if slate_overlays:
            return {"overlays": slate_overlays}

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
    moments_overlay = _moments_overlay(match, teams[:2])
    if moments_overlay:
        overlays.append(moments_overlay)

    return {"overlays": overlays}


def _game_week_preview_overlays(match_context: dict[str, Any]) -> list[dict[str, Any]]:
    matches = [match for match in match_context.get("matches") or [] if _match_has_two_teams(match)]
    if not matches:
        match = match_context.get("match")
        matches = [match] if isinstance(match, dict) and _match_has_two_teams(match) else []
    if not matches:
        return []

    asset_dir = _slate_asset_dir(matches)
    if asset_dir is None:
        return []
    asset_dir.mkdir(parents=True, exist_ok=True)

    page_size = 5
    max_pages = 2
    pages = [matches[index : index + page_size] for index in range(0, min(len(matches), page_size * max_pages), page_size)]
    overlays: list[dict[str, Any]] = []
    for page_index, page_matches in enumerate(pages):
        remaining = max(0, len(matches) - ((page_index + 1) * page_size))
        path = asset_dir / f"game-week-slate-{page_index + 1}.png"
        _render_game_week_slate(page_matches, path, page_index + 1, len(pages), remaining if page_index == len(pages) - 1 else 0)
        overlays.append(
            {
                "name": f"game week slate {page_index + 1}",
                "file": str(path),
                "start": 8 + page_index * 12,
                "dur": 12,
                "x": 0.5,
                "y": 0.48,
                "scale": 0.58,
            }
        )
    return overlays


def _match_has_two_teams(match: Any) -> bool:
    return isinstance(match, dict) and len(match.get("teams") or []) >= 2


def _slate_asset_dir(matches: list[dict[str, Any]]) -> Optional[Path]:
    for match in matches:
        asset_dir = _score_asset_dir(match.get("teams") or [])
        if asset_dir:
            return asset_dir
    return None


def _render_game_week_slate(
    matches: list[dict[str, Any]],
    path: Path,
    page_number: int,
    page_count: int,
    remaining_count: int = 0,
) -> None:
    width, height = 1120, 620
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 20, width - 24, height - 20), radius=26, fill=(4, 8, 18, 224), outline=(255, 255, 255, 86), width=2)
    title_font = _score_font(44)
    meta_font = _score_font(22)
    team_font = _score_font(28)
    time_font = _score_font(24)

    draw.text((52, 42), "GAME WEEK PREVIEW", font=title_font, fill=(255, 255, 255, 255))
    draw.text((width - 176, 56), f"PAGE {page_number}/{page_count}", font=meta_font, fill=(157, 235, 211, 255))
    y = 120
    row_h = 88
    for match in matches:
        teams = match.get("teams") or []
        left, right = _home_away_pair(teams)
        draw.rounded_rectangle((48, y, width - 48, y + 70), radius=16, fill=(12, 24, 38, 234), outline=(255, 255, 255, 40), width=1)
        _paste_logo(image, left.get("localLogo"), 82, y + 11, 48)
        _paste_logo(image, right.get("localLogo"), 690, y + 11, 48)
        draw.text((146, y + 19), _fit_text(_team_label(left), 24), font=team_font, fill=(255, 255, 255, 255))
        draw.text((560, y + 21), "v", font=team_font, fill=(250, 211, 60, 255))
        draw.text((754, y + 19), _fit_text(_team_label(right), 24), font=team_font, fill=(255, 255, 255, 255))
        kickoff = _kickoff_label(match)
        bbox = draw.textbbox((0, 0), kickoff, font=time_font)
        draw.text((width - 70 - (bbox[2] - bbox[0]), y + 22), kickoff, font=time_font, fill=(190, 225, 255, 255))
        y += row_h

    if remaining_count:
        draw.text((54, height - 58), f"+ {remaining_count} more fixtures on the ESPN slate", font=time_font, fill=(250, 211, 60, 255))
    image.save(path)


def _home_away_pair(teams: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    home = next((team for team in teams if str(team.get("homeAway")).lower() == "home"), teams[0])
    away = next((team for team in teams if str(team.get("homeAway")).lower() == "away"), teams[1])
    return home, away


def _team_label(team: dict[str, Any]) -> str:
    return str(team.get("shortName") or team.get("name") or team.get("abbreviation") or "Team")


def _kickoff_label(match: dict[str, Any]) -> str:
    date = str(match.get("date") or "").strip()
    if date:
        try:
            normalized = date.replace("Z", "+00:00")
            kickoff = datetime.fromisoformat(normalized).astimezone(timezone.utc)
            return kickoff.strftime("%a %H:%M UTC")
        except ValueError:
            pass
    status = match.get("status") or {}
    return str(status.get("shortDetail") or status.get("detail") or status.get("description") or "TBD")


def _paste_logo(image: Image.Image, logo_path: Any, x: int, y: int, size: int) -> None:
    if not logo_path:
        return
    path = Path(str(logo_path)).expanduser()
    if not path.exists():
        return
    try:
        logo = Image.open(path).convert("RGBA")
    except OSError:
        return
    logo.thumbnail((size, size), Image.LANCZOS)
    left = x + (size - logo.width) // 2
    top = y + (size - logo.height) // 2
    image.alpha_composite(logo, (left, top))


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


def _moments_overlay(match: dict[str, Any], teams: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    moments = match.get("keyMoments") or []
    if not moments:
        return None
    asset_dir = _score_asset_dir(teams)
    if asset_dir is None:
        return None
    asset_dir.mkdir(parents=True, exist_ok=True)
    path = asset_dir / "key-moments-overlay.png"
    title = str(match.get("shortName") or match.get("name") or "Match")
    _render_moments_overlay(title, moments[:4], path)
    return {
        "name": "key moments",
        "file": str(path),
        "start": 0,
        "dur": "full",
        "x": 0.5,
        "y": 0.31,
        "scale": 0.28,
    }


def _render_moments_overlay(title: str, moments: list[dict[str, Any]], path: Path) -> None:
    width, height = 760, 280
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 16, width - 18, height - 16), radius=22, fill=(4, 8, 18, 212), outline=(255, 255, 255, 90), width=2)
    title_font = _score_font(38)
    body_font = _score_font(27)
    draw.text((42, 34), title, font=title_font, fill=(255, 255, 255, 255))
    y = 92
    for moment in moments:
        clock = str(moment.get("clock") or "").strip()
        text = str(moment.get("text") or moment.get("type") or "").strip()
        team = str(moment.get("team") or "").strip()
        prefix = f"{clock} " if clock else ""
        suffix = f" ({team})" if team else ""
        line = _fit_text(f"{prefix}{text}{suffix}", 50)
        draw.text((46, y), line, font=body_font, fill=(242, 246, 255, 255))
        y += 42
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


def _key_moments(event: dict[str, Any], competition: dict[str, Any]) -> list[dict[str, Any]]:
    details = competition.get("details") or event.get("details") or competition.get("scoringPlays") or event.get("scoringPlays") or []
    teams_by_id = _teams_by_id(competition)
    moments = []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        moment_type = _moment_type(detail)
        athlete = _moment_athlete(detail)
        text = _moment_text(detail, moment_type, athlete)
        if not text:
            continue
        team = _moment_team(detail, teams_by_id)
        moments.append(
            {
                "clock": _moment_clock(detail),
                "type": moment_type,
                "text": text,
                "team": team,
                "score": _moment_score(detail),
            }
        )
    return moments[:8]


def _moment_clock(detail: dict[str, Any]) -> Optional[str]:
    for key in ("clock", "time", "displayTime"):
        value = detail.get(key)
        if isinstance(value, dict):
            display_value = value.get("displayValue") or value.get("display")
            if display_value:
                return str(display_value)
        elif value:
            return str(value)
    if detail.get("minute") is not None:
        return f"{detail['minute']}'"
    return None


def _moment_type(detail: dict[str, Any]) -> Optional[str]:
    raw_type = detail.get("type")
    if isinstance(raw_type, dict):
        value = raw_type.get("text") or raw_type.get("displayName") or raw_type.get("name")
        return str(value) if value else None
    if raw_type:
        return str(raw_type)
    return None


def _moment_athlete(detail: dict[str, Any]) -> Optional[str]:
    athletes = detail.get("athletesInvolved") or detail.get("athletes") or []
    if athletes and isinstance(athletes[0], dict):
        value = athletes[0].get("shortName") or athletes[0].get("displayName") or athletes[0].get("fullName")
        return str(value) if value else None
    athlete = detail.get("athlete")
    if isinstance(athlete, dict):
        value = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName")
        return str(value) if value else None
    return None


def _moment_text(detail: dict[str, Any], moment_type: Optional[str], athlete: Optional[str]) -> str:
    raw_text = detail.get("text") or detail.get("displayText") or detail.get("headline")
    if raw_text:
        return str(raw_text)
    if athlete and moment_type:
        return f"{athlete}: {moment_type}"
    if athlete:
        return athlete
    return str(moment_type or "")


def _moment_team(detail: dict[str, Any], teams_by_id: dict[str, str]) -> Optional[str]:
    team = detail.get("team") or {}
    if isinstance(team, dict):
        team_id = str(team.get("id") or "")
        if team_id and team_id in teams_by_id:
            return teams_by_id[team_id]
        value = team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName") or team.get("name")
        return str(value) if value else None
    if team:
        return str(team)
    return None


def _moment_score(detail: dict[str, Any]) -> Any:
    for key in ("scoreValue", "score", "homeScore", "awayScore"):
        value = detail.get(key)
        if value not in (None, 0, "0"):
            return value
    return None


def _teams_by_id(competition: dict[str, Any]) -> dict[str, str]:
    teams = {}
    for competitor in competition.get("competitors") or []:
        team = competitor.get("team") or {}
        team_id = str(team.get("id") or competitor.get("id") or "")
        if not team_id:
            continue
        label = team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName") or team.get("name")
        if label:
            teams[team_id] = str(label)
    return teams


def _fit_text(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "..."


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
