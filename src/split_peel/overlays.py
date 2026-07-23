from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from split_peel.package_ids import make_id


def load_overlay_manifest(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    overlays = payload.get("overlays", payload if isinstance(payload, list) else [])
    if not isinstance(overlays, list):
        raise ValueError("overlay manifest must be a list or an object with overlays[]")
    return overlays


def apply_overlays(
    package_dir: Path,
    show: dict[str, Any],
    overlays: list[dict[str, Any]],
    duration: float,
    episode_type: str | None = None,
) -> None:
    if not overlays:
        return

    assets = show.setdefault("assets", [])
    stage = show.setdefault("stage", {})
    image_tracks = stage.setdefault("imageTracks", [])
    background_tracks = stage.setdefault("backgroundTracks", [])
    assets_dir = package_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, overlay in enumerate(overlays):
        if not _overlay_applies_to_episode(overlay, episode_type):
            continue
        source = Path(str(overlay["file"])).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.exists():
            raise FileNotFoundError(f"overlay asset does not exist: {source}")

        name = str(overlay.get("name") or source.stem)
        asset_id = make_id(f"asset-{name}-{source.name}-{index}")
        cue_id = make_id(f"cue-{name}-{index}")
        track_id = make_id(f"track-{name}-{index}")
        destination = assets_dir / f"{asset_id}{source.suffix.lower()}"
        shutil.copy2(source, destination)

        assets.append(
            {
                "file": destination.name,
                "id": asset_id,
                "kind": str(overlay.get("kind") or _asset_kind(source)),
                "name": name,
            }
        )

        start = float(overlay.get("start", 0))
        cue_duration = _overlay_duration(overlay.get("dur", "full"), start, duration)
        cue = {
            "assetID": asset_id,
            "dur": round(cue_duration, 3),
            "from": {
                "scale": float(overlay.get("scale", 0.3)),
                "x": float(overlay.get("x", 0.5)),
                "y": float(overlay.get("y", 0.5)),
            },
            "id": cue_id,
            "start": round(start, 3),
        }
        if str(overlay.get("target") or "").lower() == "background":
            cue.pop("from", None)
            cue["crop"] = str(overlay.get("crop") or "cover")
            if bool(overlay.get("replace") or overlay.get("replaceBackground")):
                background_tracks.clear()
            background_tracks.append(
                {
                    "cues": [cue],
                    "hidden": False,
                    "id": track_id,
                    "name": str(overlay.get("trackName") or name),
                    "presence": [],
                }
            )
        else:
            image_tracks.append(
                {
                    "cues": [cue],
                    "hidden": False,
                    "id": track_id,
                    "name": str(overlay.get("trackName") or name),
                    "presence": [],
                }
            )


def _overlay_applies_to_episode(overlay: dict[str, Any], episode_type: str | None) -> bool:
    if not episode_type:
        return True
    include = _episode_type_set(overlay.get("includeEpisodeTypes"))
    exclude = _episode_type_set(overlay.get("excludeEpisodeTypes"))
    if include and episode_type not in include:
        return False
    if exclude and episode_type in exclude:
        return False
    return True


def _episode_type_set(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value if item}
    return set()


def build_pfp_overlays(script: dict[str, Any], asset_dir: Path, limit: int = 5) -> dict[str, Any]:
    source_casts = {
        cast.get("username"): cast
        for cast in script.get("sourceCasts") or []
        if cast.get("username") and cast.get("pfpUrl")
    }
    if not source_casts:
        return {"overlays": []}

    asset_dir.mkdir(parents=True, exist_ok=True)
    overlays: list[dict[str, Any]] = []
    used: set[str] = set()
    positions = [{"x": 0.08, "y": 0.28}, {"x": 0.92, "y": 0.28}]

    for line in script.get("dialogue") or []:
        username = line.get("sourceUsername")
        if not username or username in used or username not in source_casts:
            continue
        cast = source_casts[username]
        local_path = _download_pfp(str(cast["pfpUrl"]), username, asset_dir)
        position = positions[len(overlays) % len(positions)]
        start = max(0.0, float(line.get("start") or 0) - 0.2)
        overlays.append(
            {
                "name": f"@{username} pfp",
                "file": str(local_path),
                "start": round(start, 3),
                "dur": 5.0,
                "x": position["x"],
                "y": position["y"],
                "scale": 0.12,
            }
        )
        used.add(username)
        if len(overlays) >= limit:
            break

    return {"overlays": overlays}


def build_key_moment_takeover_overlays(script: dict[str, Any], asset_dir: Path) -> dict[str, Any]:
    match = script.get("match") or {}
    moments = [moment for moment in match.get("keyMoments") or [] if isinstance(moment, dict)]
    if not moments:
        return {"overlays": []}

    timing = _key_moment_takeover_timing(script, moments)
    if timing is None:
        return {"overlays": []}

    asset_dir.mkdir(parents=True, exist_ok=True)
    path = asset_dir / "key-moments-takeover.png"
    _render_key_moment_takeover(match, moments[:5], path)
    return {
        "overlays": [
            {
                "name": "key moments takeover",
                "file": str(path),
                "start": timing["start"],
                "dur": timing["dur"],
                "x": 0.5,
                "y": 0.5,
                "scale": 1.0,
            }
        ]
    }


def _key_moment_takeover_timing(script: dict[str, Any], moments: list[dict[str, Any]]) -> dict[str, float] | None:
    dialogue = [line for line in script.get("dialogue") or [] if isinstance(line, dict)]
    if not dialogue:
        return None

    moment_needles = []
    for moment in moments[:5]:
        for key in ("clock", "text", "type"):
            value = str(moment.get(key) or "").strip().lower()
            if value:
                moment_needles.append(value)
    matched_indexes = []
    for index, line in enumerate(dialogue):
        text = str(line.get("line") or "").lower()
        if any(needle and needle in text for needle in moment_needles):
            matched_indexes.append(index)

    if not matched_indexes:
        return None

    first_index = matched_indexes[0]
    last_index = matched_indexes[-1]
    start = max(0.0, float(dialogue[first_index].get("start") or 0) - 0.2)
    if last_index + 1 < len(dialogue):
        end = float(dialogue[last_index + 1].get("start") or start + 7.0) - 0.15
    else:
        end = start + 7.0
    return {"start": round(start, 3), "dur": round(max(3.5, end - start), 3)}


def _render_key_moment_takeover(match: dict[str, Any], moments: list[dict[str, Any]], path: Path) -> None:
    width, height = 1280, 720
    image = Image.new("RGBA", (width, height), (4, 8, 16, 255))
    draw = ImageDraw.Draw(image)
    _draw_takeover_background(draw, width, height)
    _draw_match_header(draw, match, width)
    _draw_moment_timeline(draw, moments, width, height)
    image.save(path)


def _draw_takeover_background(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for y in range(height):
        shade = int(10 + 34 * (y / height))
        draw.line([(0, y), (width, y)], fill=(4, shade, 26 + shade // 3, 255))
    draw.rectangle((0, 0, width, height), outline=(255, 255, 255, 34), width=2)
    for x in range(0, width, 80):
        draw.line((x, 0, x - 220, height), fill=(255, 255, 255, 10), width=1)
    draw.rounded_rectangle((58, 58, width - 58, height - 58), radius=24, outline=(255, 255, 255, 76), width=2)


def _draw_match_header(draw: ImageDraw.ImageDraw, match: dict[str, Any], width: int) -> None:
    title_font = _font(46)
    sub_font = _font(26)
    teams = match.get("teams") or []
    left = teams[0] if len(teams) > 0 else {}
    right = teams[1] if len(teams) > 1 else {}
    left_label = str(left.get("abbreviation") or left.get("shortName") or left.get("name") or "HOME")
    right_label = str(right.get("abbreviation") or right.get("shortName") or right.get("name") or "AWAY")
    left_score = str(left.get("score") if left.get("score") is not None else "")
    right_score = str(right.get("score") if right.get("score") is not None else "")
    score = f"{left_score} - {right_score}" if left_score or right_score else str(match.get("shortName") or "KEY MOMENTS")

    draw.text((82, 78), "KEY MOMENTS", font=sub_font, fill=(142, 220, 255, 255))
    draw.text((82, 112), f"{left_label}  {score}  {right_label}", font=title_font, fill=(255, 255, 255, 255))
    status = (match.get("status") or {}).get("shortDetail") or (match.get("status") or {}).get("detail") or (match.get("venue") or {}).get("name") or ""
    if status:
        draw.text((84, 168), str(status), font=sub_font, fill=(204, 214, 230, 230))
    draw.rounded_rectangle((width - 405, 82, width - 82, 158), radius=14, fill=(12, 24, 40, 245), outline=(255, 255, 255, 90), width=1)
    draw.text((width - 365, 103), "FINAL WHISTLE", font=_font(30), fill=(255, 255, 255, 245))


def _draw_moment_timeline(draw: ImageDraw.ImageDraw, moments: list[dict[str, Any]], width: int, height: int) -> None:
    top = 240
    left = 116
    card_w = width - 232
    card_h = 74
    gap = 18
    clock_font = _font(34)
    player_font = _font(30)
    team_font = _font(22)

    for index, moment in enumerate(moments):
        y = top + index * (card_h + gap)
        if y + card_h > height - 78:
            break
        event_type = str(moment.get("type") or moment.get("text") or "").lower()
        accent = _event_color(event_type)
        fill = (10, 18, 32, 235) if index % 2 == 0 else (14, 24, 42, 235)
        draw.rounded_rectangle((left, y, left + card_w, y + card_h), radius=18, fill=fill, outline=(255, 255, 255, 42), width=1)
        draw.rectangle((left, y + 12, left + 6, y + card_h - 12), fill=accent)

        icon_x = left + 42
        icon_y = y + card_h // 2
        _draw_event_icon(draw, event_type, icon_x, icon_y)

        clock = str(moment.get("clock") or "").strip()
        draw.text((left + 112, y + 19), clock, font=clock_font, fill=(255, 255, 255, 255))

        text = _moment_label(moment)
        draw.text((left + 225, y + 16), text, font=player_font, fill=(255, 255, 255, 255))
        team = str(moment.get("team") or "").strip()
        if team:
            draw.text((left + card_w - 130, y + 23), team, font=team_font, fill=(185, 206, 225, 235))


def _draw_event_icon(draw: ImageDraw.ImageDraw, event_type: str, x: int, y: int) -> None:
    if "penalty" in event_type:
        draw.ellipse((x - 29, y - 29, x + 29, y + 29), outline=(255, 255, 255, 255), width=4)
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 255, 255, 255))
        draw.line((x - 18, y + 18, x + 18, y - 18), fill=(87, 214, 255, 255), width=4)
        return
    if "yellow" in event_type:
        draw.rounded_rectangle((x - 18, y - 26, x + 18, y + 26), radius=4, fill=(250, 213, 48, 255), outline=(255, 244, 174, 255), width=2)
        return
    if "red card" in event_type or event_type.strip() == "red":
        draw.rounded_rectangle((x - 18, y - 26, x + 18, y + 26), radius=4, fill=(220, 37, 50, 255), outline=(255, 172, 180, 255), width=2)
        return
    draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=(245, 248, 252, 255), outline=(8, 18, 32, 255), width=3)
    draw.polygon([(x, y - 13), (x + 13, y - 4), (x + 8, y + 12), (x - 8, y + 12), (x - 13, y - 4)], fill=(9, 17, 30, 255))
    draw.line((x - 28, y, x - 13, y - 4), fill=(9, 17, 30, 255), width=2)
    draw.line((x + 28, y, x + 13, y - 4), fill=(9, 17, 30, 255), width=2)


def _event_color(event_type: str) -> tuple[int, int, int, int]:
    if "yellow" in event_type:
        return (250, 213, 48, 255)
    if "penalty" in event_type:
        return (87, 214, 255, 255)
    if "red card" in event_type or event_type.strip() == "red":
        return (220, 37, 50, 255)
    return (70, 238, 147, 255)


def _moment_label(moment: dict[str, Any]) -> str:
    text = " ".join(str(moment.get("text") or moment.get("type") or "Moment").split())
    return text[:48] + "..." if len(text) > 51 else text


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _overlay_duration(raw_duration: Any, start: float, show_duration: float) -> float:
    if raw_duration == "full" or raw_duration is None:
        return max(0.0, show_duration - start)
    return float(raw_duration)


def _asset_kind(source: Path) -> str:
    if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        return "video"
    return "image"


def _download_pfp(url: str, username: str, asset_dir: Path) -> Path:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    destination = asset_dir / f"{_slug(username)}-pfp{suffix}"
    request = urllib.request.Request(url, headers={"User-Agent": "split-peel/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())
    return destination


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-")[:80]
